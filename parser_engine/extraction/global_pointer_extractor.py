"""GlobalPointer 抽取器适配器。"""

from __future__ import annotations


class GlobalPointerExtractor:
    """专用实体抽取模型适配器。"""

    def __init__(self, enabled: bool = False, mode: str = "shadow"):
        """初始化抽取器。

        Args:
            enabled: 是否启用。
            mode: 运行模式，支持 active/shadow/disabled。
        """
        self.enabled = enabled
        self.mode = mode

    def extract(self, match) -> list:
        """抽取字段实体。

        Args:
            match: 字段匹配结果。

        Returns:
            list: 实体抽取结果。初始版本返回空列表。
        """
        return []
