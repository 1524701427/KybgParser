"""BGE/Embedding 匹配器适配器。"""

from __future__ import annotations

import gc
import ctypes
import os
from functools import lru_cache
from typing import Any

from parser_engine.core.logger import logger


class BgeEmbeddingMatcher:
    """BGE 字段语义匹配器。

    该模块只做“候选文本像不像某个字段”的语义打分，不负责抽字段值。
    """

    def __init__(
        self,
        model_name: str | None = None,
        enabled: bool = False,
        threshold: float = 0.72,
        max_text_length: int = 256,
        batch_size: int = 8,
        memory_aware: bool = True,
        memory_safety_ratio: float = 0.25,
        min_free_memory_mb: int = 1024,
        release_after_match: bool = True,
    ):
        """初始化 BGE 匹配器。

        Args:
            model_name: 模型名称或本地路径。
            enabled: 是否启用真实向量模型。
            threshold: 相似度阈值，低于该阈值不加分。
            max_text_length: 候选文本最大长度，避免长段落拖慢编码。
            batch_size: 批量编码大小，避免逐条调用模型导致大文档很慢。
            memory_aware: 是否根据当前可用内存动态降低实际批次。
            memory_safety_ratio: 可用内存中允许本次编码使用的比例。
            min_free_memory_mb: 编码时尽量保留的空闲物理内存。
            release_after_match: BGE 匹配结束后是否释放模型内存。
        """
        self.model_name = model_name or "BAAI/bge-base-zh-v1.5"
        self.enabled = enabled
        self.threshold = threshold
        self.max_text_length = max_text_length
        self.batch_size = batch_size
        self.memory_aware = memory_aware
        self.memory_safety_ratio = memory_safety_ratio
        self.min_free_memory_bytes = min_free_memory_mb * 1024 * 1024
        self.release_after_match = release_after_match
        self.model: Any | None = None
        self.loaded = False
        # 延迟加载：避免在 Aspose 读取大型 doc 前先占用数百 MB 内存。

    def score(self, candidate) -> float:
        """计算字段与候选文本的语义分。

        Args:
            candidate: 字段候选。

        Returns:
            float: 语义加分。未启用模型或低于阈值时返回 0。
        """
        return self.score_many([candidate])[0]

    def score_many(self, candidates: list) -> list[float]:
        """批量计算字段与候选文本的语义分。"""
        if not candidates:
            return []
        if not self.enabled:
            return [0.0] * len(candidates)
        if self.model is None:
            self._load_model()
        if self.model is None:
            return [0.0] * len(candidates)

        field_texts = [self._build_field_text(candidate.field_config) for candidate in candidates]
        candidate_texts = [candidate.text[: self.max_text_length] for candidate in candidates]
        try:
            similarities = self._cosine_similarities(field_texts, candidate_texts)
        except RuntimeError as exc:
            if not self._is_memory_error(exc):
                raise
            logger.warning("BGE 内存不足，本轮语义匹配自动跳过，后续继续执行规则抽取和 UIE")
            self._release_model(disable=True)
            return [0.0] * len(candidates)

        scores: list[float] = []
        for candidate, similarity in zip(candidates, similarities, strict=True):
            candidate.meta["bge_similarity"] = similarity

            if similarity < self.threshold:
                scores.append(0.0)
                continue
            # BGE 只作为补充分，不允许压过 alias 和章节规则。
            scores.append(min((similarity - self.threshold) * 1.5, 0.35))
        return scores

    def _load_model(self) -> None:
        """加载向量模型。"""
        try:
            import torch  # noqa: F401
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            logger.warning(f"未安装 sentence-transformers，BGE 匹配器保持关闭：{exc}")
            self.enabled = False
            return
        gc.collect()
        logger.info(f"正在加载 BGE 模型：{self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        if hasattr(self.model, "max_seq_length"):
            self.model.max_seq_length = min(int(self.model.max_seq_length), self.max_text_length)
        self.loaded = True
        logger.info("BGE 模型加载完成")

    def _release_model(self, disable: bool = False) -> None:
        """释放 BGE 模型占用的内存。"""
        self.model = None
        self.loaded = False
        if disable:
            self.enabled = False
        self._encode_text.cache_clear()
        gc.collect()

    def _build_field_text(self, field_config: dict) -> str:
        """构建字段语义描述。

        Args:
            field_config: 字段配置。

        Returns:
            str: 字段名、别名和单位组合后的描述文本。
        """
        parts = [field_config.get("name", "")]
        parts.extend(field_config.get("aliases") or [])
        standard_unit = field_config.get("standard_unit")
        if standard_unit:
            parts.append(f"单位 {standard_unit}")
        return "；".join(part for part in parts if part)

    @lru_cache(maxsize=1024)
    def _encode_text(self, text: str):
        """编码文本并缓存向量。

        Args:
            text: 待编码文本。

        Returns:
            Any: 归一化后的向量。
        """
        return self.model.encode(text, normalize_embeddings=True)

    def _encode_texts(self, texts: list[str]):
        """批量编码文本。"""
        if not texts:
            return []
        if len(texts) == 1:
            return [self._encode_text(texts[0])]
        vectors = []
        index = 0
        batch_size = self._select_batch_size(texts, log=True)
        logger.info(f"BGE 实际编码 batch_size={batch_size}")
        while index < len(texts):
            batch_size = min(batch_size, self._select_batch_size(texts[index:]))
            current_size = min(batch_size, len(texts) - index)
            batch = texts[index : index + current_size]
            try:
                batch_vectors = self._encode_batch(batch, current_size)
            except RuntimeError as exc:
                if not self._is_memory_error(exc) or current_size == 1:
                    raise
                gc.collect()
                batch_size = max(1, current_size // 2)
                logger.warning(f"BGE 编码内存不足，自动降低 batch_size 到 {batch_size} 后重试")
                continue
            vectors.extend(batch_vectors)
            index += current_size
        return vectors

    def _select_batch_size(self, texts: list[str], log: bool = False) -> int:
        """根据配置上限、当前可用内存和文本长度选择实际编码批次。"""
        configured_size = max(1, self.batch_size)
        if not self.memory_aware:
            return configured_size

        available_bytes = self._available_memory_bytes()
        if available_bytes is None:
            return configured_size

        usable_bytes = max(0, available_bytes - self.min_free_memory_bytes)
        usable_bytes = int(usable_bytes * self.memory_safety_ratio)
        if usable_bytes <= 0:
            logger.warning("BGE 编码前可用内存低于保留阈值，实际 batch_size 降为 1")
            return 1

        per_text_bytes = max(1, self._estimate_encode_memory_bytes(texts))
        dynamic_size = max(1, usable_bytes // per_text_bytes)
        selected_size = min(configured_size, dynamic_size, len(texts))
        if log:
            logger.info(
                "BGE 内存感知批次："
                f"可用内存={available_bytes // 1024 // 1024}MB，"
                f"保留={self.min_free_memory_bytes // 1024 // 1024}MB，"
                f"估算单条={per_text_bytes // 1024 // 1024}MB，"
                f"配置上限={configured_size}，实际={selected_size}"
            )
        return max(1, selected_size)

    def _estimate_encode_memory_bytes(self, texts: list[str]) -> int:
        """按模型规模和样本文本长度粗略估算单条编码峰值内存。"""
        sample = texts[: min(len(texts), 32)]
        avg_chars = sum(len(text) for text in sample) / max(1, len(sample))
        token_count = min(self.max_text_length, max(16, int(avg_chars * 1.15) + 8))

        config = self._model_config()
        hidden_size = int(getattr(config, "hidden_size", 768))
        num_layers = int(getattr(config, "num_hidden_layers", 12))
        num_heads = int(getattr(config, "num_attention_heads", 12))
        intermediate_size = int(getattr(config, "intermediate_size", hidden_size * 4))

        bytes_per_float = 4
        hidden_bytes = token_count * hidden_size * bytes_per_float
        intermediate_bytes = token_count * intermediate_size * bytes_per_float
        attention_bytes = num_heads * token_count * token_count * bytes_per_float
        per_layer_bytes = hidden_bytes * 6 + intermediate_bytes * 2 + attention_bytes
        return int(per_layer_bytes * num_layers)

    def _model_config(self):
        """获取底层 Transformer 配置，取不到时返回 None 并使用默认 BGE-base 参数。"""
        try:
            module = self.model._first_module()
        except Exception:
            return None
        auto_model = getattr(module, "auto_model", None)
        return getattr(auto_model, "config", None)

    def _available_memory_bytes(self) -> int | None:
        """读取当前系统可用物理内存。"""
        if os.name == "nt":
            return self._available_memory_bytes_windows()
        if hasattr(os, "sysconf"):
            try:
                pages = os.sysconf("SC_AVPHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return int(pages * page_size)
            except (OSError, ValueError):
                return None
        return None

    def _available_memory_bytes_windows(self) -> int | None:
        """通过 Windows API 读取可用物理内存。"""

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            success = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        except Exception:
            return None
        if not success:
            return None
        return int(status.ullAvailPhys)

    def _encode_batch(self, texts: list[str], batch_size: int):
        """调用模型编码一个小批次，兼容旧版 sentence-transformers 参数。"""
        try:
            return self.model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=batch_size,
                show_progress_bar=False,
            )
        except TypeError:
            return self.model.encode(texts, normalize_embeddings=True)

    def _is_memory_error(self, exc: RuntimeError) -> bool:
        """判断 Torch 编码异常是否为内存不足。"""
        message = str(exc).lower()
        return any(keyword in message for keyword in ["out of memory", "not enough memory", "defaultcpuallocator"])

    def _cosine_similarity(self, left: str, right: str) -> float:
        """计算余弦相似度。

        Args:
            left: 字段描述文本。
            right: 候选文本。

        Returns:
            float: 余弦相似度。
        """
        left_vector = self._encode_text(left)
        right_vector = self._encode_text(right)
        return float(left_vector @ right_vector)

    def _cosine_similarities(self, left_texts: list[str], right_texts: list[str]) -> list[float]:
        """批量计算多组文本的余弦相似度。"""
        unique_texts = list(dict.fromkeys([*left_texts, *right_texts]))
        logger.info(
            f"BGE 批量编码文本：候选 {len(right_texts)} 条，去重后 {len(unique_texts)} 条，batch_size={self.batch_size}"
        )
        vectors = self._encode_texts(unique_texts)
        vector_by_text = dict(zip(unique_texts, vectors, strict=True))
        return [float(vector_by_text[left] @ vector_by_text[right]) for left, right in zip(left_texts, right_texts, strict=True)]
