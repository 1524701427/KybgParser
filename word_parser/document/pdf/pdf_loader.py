'''基于 opendataloader-pdf 的 PDF 加载器。'''

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.logger import logger


class OpenDataLoaderPdfLoader:
    '''将文本层 PDF 加载为统一的 DocumentAST。'''

    def load(self, file_path: str) -> DocumentAST:
        path = Path(file_path)
        if path.suffix.lower() != '.pdf':
            raise ValueError('OpenDataLoaderPdfLoader 仅支持 .pdf 文件')
        try:
            from opendataloader_pdf import convert  # type: ignore
        except Exception as exc:
            raise RuntimeError('解析 PDF 需要 opendataloader-pdf，请先安装对应依赖。') from exc

        logger.info(f'使用 OpenDataLoaderPdfLoader 解析 PDF：{path}')
        with tempfile.TemporaryDirectory(prefix='opendataloader_pdf_') as output_dir:
            convert(input_path=str(path), output_dir=output_dir, format='json', quiet=True, table_method='cluster', reading_order='xycut', image_output='off')
            data = json.loads(self._find_output_json(output_dir, path).read_text(encoding='utf-8'))
        ast = self._ast_from_json(path, data)
        self._attach_pdf_page_texts(path, ast)
        self._recover_missing_tables(path, ast)
        if not ast.blocks and not ast.tables:
            raise RuntimeError('PDF 没有可抽取的文本层，暂不支持扫描版 PDF。')
        logger.info(f'PDF 解析完成：文本块 {len(ast.blocks)} 个，表格 {len(ast.tables)} 个')
        return ast

    def _attach_pdf_page_texts(self, path: Path, ast: DocumentAST) -> None:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            logger.warning(f'已跳过 PDF 页面文本兜底：PyMuPDF 不可用：{exc}')
            return
        tools = getattr(fitz, 'TOOLS', None)
        if tools is not None:
            for method_name in ('mupdf_display_errors', 'mupdf_display_warnings'):
                method = getattr(tools, method_name, None)
                if method is None:
                    continue
                try:
                    method(False)
                except Exception:
                    pass
        page_texts: list[dict[str, Any]] = []
        page_lines: list[dict[str, Any]] = []
        try:
            with fitz.open(path) as doc:
                for page_index in range(doc.page_count):
                    raw_text = (doc.load_page(page_index).get_text('text') or '').replace('\x00', ' ')
                    text = self._clean_text(raw_text)
                    if text:
                        page_texts.append({'page': page_index + 1, 'text': text})
                        page_lines.append({'page': page_index + 1, 'text': raw_text})
        except Exception as exc:
            logger.warning(f'已跳过 PDF 页面文本兜底：{exc}')
            return
        if page_texts:
            ast.meta['pdf_page_texts'] = page_texts
            ast.meta['pdf_page_lines'] = page_lines

    def _recover_missing_tables(self, path: Path, ast: DocumentAST) -> None:
        """用 PDF 页面几何信息补回主解析器漏识别的表格。"""
        try:
            import fitz  # type: ignore
        except Exception as exc:
            logger.warning(f'已跳过 PDF 表格补偿：PyMuPDF 不可用：{exc}')
            return
        page_texts = {item['page']: str(item['text']) for item in ast.meta.get('pdf_page_lines') or []}
        recovered = repaired = 0
        try:
            with fitz.open(path) as doc:
                for page_number in page_texts:
                    page = doc.load_page(page_number - 1)
                    for found in page.find_tables(strategy='lines').tables:
                        matrix = self._normalize_recovered_matrix(found.extract())
                        if len(matrix) < 3 or len(matrix[0]) < 2:
                            continue
                        existing = next((table for table in ast.tables
                                         if table.page == page_number
                                         and (self._boxes_match(table.meta.get('bounding_box'), found.bbox)
                                              or self._same_table_start(table.to_matrix(), matrix))), None)
                        caption = self._recovered_table_caption(page, found.bbox)
                        if existing is not None:
                            if self._has_shifted_header(existing.to_matrix()):
                                existing.rows = self._matrix_to_table(matrix, 0, existing.order, page_number).rows
                                existing.meta['geometry_recovered'] = True
                                for block in ast.blocks:
                                    if block.meta.get('table_id') == existing.id:
                                        block.text = self._table_text(existing)
                                        break
                                repaired += 1
                            if caption and (not existing.caption or not self._is_caption(existing.caption)
                                            or caption.startswith(existing.caption)):
                                existing.caption = caption
                            continue
                        order = max((block.order for block in ast.blocks), default=0) + 1
                        table = self._matrix_to_table(matrix, len(ast.tables) + 1, order, page_number)
                        table.caption = caption
                        table.meta['source'] = 'pdf_geometry_fallback'
                        table.meta['bounding_box'] = found.bbox
                        ast.tables.append(table)
                        ast.blocks.append(DocumentBlock(
                            id=f'tb_{len(ast.tables):04d}', type='table', text=self._table_text(table),
                            order=order, page=page_number,
                            meta={'table_id': table.id, 'source': 'pdf_geometry_fallback'},
                        ))
                        recovered += 1
            self._merge_continued_tables(ast)
        except Exception as exc:
            logger.warning(f'PDF 表格补偿中断：{exc}')
        if recovered or repaired:
            logger.info(f'PDF 几何表格补偿完成：修复 {repaired} 张表，新增 {recovered} 张表')

    def _boxes_match(self, original: Any, recovered: Any) -> bool:
        """用页面坐标判断两种解析器识别的是否为同一张表。"""
        if not isinstance(original, (list, tuple)) or len(original) != 4:
            return False
        try:
            a, b = [float(value) for value in original], [float(value) for value in recovered]
            intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
            area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
            area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
            return intersection / min(area_a, area_b) >= 0.6 if min(area_a, area_b) else False
        except (TypeError, ValueError):
            return False

    def _same_table_start(self, original: list[list[str]], recovered: list[list[str]]) -> bool:
        """当两个解析器给出的边框不同，用表头和首行识别重复表。"""
        if len(original) < 2 or len(recovered) < 2 or len(original[0]) != len(recovered[0]):
            return False
        return all(
            [self._clean_text(value) for value in original[index]]
            == [self._clean_text(value) for value in recovered[index]]
            for index in (0, 1)
        )

    def _normalize_recovered_matrix(self, raw_rows: list[list[Any]]) -> list[list[str]]:
        """清理单元格并合并分行表头，保持列位置不变。"""
        matrix = [[self._clean_text(str(cell or '')) for cell in row] for row in raw_rows]
        matrix = [row for row in matrix if any(row)]
        if len(matrix) < 2:
            return []
        width = max(map(len, matrix))
        matrix = [row + [''] * (width - len(row)) for row in matrix]
        if len(matrix) > 2:
            second = matrix[1]
            # PDF 常把分组标题和逐年列名放在两行；逐年列名才是实际列名。
            if sum(bool(re.fullmatch(r'第\s*\d+\s*年', cell)) for cell in second) >= 2:
                matrix[0] = [re.sub(r'\s+', '', child) if child else parent
                             for parent, child in zip(matrix[0], second)]
                del matrix[1]
        return matrix

    def _has_shifted_header(self, matrix: list[list[str]]) -> bool:
        """判断第二行表头是否错误地从首列开始排列。"""
        if len(matrix) < 3:
            return False
        first, second = matrix[:2]
        year_header_shift = (sum(bool(re.fullmatch(r'第\s*\d+\s*年', cell)) for cell in second) >= 2
                             and bool(first[0]) and bool(first[1])
                             and bool(re.fullmatch(r'第\s*\d+\s*年', second[0])))
        unit_row_shift = (first[0] in {'标签', '编号', '风机编号'}
                          and second[0] in {'m', 'MWh', 'kWh', '%', '/'}
                          and sum(cell in {'m', 'MWh', 'kWh', '%', '/', 'm/s', 'h'} for cell in second) >= 3)
        return year_header_shift or unit_row_shift

    def _merge_continued_tables(self, ast: DocumentAST) -> None:
        """将下一页没有重复表头的连续数据行接回前一页表格。"""
        ordered = sorted(ast.tables, key=lambda table: (table.page or 0, table.order))
        removed: set[str] = set()
        for current in ordered:
            if current.id in removed or not current.page or not current.rows:
                continue
            matrix = current.to_matrix()
            first = matrix[0][0].strip() if matrix[0] else ''
            if not re.fullmatch(r'(?:[A-Za-z]{1,4}\d{1,4}|\d{1,3})', first):
                continue
            previous = next((table for table in reversed(ordered)
                             if table.id not in removed and table.page == current.page - 1
                             and table.rows and len(table.rows[0]) == len(matrix[0])
                             and table.to_matrix()[0][0].strip() in ('标签', '序号', '编号')), None)
            if previous is None:
                continue
            start = len(previous.rows)
            for offset, row in enumerate(current.rows):
                for cell in row:
                    cell.row = start + offset
                previous.rows.append(row)
            removed.add(current.id)
            for block in ast.blocks:
                if block.meta.get('table_id') == previous.id:
                    block.text = self._table_text(previous)
                    break
        if removed:
            ast.tables = [table for table in ast.tables if table.id not in removed]
            ast.blocks = [block for block in ast.blocks if block.meta.get('table_id') not in removed]

    def _recovered_table_caption(self, page: Any, bounds: Any) -> str | None:
        """按页面坐标取紧邻表格上方的表题。"""
        top = float(bounds[1])
        candidates: list[tuple[float, str]] = []
        for block in page.get_text('blocks'):
            gap = top - float(block[3])
            if not 0 <= gap <= 80:
                continue
            lines = [line.strip() for line in str(block[4]).splitlines() if line.strip()]
            for index, line in enumerate(lines):
                line = line.strip()
                if self._is_caption(line):
                    if re.fullmatch(r'(?:表|附表|Table)\s*\d+(?:[.-]\d+)*', line, re.I) and index + 1 < len(lines):
                        line += ' ' + lines[index + 1]
                    candidates.append((gap, line))
        return min(candidates)[1] if candidates else None

    def _caption_links(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        links: dict[str, str] = {}
        for node in nodes:
            if str(node.get('type') or '').lower() != 'caption':
                continue
            target_id = node.get('linked content id')
            text = self._clean_text(str(node.get('content') or ''))
            if target_id is not None and text:
                links[str(target_id)] = text
        return links

    def _paragraph_block(self, node: dict[str, Any], index: int, order: int, structure_type: str | None = None) -> DocumentBlock:
        meta = {'opendataloader_id': node.get('id'), 'bounding_box': node.get('bounding box')}
        if structure_type:
            meta['structure_type'] = structure_type
        return DocumentBlock(id=f'p_{index:04d}', type='paragraph', text=self._clean_text(str(node.get('content') or '')), order=order, page=self._page_number(node), meta=meta)

    def _page_number(self, node: dict[str, Any]) -> int | None:
        value = node.get('page number')
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _table_matrix(self, node: dict[str, Any]) -> list[list[str]]:
        matrix: list[list[str]] = []
        for row in node.get('rows') or []:
            cells = row.get('cells') or []
            parsed = [self._cell_text(cell) for cell in cells]
            if any(parsed):
                matrix.append(parsed)
        max_cols = max((len(row) for row in matrix), default=0)
        if max_cols <= 1 or len(matrix) <= 1:
            return []
        return [row + [''] * (max_cols - len(row)) for row in matrix]

    def _cell_text(self, cell: dict[str, Any]) -> str:
        parts: list[str] = []
        for kid in cell.get('kids') or []:
            text = self._clean_text(str(kid.get('content') or ''))
            if text:
                parts.append(text)
        return self._clean_text(' '.join(parts))

    def _matrix_to_table(self, matrix: list[list[str]], index: int, order: int, page: int | None) -> DocumentTable:
        rows: list[list[TableCell]] = []
        for row_index, row in enumerate(matrix):
            rows.append([TableCell(text=text, row=row_index, col=col_index, is_header=row_index == 0) for col_index, text in enumerate(row)])
        return DocumentTable(id=f't_{index:04d}', order=order, page=page, rows=rows)

    def _caption_from_previous_block(self, ast: DocumentAST) -> str | None:
        for block in reversed(ast.blocks[-4:]):
            if block.type != 'paragraph':
                continue
            text = self._clean_text(block.text)
            if self._is_caption(text):
                return text
            if text:
                return None
        return None

    def _is_caption(self, text: str) -> bool:
        return bool(re.match(r'^(?:Table|\u8868|\u9644\u8868)\s*[\d\u4e00-\u9fa5A-Za-z.-]+', text, flags=re.IGNORECASE))

    def _table_text(self, table: DocumentTable) -> str:
        return '\n'.join(' | '.join(cell.text for cell in row) for row in table.rows)

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', (text or '').replace('\x00', ' ')).strip()
    def _find_output_json(self, output_dir: str, source_path: Path) -> Path:
        direct = Path(output_dir) / f'{source_path.stem}.json'
        if direct.exists():
            return direct
        matches = list(Path(output_dir).glob('*.json'))
        if matches:
            return matches[0]
        raise RuntimeError('opendataloader-pdf 未生成 JSON 输出')

    def _ast_from_json(self, path: Path, data: dict[str, Any]) -> DocumentAST:
        ast = DocumentAST(file_name=path.name, meta={'loader': 'OpenDataLoaderPdfLoader', 'ocr': False, 'source': 'opendataloader-pdf'})
        nodes = list(data.get('kids') or [])
        caption_by_target = self._caption_links(nodes)
        order = para_index = table_index = 0
        for node in nodes:
            node_type = str(node.get('type') or '').lower()
            if node_type == 'caption':
                para_index += 1
                block = self._paragraph_block(node, para_index, order, structure_type='table_caption')
                ast.blocks.append(block)
                order += 1
                continue
            if node_type == 'table':
                matrix = self._table_matrix(node)
                if not matrix:
                    continue
                table_index += 1
                table = self._matrix_to_table(matrix, table_index, order, self._page_number(node))
                caption = caption_by_target.get(str(node.get('id'))) or self._caption_from_previous_block(ast)
                if caption:
                    table.caption = caption
                    table.meta['caption_before'] = caption
                table.meta['opendataloader_id'] = node.get('id')
                table.meta['bounding_box'] = node.get('bounding box')
                ast.tables.append(table)
                ast.blocks.append(DocumentBlock(id=f'tb_{table_index:04d}', type='table', text=self._table_text(table), order=order, page=table.page, meta={'table_id': table.id, 'opendataloader_id': node.get('id')}))
                order += 1
                continue
            if node_type == 'paragraph':
                text = self._clean_text(str(node.get('content') or ''))
                if not text:
                    continue
                para_index += 1
                ast.blocks.append(self._paragraph_block(node, para_index, order))
                order += 1
        return ast


PdfTextLoader = OpenDataLoaderPdfLoader
