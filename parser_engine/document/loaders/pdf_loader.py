'''PDF loader backed by opendataloader-pdf.'''

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from parser_engine.core.logger import logger


class OpenDataLoaderPdfLoader:
    '''Load text-layer PDFs into the common DocumentAST.'''

    def load(self, file_path: str) -> DocumentAST:
        path = Path(file_path)
        if path.suffix.lower() != '.pdf':
            raise ValueError('OpenDataLoaderPdfLoader only supports .pdf files')
        try:
            from opendataloader_pdf import convert  # type: ignore
        except Exception as exc:
            raise RuntimeError('PDF parsing requires opendataloader-pdf. Install requirements.txt again.') from exc

        logger.info(f'Using OpenDataLoaderPdfLoader to parse PDF: {path}')
        with tempfile.TemporaryDirectory(prefix='opendataloader_pdf_') as output_dir:
            convert(input_path=str(path), output_dir=output_dir, format='json', quiet=True, table_method='cluster', reading_order='xycut', image_output='off')
            data = json.loads(self._find_output_json(output_dir, path).read_text(encoding='utf-8'))
        ast = self._ast_from_json(path, data)
        self._attach_pdf_page_texts(path, ast)
        if not ast.blocks and not ast.tables:
            raise RuntimeError('PDF has no extractable text layer. Scanned PDFs are not supported.')
        logger.info(f'PDF parsing completed: blocks {len(ast.blocks)}, tables {len(ast.tables)}')
        return ast

    def _attach_pdf_page_texts(self, path: Path, ast: DocumentAST) -> None:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            logger.warning(f'PDF page text fallback skipped: PyMuPDF is unavailable: {exc}')
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
        try:
            with fitz.open(path) as doc:
                for page_index in range(doc.page_count):
                    text = self._clean_text(doc.load_page(page_index).get_text('text') or '')
                    if text:
                        page_texts.append({'page': page_index + 1, 'text': text})
        except Exception as exc:
            logger.warning(f'PDF page text fallback skipped: {exc}')
            return
        if page_texts:
            ast.meta['pdf_page_texts'] = page_texts

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
        raise RuntimeError('opendataloader-pdf did not generate JSON output')

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
