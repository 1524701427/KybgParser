"""训练数据集构建。"""

from __future__ import annotations

from pathlib import Path


class TrainingDatasetBuilder:
    """从 Golden JSON 和解析过程日志构建训练数据。"""

    def build_candidate_ranker_dataset(self, golden_dir: str | Path):
        """构建候选排序训练数据。"""
        return []
