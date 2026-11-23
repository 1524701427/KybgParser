"""对外解析服务。"""

from __future__ import annotations


class ParserService:
    """可被业务代码直接导入使用的解析服务。"""

    def __init__(self, pipeline):
        """初始化解析服务。

        参数：
            pipeline: 已装配好的解析流水线。
        """
        self.pipeline = pipeline

    def parse(self, file_path: str) -> dict:
        """解析 Word 或 PDF 文档。

        参数：
            file_path: Word 或 PDF 文档路径。

        返回：
            dict: 解析结果。
        """
        return self.pipeline.parse(file_path)

    def parse_full(
        self,
        file_path: str,
        *,
        config_root=None,
        table_value_config=None,
    ) -> dict:
        """完整执行：预抽取、一次抽取、二次抽取、最终映射。

        原有 parse() 保持只运行一次抽取的兼容接口。
        """
        from word_parser.application.workflow import run_full_parse
        return run_full_parse(
            self, file_path,
            config_root=config_root,
            table_value_config=table_value_config,
        )
