"""Word 加载器接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from word_parser.document.ast.document import DocumentAST


class WordLoader(ABC):
    """Word 文档加载器抽象基类。"""

    @abstractmethod
    def load(self, file_path: str) -> DocumentAST:
        """加载 Word 文档并转换为 AST。

        参数：
            file_path: Word 文件路径。

        返回：
            DocumentAST: 统一文档对象。
        """
