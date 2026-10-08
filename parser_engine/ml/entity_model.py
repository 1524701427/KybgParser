"""实体抽取模型适配器。"""

from __future__ import annotations


class EntityExtractionModel:
    """BERT-CRF/GlobalPointer 等实体抽取模型的统一包装。"""

    def __init__(self, enabled: bool = False, mode: str = "shadow"):
        """初始化实体抽取模型。

        Args:
            enabled: 是否启用真实模型。
            mode: 运行模式，支持 active/shadow/disabled。
        """
        self.enabled = enabled
        self.mode = mode

    def extract(self, text: str, schema: list[str]) -> list[dict]:
        """抽取字段实体。

        Args:
            text: 候选文本。
            schema: 抽取 schema。

        Returns:
            list[dict]: 实体列表。
        """
        return []
