"""错误分析工具。"""

from __future__ import annotations


class ErrorAnalyzer:
    """汇总字段错误原因。"""

    def analyze(self, predictions: list[dict], golden: list[dict]) -> dict:
        """分析错误。"""
        return {"message": "错误分析模块已预留，等待 Golden 数据接入"}
