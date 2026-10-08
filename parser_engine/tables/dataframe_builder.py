"""表格 DataFrame 构建器。"""

from __future__ import annotations

from parser_engine.document.ast.document import DocumentTable
from parser_engine.core.logger import logger


class DataFrameBuilder:
    """将统一表格对象转换为 pandas DataFrame。"""

    def build(self, table: DocumentTable):
        """构建 DataFrame。

        Args:
            table: 统一表格对象。

        Returns:
            pandas.DataFrame: 表格数据框。
        """
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("表格 DataFrame 增强需要安装 pandas") from exc
        matrix = table.to_matrix()
        df = pd.DataFrame(matrix)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        logger.info(f"表格已转换为 DataFrame：{table.id}")
        return df
