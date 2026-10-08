"""标题识别模型适配器。"""

from __future__ import annotations


class SklearnHeadingClassifier:
    """sklearn 标题分类器占位实现。"""

    def __init__(self, enabled: bool = False, mode: str = "shadow"):
        """初始化标题分类器。

        Args:
            enabled: 是否启用真实模型。
            mode: 运行模式，支持 active/shadow/disabled。
        """
        self.enabled = enabled
        self.mode = mode
        self.model = None

    def predict(self, features: dict) -> dict:
        """预测段落结构类型。

        Args:
            features: 段落文本、字号、加粗、编号等特征。

        Returns:
            dict: 预测结果。
        """
        return {"label": "UNKNOWN", "score": 0.0, "mode": self.mode}
