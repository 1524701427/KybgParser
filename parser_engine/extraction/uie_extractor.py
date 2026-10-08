"""UIE 抽取器适配器。"""

from __future__ import annotations

import re
import gc
from collections import defaultdict
from typing import Any

from parser_engine.document.ast.evidence import Extraction, FieldEvidence
from parser_engine.core.logger import logger


class UIEExtractor:
    """UIE 抽取器。

    UIE 只用于候选文本增强抽取，不扫全文，也不直接决定最终 JSON。
    """

    NUMBER_UNIT_PATTERN = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z%/·\u4e00-\u9fa5-]+)?")

    def __init__(
        self,
        enabled: bool = False,
        mode: str = "shadow",
        model_name: str = "uie-base",
        threshold: float = 0.65,
        max_text_length: int = 512,
        batch_size: int = 4,
        release_after_extract: bool = True,
    ):
        """初始化 UIE 抽取器。

        Args:
            enabled: 是否启用。
            mode: 运行模式，支持 active/shadow/disabled。
            model_name: PaddleNLP UIE 模型名称或本地路径。
            threshold: UIE 置信度阈值。
            max_text_length: 送入 UIE 的候选文本最大长度。
            batch_size: 同一字段 schema 下批量送入 UIE 的文本数量。
            release_after_extract: UIE 批量抽取结束后是否释放模型。
        """
        self.enabled = enabled
        self.mode = mode
        self.model_name = model_name
        self.threshold = threshold
        self.max_text_length = max_text_length
        self.batch_size = max(1, batch_size)
        self.release_after_extract = release_after_extract
        self.model: Any | None = None

    def extract(self, match) -> list[Extraction]:
        """从候选文本中抽取字段值。

        Args:
            match: 字段匹配结果。

        Returns:
            list[Extraction]: UIE 抽取结果。
        """
        if not self.enabled or self.model is None:
            if self.enabled and self.model is None:
                self._load_model()
            if not self.enabled or self.model is None:
                return []
        if self.mode != "active":
            logger.info("UIEExtractor 当前为 shadow 模式，仅加载模型，不参与最终抽取")
            return []

        schema = self._build_schema(match.candidate.field_config)
        try:
            self.model.set_schema(schema)
            outputs = self.model(match.candidate.text[: self.max_text_length])
        except Exception as exc:
            logger.warning(f"UIE 抽取失败：{exc}")
            return []

        return self._convert_outputs(match, outputs)

    def extract_many(self, matches) -> list[Extraction]:
        """按字段 schema 批量抽取候选，降低 UIE 逐条推理开销。"""
        if not matches:
            return []
        if not self.enabled or self.model is None:
            if self.enabled and self.model is None:
                self._load_model()
            if not self.enabled or self.model is None:
                return []
        if self.mode != "active":
            logger.info("UIEExtractor 当前为 shadow 模式，仅加载模型，不参与最终抽取")
            return []

        grouped = defaultdict(list)
        for match in matches:
            schema = tuple(self._build_schema(match.candidate.field_config))
            grouped[schema].append(match)

        results: list[Extraction] = []
        for schema, schema_matches in grouped.items():
            self.model.set_schema(list(schema))
            for start in range(0, len(schema_matches), self.batch_size):
                batch = schema_matches[start : start + self.batch_size]
                results.extend(self._extract_batch_with_retry(batch, self.batch_size))
        return results

    def _extract_batch_with_retry(self, matches, batch_size: int) -> list[Extraction]:
        """批量 UIE 抽取，遇到内存错误自动拆小批次。"""
        if not matches:
            return []
        current_size = min(max(1, batch_size), len(matches))
        results: list[Extraction] = []
        index = 0
        while index < len(matches):
            batch = matches[index : index + current_size]
            texts = [match.candidate.text[: self.max_text_length] for match in batch]
            try:
                outputs = self.model(texts if len(texts) > 1 else texts[0])
            except RuntimeError as exc:
                if current_size == 1 or not self._is_memory_error(exc):
                    logger.warning(f"UIE 批量抽取失败：{exc}")
                    index += current_size
                    continue
                gc.collect()
                current_size = max(1, current_size // 2)
                logger.warning(f"UIE 内存不足，自动降低 batch_size 到 {current_size} 后重试")
                continue
            except Exception as exc:
                logger.warning(f"UIE 批量抽取失败：{exc}")
                index += current_size
                continue

            normalized_outputs = outputs if isinstance(outputs, list) else [outputs]
            for match, output in zip(batch, normalized_outputs, strict=False):
                results.extend(self._convert_outputs(match, [output]))
            index += current_size
        return results

    def _load_model(self) -> None:
        """加载 PaddleNLP UIE 模型。"""
        try:
            import torch  # noqa: F401
            from paddlenlp import Taskflow  # type: ignore
        except Exception as exc:
            logger.warning(f"未安装 paddlenlp/paddlepaddle，UIE 抽取器保持关闭：{exc}")
            self.enabled = False
            return
        logger.info(f"正在加载 UIE 模型：{self.model_name}")
        self.model = Taskflow("information_extraction", schema=["字段值"], model=self.model_name)
        logger.info("UIE 模型加载完成")

    def release_model(self) -> None:
        """释放 UIE 模型占用的内存。"""
        self.model = None
        gc.collect()

    def _build_schema(self, field_config: dict) -> list[str]:
        """根据字段配置构建 UIE schema。

        Args:
            field_config: 字段配置。

        Returns:
            list[str]: UIE schema。
        """
        schema = [field_config.get("name", "字段值")]
        schema.extend((field_config.get("aliases") or [])[:3])
        return list(dict.fromkeys(item for item in schema if item))

    def _convert_outputs(self, match, outputs: list[dict]) -> list[Extraction]:
        """将 UIE 输出转换为统一抽取对象。

        Args:
            match: 字段匹配结果。
            outputs: UIE 原始输出。

        Returns:
            list[Extraction]: 统一抽取结果。
        """
        if not outputs:
            return []
        first_output = outputs[0]
        results: list[Extraction] = []
        for schema_name, items in first_output.items():
            for item in items or []:
                probability = float(item.get("probability", 0.0))
                if probability < self.threshold:
                    continue
                raw_value = item.get("text", "")
                value, unit = self._split_number_unit(raw_value, match.candidate.field_config)
                evidence = FieldEvidence(
                    source_type=match.candidate.source_type,
                    text=match.candidate.text,
                    score=match.score + probability,
                    block_id=match.candidate.block_id,
                    table_id=match.candidate.table_id,
                    page=match.candidate.page,
                    section_path=match.candidate.section_path.copy(),
                    match_method=f"{match.method}+uie",
                    meta={"schema_name": schema_name, "uie_probability": probability},
                )
                results.append(
                    Extraction(
                        field_code=match.candidate.field_code,
                        field_name=match.candidate.field_name,
                        raw_value=raw_value,
                        value=value,
                        unit=unit,
                        score=match.score + min(probability, 0.9),
                        method="uie",
                        evidence=evidence,
                        debug={"schema_name": schema_name, "uie_probability": probability},
                    )
                )
        return results

    def _split_number_unit(self, raw_value: str, field_config: dict | None = None) -> tuple[str, str | None]:
        """从 UIE 文本中拆出数值和单位。

        Args:
            raw_value: UIE 抽出的文本。
            field_config: 字段配置，用于限制允许的单位。

        Returns:
            tuple[str, str | None]: 数值文本和单位。
        """
        found = self.NUMBER_UNIT_PATTERN.search(raw_value)
        if not found:
            return raw_value, None
        value = found.group(1)
        unit = self._match_unit_alias(raw_value[found.end(1) :], field_config or {})
        return value, unit

    def _match_unit_alias(self, text: str, field_config: dict) -> str | None:
        """只从字段配置允许的单位别名中识别单位。"""
        stripped = text.strip()
        unit_aliases = list(field_config.get("unit_aliases") or [])
        standard_unit = field_config.get("standard_unit")
        if standard_unit:
            unit_aliases.append(standard_unit)
        for unit in sorted(set(unit_aliases), key=len, reverse=True):
            if stripped.startswith(unit):
                return unit
        return None

    def _is_memory_error(self, exc: RuntimeError) -> bool:
        """判断 UIE/Paddle 异常是否为内存不足。"""
        message = str(exc).lower()
        return any(keyword in message for keyword in ["out of memory", "not enough memory", "bad allocation", "memory"])
