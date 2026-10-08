"""Word 加载器接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from parser_engine.document.ast.document import DocumentAST


class WordLoader(ABC):
    """Word 文档加载器抽象基类。"""

    @abstractmethod
    def load(self, file_path: str) -> DocumentAST:
        """加载 Word 文档并转换为 AST。

        Args:
            file_path: Word 文件路径。

        Returns:
            DocumentAST: 统一文档对象。
        """
