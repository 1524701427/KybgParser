"""候选排序模型适配器。"""

from __future__ import annotations


class SklearnCandidateRanker:
    """sklearn 候选排序器占位实现。"""

    def __init__(self, enabled: bool = False, mode: str = "shadow"):
        """初始化候选排序器。

        Args:
            enabled: 是否启用真实模型。
            mode: 运行模式，支持 active/shadow/disabled。
        """
        self.enabled = enabled
        self.mode = mode
        self.model = None

    def score(self, features: dict) -> float:
        """计算候选值排序分。

        Args:
            features: 候选值特征。

        Returns:
            float: 排序分。
        """
        return 0.0
