"""非 LLM 语义验证器：Reranker + NLI。"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

from parser_engine.document.ast.evidence import Extraction
from parser_engine.core.logger import logger


class OnnxReranker:
    """ONNX CrossEncoder 风格 reranker 包装。"""

    def __init__(self, session, tokenizer, max_length: int = 256):
        self.session = session
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.input_names = {item.name for item in session.get_inputs()}

    def predict(self, pairs, batch_size: int = 4):
        """返回每个 query/passage pair 的相关性分数。"""
        import numpy as np

        scores = []
        for start in range(0, len(pairs), max(1, batch_size)):
            batch = pairs[start : start + max(1, batch_size)]
            queries = [item[0] for item in batch]
            passages = [item[1] for item in batch]
            inputs = self.tokenizer(
                queries,
                passages,
                return_tensors="np",
                truncation=True,
                max_length=self.max_length,
                padding=True,
            )
            feed = {}
            for name, value in inputs.items():
                if name not in self.input_names:
                    continue
                if hasattr(value, "dtype") and getattr(value.dtype, "kind", None) in {"i", "u"} and value.dtype != np.int64:
                    value = value.astype(np.int64, copy=False)
                feed[name] = value
            outputs = self.session.run(None, feed)[0]
            array = np.asarray(outputs)
            if array.ndim == 2 and array.shape[1] == 1:
                array = array[:, 0]
            elif array.ndim == 2:
                array = array[:, -1]
            scores.extend(float(item) for item in array.reshape(-1))
        return scores


class SemanticVerifier:
    """使用非生成式模型验证候选值和证据的一致性。"""

    def __init__(
        self,
        field_configs: dict[str, dict],
        enabled: bool = True,
        reranker_enabled: bool = False,
        reranker_model_name: str | None = None,
        reranker_backend: str = "cross_encoder",
        reranker_weight: float = 0.6,
        nli_enabled: bool = False,
        nli_model_name: str | None = None,
        nli_weight: float = 0.8,
        release_after_verify: bool = True,
        batch_size: int = 16,
    ):
        """初始化语义验证器。"""
        self.field_configs = field_configs
        self.enabled = enabled
        self.reranker_enabled = reranker_enabled
        self.reranker_model_name = reranker_model_name
        self.reranker_backend = reranker_backend
        self.reranker_weight = reranker_weight
        self.nli_enabled = nli_enabled
        self.nli_model_name = nli_model_name
        self.nli_weight = nli_weight
        self.release_after_verify = release_after_verify
        self.batch_size = max(1, batch_size)
        self.reranker_model: Any | None = None
        self.nli_tokenizer: Any | None = None
        self.nli_model: Any | None = None

    def verify(self, extractions: list[Extraction]) -> list[Extraction]:
        """对候选抽取结果追加 Reranker/NLI 语义验证分。"""
        extractions = self.verify_reranker(extractions)
        return self.verify_nli(extractions)

    def verify_reranker(self, extractions: list[Extraction]) -> list[Extraction]:
        """对候选追加 Cross-Encoder Reranker 相关性分。"""
        if not self.enabled:
            return extractions

        reranker_count = 0
        if self.reranker_enabled:
            scores = self._reranker_scores(extractions)
            for extraction, reranker_score in zip(extractions, scores, strict=True):
                if reranker_score is None:
                    continue
                reranker_count += 1
                extraction.score += self._centered_score(reranker_score) * self.reranker_weight
                extraction.debug["reranker_score"] = reranker_score

        if self.release_after_verify:
            self._release_reranker()
        logger.info(f"Reranker 语义验证完成：{reranker_count} 条")
        return extractions

    def verify_nli(self, extractions: list[Extraction]) -> list[Extraction]:
        """对候选追加 NLI 支持性验证分。"""
        if not self.enabled:
            return extractions

        nli_count = 0
        if self.nli_enabled:
            nli_results = self._nli_scores(extractions)
            for extraction, nli in zip(extractions, nli_results, strict=True):
                if nli is None:
                    continue
                nli_count += 1
                label, score = nli
                extraction.score += self._nli_delta(label, score)
                extraction.debug["nli_label"] = label
                extraction.debug["nli_score"] = score

        if self.release_after_verify:
            self._release_nli()
        logger.info(f"NLI 语义验证完成：{nli_count} 条")
        return extractions

    def _reranker_score(self, extraction: Extraction) -> float | None:
        """计算 Cross-Encoder Reranker 相关性分。"""
        return self._reranker_scores([extraction])[0]

    def _reranker_scores(self, extractions: list[Extraction]) -> list[float | None]:
        """批量计算 Cross-Encoder Reranker 相关性分。"""
        if type(self)._reranker_score is not SemanticVerifier._reranker_score:
            return [self._reranker_score(extraction) for extraction in extractions]
        model = self._load_reranker()
        if model is None:
            return [None] * len(extractions)
        pairs: list[tuple[str, str]] = []
        positions: list[int] = []
        scores: list[float | None] = [None] * len(extractions)
        for index, extraction in enumerate(extractions):
            query = self._build_reranker_query(extraction)
            passage = extraction.evidence.text or ""
            if not query or not passage:
                continue
            pairs.append((query, passage))
            positions.append(index)
        if not pairs:
            return scores
        try:
            raw_scores = model.predict(pairs, batch_size=self.batch_size)
        except TypeError:
            raw_scores = model.predict(pairs)
        except Exception as exc:
            logger.warning(f"Reranker 语义验证失败：{exc}")
            return scores
        for position, score in zip(positions, raw_scores, strict=True):
            try:
                scores[position] = float(score)
            except Exception:
                scores[position] = float(score[0])
        return scores

    def _nli_score(self, extraction: Extraction) -> tuple[str, float] | None:
        """计算 NLI 支持性标签和分数。"""
        return self._nli_scores([extraction])[0]

    def _nli_scores(self, extractions: list[Extraction]) -> list[tuple[str, float] | None]:
        """批量计算 NLI 支持性标签和分数。"""
        if type(self)._nli_score is not SemanticVerifier._nli_score:
            return [self._nli_score(extraction) for extraction in extractions]
        model_pair = self._load_nli()
        if model_pair is None:
            return [None] * len(extractions)
        tokenizer, model = model_pair
        pairs: list[tuple[str, str]] = []
        positions: list[int] = []
        results: list[tuple[str, float] | None] = [None] * len(extractions)
        for index, extraction in enumerate(extractions):
            premise = extraction.evidence.text or ""
            hypothesis = self._build_nli_hypothesis(extraction)
            if not premise or not hypothesis:
                continue
            pairs.append((premise, hypothesis))
            positions.append(index)
        if not pairs:
            return results
        try:
            import torch

            current_batch_size = self.batch_size
            start = 0
            while start < len(pairs):
                batch = pairs[start : start + current_batch_size]
                try:
                    batch_results = self._nli_score_batch(tokenizer, model, batch)
                except RuntimeError as exc:
                    if current_batch_size == 1 or not self._is_memory_error(exc):
                        raise
                    current_batch_size = max(1, current_batch_size // 2)
                    logger.warning(f"NLI 内存不足，自动降低 batch_size 到 {current_batch_size} 后重试")
                    continue
                for offset, item in enumerate(batch_results):
                    results[positions[start + offset]] = item
                start += current_batch_size
            return results
        except Exception as exc:
            logger.warning(f"NLI 语义验证失败：{exc}")
            return results

    def _nli_score_batch(self, tokenizer, model, batch: list[tuple[str, str]]) -> list[tuple[str, float]]:
        """计算一个 NLI 小批次。"""
        import torch

        premises = [item[0] for item in batch]
        hypotheses = [item[1] for item in batch]
        inputs = tokenizer(premises, hypotheses, return_tensors="pt", truncation=True, max_length=512, padding=True)
        device = next(model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)
        results = []
        for row in probs:
            best_index = int(torch.argmax(row).item())
            label = model.config.id2label.get(best_index, str(best_index)).lower()
            results.append((label, float(row[best_index].item())))
        return results

    def _is_memory_error(self, exc: RuntimeError) -> bool:
        """判断模型推理异常是否为内存不足。"""
        message = str(exc).lower()
        return any(keyword in message for keyword in ["out of memory", "not enough memory", "defaultcpuallocator", "bad allocation"])

    def _load_reranker(self):
        """延迟加载 Cross-Encoder Reranker。"""
        if self.reranker_model is not None:
            return self.reranker_model
        if not self.reranker_model_name:
            return None
        if self.reranker_backend == "onnx":
            logger.info(f"正在加载 Reranker 模型：{self.reranker_model_name}")
            self._log_model_file_size(self.reranker_model_name, "Reranker")
            return self._load_onnx_reranker()
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception as exc:
            logger.warning(f"未安装 sentence-transformers，Reranker 语义验证保持关闭：{exc}")
            self.reranker_enabled = False
            return None
        logger.info(f"正在加载 Reranker 模型：{self.reranker_model_name}")
        self._log_model_file_size(self.reranker_model_name, "Reranker")
        try:
            self.reranker_model = CrossEncoder(
                self.reranker_model_name,
                max_length=256,
                automodel_args={"local_files_only": True},
                tokenizer_args={"local_files_only": True},
            )
        except TypeError:
            self.reranker_model = CrossEncoder(self.reranker_model_name, max_length=256)
        logger.info("Reranker 模型加载完成")
        return self.reranker_model

    def _load_onnx_reranker(self):
        """优先使用 ONNX Reranker，避免加载 CrossEncoder 大权重导致进程被杀。"""
        model_dir = Path(self.reranker_model_name or "")
        onnx_path = model_dir / "onnx" / "model.onnx"
        if not onnx_path.exists():
            logger.warning(f"未找到 Reranker ONNX 模型，跳过 Reranker：{onnx_path}")
            self.reranker_enabled = False
            return None
        try:
            import onnxruntime as ort  # type: ignore
            from transformers import AutoTokenizer  # type: ignore
        except Exception as exc:
            logger.warning(f"ONNX Reranker 依赖不可用，跳过 Reranker：{exc}")
            self.reranker_enabled = False
            return None
        logger.info(f"正在加载 ONNX Reranker：{onnx_path}")
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        session = ort.InferenceSession(str(onnx_path), sess_options=session_options, providers=["CPUExecutionProvider"])
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        self.reranker_model = OnnxReranker(session=session, tokenizer=tokenizer, max_length=256)
        logger.info("ONNX Reranker 加载完成")
        return self.reranker_model

    def _log_model_file_size(self, model_name: str | None, label: str) -> None:
        """记录本地模型权重大小，便于判断加载阶段耗时。"""
        if not model_name:
            return
        path = Path(model_name)
        if not path.exists():
            return
        candidates = [path / "model.safetensors", path / "pytorch_model.bin"]
        for file_path in candidates:
            if file_path.exists():
                size_mb = file_path.stat().st_size / 1024 / 1024
                logger.info(f"{label} 本地权重文件：{file_path.name}，大小 {size_mb:.1f}MB")
                return

    def _load_nli(self):
        """延迟加载 NLI 模型。"""
        if self.nli_model is not None and self.nli_tokenizer is not None:
            return self.nli_tokenizer, self.nli_model
        if not self.nli_model_name:
            return None
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        except Exception as exc:
            logger.warning(f"未安装 transformers，NLI 语义验证保持关闭：{exc}")
            self.nli_enabled = False
            return None
        logger.info(f"正在加载 NLI 模型：{self.nli_model_name}")
        self.nli_tokenizer = AutoTokenizer.from_pretrained(self.nli_model_name)
        self.nli_model = AutoModelForSequenceClassification.from_pretrained(self.nli_model_name)
        self.nli_model.eval()
        logger.info("NLI 模型加载完成")
        return self.nli_tokenizer, self.nli_model

    def _build_reranker_query(self, extraction: Extraction) -> str:
        """构造 Reranker 查询，包含字段、原始候选值和单位。"""
        value_text = str(extraction.raw_value or extraction.value or "").strip()
        unit = extraction.unit or ""
        return f"{extraction.field_name}：{value_text}{unit}".strip()

    def _build_nli_hypothesis(self, extraction: Extraction) -> str:
        """构造 NLI 声明，使用归一化值和单位。"""
        value_text = str(extraction.value or extraction.raw_value or "").strip()
        unit = extraction.unit or ""
        if not value_text:
            return ""
        return f"该项目的{extraction.field_name}为{value_text}{unit}。"

    def _centered_score(self, score: float) -> float:
        """将 0-1 分数居中；非概率分数只保留正负方向。"""
        if 0.0 <= score <= 1.0:
            return score - 0.5
        return max(min(score, 1.0), -1.0) * 0.5

    def _nli_delta(self, label: str, score: float) -> float:
        """将 NLI 标签转成候选加减分。"""
        normalized = label.lower()
        if "entail" in normalized or "support" in normalized or normalized in {"0", "label_0"}:
            return score * self.nli_weight
        if "contrad" in normalized:
            return -score * self.nli_weight
        return -0.15 * score

    def _release_models(self) -> None:
        """释放语义验证模型内存。"""
        self._release_reranker()
        self._release_nli()
        gc.collect()

    def _release_reranker(self) -> None:
        """释放 Reranker 模型内存。"""
        self.reranker_model = None

    def _release_nli(self) -> None:
        """释放 NLI 模型内存。"""
        self.nli_tokenizer = None
        self.nli_model = None