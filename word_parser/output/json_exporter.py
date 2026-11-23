"""将解析上下文导出为业务结果、审计详情和占位符映射 JSON。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from word_parser.logger import logger
from word_parser.application.context import ParseContext
from word_parser.output.detail_fields import DetailFieldsMixin
from word_parser.output.detail_sources import DetailSourcesMixin
from word_parser.output.detail_tables import DetailTablesMixin
from word_parser.output.field_traces import FieldTracesMixin
from word_parser.output.result_builder import ResultBuilder
from word_parser.primary.domain_stage import DomainExtractionState
from word_parser.mapping.projector import mapping_from_detail_json


class JsonExporter(
    DetailFieldsMixin,
    DetailTablesMixin,
    DetailSourcesMixin,
    FieldTracesMixin,
):
    """统一编排三种 JSON 视图，具体组装职责由相邻 mixin 承担。"""

    COLUMN_KEY_FIELD_ALIASES = {
        "hubHeightAvgWindSpeed": "hubHeightAnnualAverageWindSpeed",
        "turbineCapacityKw": "turbineCapacity",
        "ratedVoltage": "collectorVoltageLevel",
        "totalLength": "collectorLineLength",
    }

    def __init__(self, result_builder: ResultBuilder | None = None, output_dir: str | Path = "data/predictions"):
        """初始化导出器，并允许调用方注入共享的结果构建器。"""
        self.result_builder = result_builder or ResultBuilder()
        self.output_dir = Path(output_dir)

    def export(self, ctx: ParseContext, *, defer_mapping: bool = False, prepared: DomainExtractionState | None = None, memory_only: bool = False) -> dict:
        """构建解析结果、写出三个 JSON 文件并返回同一份结果摘要。"""
        logger.info(f"开始导出解析结果：{ctx.file_path}")
        built_result = (self.result_builder.build_prepared(prepared) if prepared is not None
                        else self.result_builder.build(ctx.ast, ctx.validated, file_path=ctx.file_path))
        ctx.result = {
            "filePath": ctx.file_path,
            "sections": self._strip_private_keys(built_result.get("sections", [])),
        }
        detail_json = self._build_detail_json(ctx, built_result)
        mapped_json = {} if defer_mapping else self._build_mapped_json(detail_json)
        result_json = self._build_result_json(ctx)
        if not memory_only:
            self._write_output_files(ctx, detail_json, result_json, mapped_json, write_mapped=not defer_mapping)
        logger.info(f"解析结果组装完成：{self.output_dir} | 内存模式={memory_only}")
        exported = {
            "filePath": ctx.file_path,
            "result": ctx.result,
            "fields": detail_json["fieldIndex"],
            "mapped": mapped_json,
            "debug": detail_json.get("debug", {}),
            "outputFiles": {
                "detail": str(self._output_path(ctx, "details")),
                "result": str(self._output_path(ctx, "result")),
                "mapped": str(self._output_path(ctx, "mapped")),
            },
        }
        if memory_only:
            # Preserve the exact primary detail (including fieldIndex/tableIndex)
            # for the final stage; do not publish interim JSON files.
            exported["_primary_detail"] = self._strip_private_keys(detail_json)
        return exported

    def _map_output_field_codes(self, payload: Any, map_keys: bool = False) -> Any:
        mapping = getattr(self.result_builder, "output_field_codes", {})
        if not mapping:
            return payload
        if isinstance(payload, list):
            return [self._map_output_field_codes(item) for item in payload]
        if not isinstance(payload, dict):
            return payload

        result: dict[str, Any] = {}
        for key, value in payload.items():
            output_key = mapping.get(key, key) if map_keys else key
            if key in {"fieldCode", "key"} and isinstance(value, str):
                result[output_key] = mapping.get(value, value)
            elif key == "fieldCodes" and isinstance(value, list):
                result[output_key] = [mapping.get(code, code) for code in value]
            else:
                result[output_key] = self._map_output_field_codes(
                    value,
                    map_keys=key in {"fieldIndex", "tableIndex"},
                )
        return result

    def _build_mapped_json(self, detail_json: dict[str, Any]) -> dict[str, Any]:
        """按配置生成 `${...}` 键完整、允许空值的对接 JSON。"""
        return mapping_from_detail_json(detail_json, self.result_builder)

    def _build_result_json(self, ctx: ParseContext) -> dict:
        """生成不含调试私有字段的业务章节结果。"""
        return {
            "filePath": ctx.result.get("filePath", ctx.file_path),
            "sections": self._strip_private_keys(ctx.result.get("sections", [])),
        }

    def _strip_private_keys(self, value: Any) -> Any:
        """递归移除内部键，并将常见标量转换为 JSON 可序列化值。"""
        if isinstance(value, dict):
            return {key: self._strip_private_keys(item) for key, item in value.items() if not str(key).startswith("_")}
        if isinstance(value, list):
            return [self._strip_private_keys(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return self._strip_private_keys(item())
            except (TypeError, ValueError):
                pass
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                return self._strip_private_keys(tolist())
            except (TypeError, ValueError):
                pass
        return value

    def _write_output_files(self, ctx: ParseContext, detail_json: dict, result_json: dict, mapped_json: dict, *, write_mapped: bool = True) -> None:
        """使用 UTF-8 将详情、业务结果和映射结果写入输出目录。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path(ctx, "details").write_text(
            json.dumps(self._strip_private_keys(detail_json), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._output_path(ctx, "result").write_text(
            json.dumps(self._strip_private_keys(result_json), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if write_mapped:
            self._output_path(ctx, "mapped").write_text(
                json.dumps(self._strip_private_keys(mapped_json), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _output_path(self, ctx: ParseContext, suffix: str) -> Path:
        """根据输入文件名生成跨平台安全的输出路径。"""
        stem = Path(ctx.file_path).stem or "parse_result"
        safe_stem = "".join(char if char not in '<>:"/\\|?*' else "_" for char in stem)
        return self.output_dir / f"{safe_stem}_{suffix}.json"
