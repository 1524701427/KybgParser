"""对外解析服务。"""

from __future__ import annotations


class ParserService:
    """可被业务代码直接导入使用的解析服务。"""

    def __init__(self, pipeline):
        """初始化解析服务。

        Args:
            pipeline: 已装配好的解析流水线。
        """
        self.pipeline = pipeline

    def parse(self, file_path: str) -> dict:
        """解析 Word 文档。

        Args:
            file_path: Word 文档路径。

        Returns:
            dict: 解析结果。
        """
        return self.pipeline.parse(file_path)
