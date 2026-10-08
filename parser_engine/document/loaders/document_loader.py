'''File extension router for supported document loaders.'''

from __future__ import annotations

import tempfile
from pathlib import Path

from parser_engine.document.ast.document import DocumentAST
from parser_engine.core.logger import logger
from parser_engine.document.layout_sidecar import OpenDataLoaderLayoutSidecar
from parser_engine.document.loaders.aspose_loader import AsposeWordsLoader
from parser_engine.document.loaders.pdf_loader import OpenDataLoaderPdfLoader


class DocumentLoader:
    '''Route Word and text-layer PDF files into the common DocumentAST.'''

    def __init__(self, word_loader=None, pdf_loader=None, layout_sidecar=None, enable_word_pdf_layout: bool = True):
        """初始化文档加载器。

        Args:
            word_loader: Word 加载器。
            pdf_loader: PDF 加载器。
            layout_sidecar: Word->PDF 版面增强器。
            enable_word_pdf_layout: 是否对 Word 文档启用 PDF layout 旁路增强。
        """
        self.word_loader = word_loader or AsposeWordsLoader(fallback_to_simple=True)
        self.pdf_loader = pdf_loader or OpenDataLoaderPdfLoader()
        self.layout_sidecar = layout_sidecar or OpenDataLoaderLayoutSidecar()
        self.enable_word_pdf_layout = enable_word_pdf_layout

    def load(self, file_path: str) -> DocumentAST:
        """按文件后缀选择加载器并返回统一 AST。"""
        suffix = Path(file_path).suffix.lower()
        if suffix in {'.doc', '.docx'}:
            ast = self.word_loader.load(file_path)
            return self._enrich_word_ast_with_pdf_layout(file_path, ast)
        if suffix == '.pdf':
            return self.pdf_loader.load(file_path)
        raise ValueError(f'Unsupported document type: {suffix or file_path}')

    def _enrich_word_ast_with_pdf_layout(self, file_path: str, ast: DocumentAST) -> DocumentAST:
        """用 Word 转 PDF 的版面结果增强 AST。

        Args:
            file_path: Word 文件路径。
            ast: Word loader 已生成的 AST。

        Returns:
            DocumentAST: 增强后的 AST；失败时返回原 AST。
        """
        if not self.enable_word_pdf_layout:
            return ast
        export_pdf = getattr(self.word_loader, 'export_pdf', None)
        if export_pdf is None:
            logger.warning('当前 Word loader 不支持导出 PDF，跳过 layout sidecar')
            return ast
        try:
            with tempfile.TemporaryDirectory(prefix='word_pdf_layout_') as tmp_dir:
                pdf_path = Path(tmp_dir) / f'{Path(file_path).stem}.pdf'
                if not export_pdf(file_path, pdf_path):
                    return ast
                return self.layout_sidecar.enrich_ast_from_pdf(ast, pdf_path)
        except Exception as exc:
            logger.warning(f'Word PDF layout sidecar skipped: {exc}')
            ast.meta.setdefault('layout_sidecar', {})['status'] = 'failed'
            ast.meta.setdefault('layout_sidecar', {})['error'] = str(exc)
            return ast
