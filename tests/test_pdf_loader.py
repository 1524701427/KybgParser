from __future__ import annotations

import sys
import json
from pathlib import Path

from parser_engine.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from parser_engine.document.layout_sidecar import LayoutTable, OpenDataLoaderLayoutSidecar
from parser_engine.document.loaders.document_loader import DocumentLoader
from parser_engine.document.loaders.pdf_loader import PdfTextLoader
from parser_engine.document import StructureParser


class FakeWordLoader:
    def load(self, file_path: str):
        return ('word', Path(file_path).suffix.lower())


class FakePdfLoader:
    def load(self, file_path: str):
        return ('pdf', Path(file_path).suffix.lower())


def test_document_loader_routes_by_suffix():
    loader = DocumentLoader(word_loader=FakeWordLoader(), pdf_loader=FakePdfLoader(), enable_word_pdf_layout=False)

    assert loader.load('sample.docx') == ('word', '.docx')
    assert loader.load('sample.doc') == ('word', '.doc')
    assert loader.load('sample.pdf') == ('pdf', '.pdf')


def test_document_loader_enriches_word_ast_with_pdf_layout_sidecar(tmp_path):
    """验证 Word 加载后会尝试把 PDF layout sidecar 挂回 AST。"""

    class FakeWordAstLoader:
        def load(self, file_path: str):
            return DocumentAST(
                file_name=Path(file_path).name,
                blocks=[DocumentBlock(id='tb1', type='table', text='', order=1, meta={'table_id': 't1'})],
                tables=[DocumentTable(id='t1', order=1, rows=[[TableCell(text='项目', row=0, col=0), TableCell(text='数值', row=0, col=1)]])],
            )

        def export_pdf(self, file_path: str, output_path):
            Path(output_path).write_bytes(b'%PDF-1.7')
            return True

    class FakeSidecar:
        def enrich_ast_from_pdf(self, ast, pdf_path):
            ast.tables[0].meta['layout_title_candidates'] = [{'source': 'layout_nearby_title', 'text': '附表 1：财务指标汇总表', 'score': 5.0}]
            ast.meta['layout_sidecar'] = {'status': 'ok', 'pdf': str(pdf_path)}
            return ast

    source = tmp_path / 'sample.docx'
    source.write_bytes(b'docx')
    loader = DocumentLoader(word_loader=FakeWordAstLoader(), pdf_loader=FakePdfLoader(), layout_sidecar=FakeSidecar())

    ast = loader.load(str(source))

    assert ast.meta['layout_sidecar']['status'] == 'ok'
    assert ast.tables[0].meta['layout_title_candidates'][0]['text'] == '附表 1：财务指标汇总表'


def test_layout_sidecar_attaches_pdf_title_candidates_to_word_table():
    """验证 OpenDataLoader sidecar 会把 PDF 表题候选写入 Word 表。"""
    ast = DocumentAST(
        file_name='sample.docx',
        blocks=[DocumentBlock(id='tb1', type='table', text='', order=1, meta={'table_id': 't1'})],
        tables=[
            DocumentTable(
                id='t1',
                order=1,
                rows=[
                    [TableCell(text='项目', row=0, col=0), TableCell(text='数值', row=0, col=1)],
                    [TableCell(text='容量', row=1, col=0), TableCell(text='100', row=1, col=1)],
                ],
            )
        ],
    )
    layout_table = LayoutTable(
        id=3,
        order=1,
        page=5,
        bbox=[100, 200, 500, 500],
        nearby_titles=[{'text': '附表 1：财务指标汇总表', 'score': 5.0, 'distance': 1, 'bbox': [120, 170, 480, 190], 'bold': True, 'alignment': 'center'}],
        matrix_preview=[['项目', '数值'], ['容量', '100']],
    )

    OpenDataLoaderLayoutSidecar().attach_layout_tables(ast, [layout_table])
    structured = StructureParser().parse(ast)

    table = structured.tables[0]
    assert table.page == 5
    assert table.caption == '附表 1：财务指标汇总表'
    assert table.meta['layout_title_candidates'][0]['source'] == 'layout_nearby_title'
    assert table.meta['caption_source'] == 'layout_nearby_title'


def test_pdf_text_loader_builds_ast_from_text_and_table(monkeypatch, tmp_path):
    class FakeOpenDataLoaderPdf:
        @staticmethod
        def convert(input_path, output_dir, format, quiet, table_method, reading_order, image_output):
            assert Path(input_path).suffix == '.pdf'
            assert format == 'json'
            assert quiet is True
            assert table_method == 'cluster'
            assert reading_order == 'xycut'
            assert image_output == 'off'
            data = {
                'kids': [
                    {'type': 'paragraph', 'id': 1, 'page number': 1, 'content': '1 Resource'},
                    {'type': 'caption', 'id': 2, 'page number': 1, 'linked content id': 3, 'content': 'Table 1 Road data'},
                    {
                        'type': 'table',
                        'id': 3,
                        'page number': 1,
                        'rows': [
                            {'cells': [{'kids': [{'content': 'name'}]}, {'kids': [{'content': 'value'}]}]},
                            {'cells': [{'kids': [{'content': 'road'}]}, {'kids': [{'content': '12.3'}]}]},
                        ],
                    },
                ]
            }
            (Path(output_dir) / 'sample.json').write_text(json.dumps(data), encoding='utf-8')

    monkeypatch.setitem(sys.modules, 'opendataloader_pdf', FakeOpenDataLoaderPdf)
    pdf_path = tmp_path / 'sample.pdf'
    pdf_path.write_bytes(b'%PDF-1.4 text fixture')

    ast = PdfTextLoader().load(str(pdf_path))

    assert ast.meta['loader'] == 'OpenDataLoaderPdfLoader'
    assert ast.blocks[0].page == 1
    assert ast.tables[0].caption == 'Table 1 Road data'
    assert ast.tables[0].to_matrix() == [['name', 'value'], ['road', '12.3']]
    assert ast.blocks[-1].meta['table_id'] == ast.tables[0].id
