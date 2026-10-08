"""Result schema configuration and existing fallback definitions.

These methods share ResultBuilder state during the compatibility migration.
Rule bodies and call order are preserved.
"""

from __future__ import annotations

from copy import deepcopy

from pathlib import Path

from typing import Any

from word_parser.config.loader import ConfigLoader

from word_parser.config.output_schema import field_meta_from_config as configured_field_meta, section_schema_from_config as configured_section_schema


class ResultSchemaMixin:
    def _load_output_schema(self, config_root: str | Path) -> dict[str, Any]:
        return ConfigLoader(config_root).load_yaml("output_schema.yaml")

    def _configure_output_schema(self, schema: dict[str, Any]) -> None:
        self.section_order = list(schema.get("section_order") or self.SECTION_ORDER)
        self.required_section_schema = self._section_schema_from_config(schema.get("sections")) or self._default_section_schema()
        self.common_section_fields = set(schema.get("common_section_fields") or self.COMMON_SECTION_FIELDS)
        self.detail_tables = deepcopy(schema.get("detail_tables") or self.DETAIL_TABLES)
        self.table_output_headers = self._table_output_headers_from_config(schema.get("table_outputs") if "table_outputs" in schema else None)
        self.required_field_meta = self._field_meta_from_config(schema.get("fields"))
        self.required_table_schemas = self._required_table_schemas_from_config(schema.get("table_outputs") if "table_outputs" in schema else None)
        if "original_table_groups" in schema:
            self.original_table_group_specs = list(schema.get("original_table_groups") or [])
        elif "original_tables" in schema:
            self.original_table_group_specs = []
        else:
            self.original_table_group_specs = self._default_original_table_group_specs()
        self.original_table_specs = list(schema.get("original_tables") or []) if "original_tables" in schema else []
        self.repeatable_original_table_specs = list(schema.get("repeatable_original_tables") or [])
        self.combined_table_specs = list(schema["combined_tables"] if "combined_tables" in schema else self._default_combined_table_specs())
        self.combined_detail_field_specs = self._load_combined_detail_field_specs(schema.get("combined_detail_field_mappings"))
        self.resource_table_key_specs = self._load_table_key_specs(
            schema.get("resource_table_key_patterns"),
            self._default_resource_table_key_specs_config(),
        )
        self.electrical_secondary_table_key_specs = self._load_table_key_specs(
            schema.get("electrical_secondary_table_key_patterns"),
            self._default_electrical_secondary_table_key_specs_config(),
        )
        self.generation_text_field_specs = self._load_generation_text_field_specs(schema.get("generation_text_fields"))
        self.wind_resource_direction_table_specs = list(schema.get("wind_resource_direction_table_rules") or [])

    def _section_schema_from_config(self, sections: Any) -> dict[str, dict[str, list[str]]]:
        return configured_section_schema(sections)

    def _default_section_schema(self) -> dict[str, dict[str, list[str]]]:
        """返回由 output_schema.yaml 生成的默认章节结构。"""
        return deepcopy(self.REQUIRED_SECTION_SCHEMA)

    def _table_output_headers_from_config(self, table_outputs: Any) -> dict[str, dict[str, Any]]:
        result = deepcopy(self.TABLE_OUTPUT_HEADERS)
        if not isinstance(table_outputs, dict):
            return result
        for key, spec in table_outputs.items():
            if not isinstance(spec, dict):
                continue
            headers = spec.get("headers") or []
            default = result.get(key, {})
            result[key] = {"name": spec.get("name") or default.get("name") or key, "headers": headers}
        return result

    def _required_table_schemas_from_config(self, table_outputs: Any) -> dict[str, tuple[str, list[tuple[str, str]]]]:
        result = deepcopy(self.REQUIRED_TABLE_SCHEMAS)
        if not isinstance(table_outputs, dict):
            return result
        for key, spec in table_outputs.items():
            if not isinstance(spec, dict):
                continue
            headers = [(str(item.get("key")), str(item.get("name"))) for item in (spec.get("headers") or []) if isinstance(item, dict) and item.get("key")]
            default_name = result.get(key, (key, []))[0]
            result[key] = (str(spec.get("name") or default_name or key), headers)
        return result

    def _field_meta_from_config(self, fields: Any) -> dict[str, tuple[str, str | None]]:
        result = deepcopy(self.REQUIRED_FIELD_META)
        result.update(configured_field_meta(fields))
        return result

    def _merge_field_meta_from_field_configs(self) -> None:
        for code, config in self.field_configs.items():
            name = config.get("name") or code
            unit = config.get("standard_unit") or config.get("unit")
            self.required_field_meta.setdefault(code, (str(name), unit))

    def _default_original_table_group_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "key_prefix": "resourceOriginalTable",
                "name": "资源章节原表",
                "title_only": True,
                "patterns": [
                    r"测风塔.*基本情况",
                    r"风切变指数(?:计算成果|统计)?表",
                    r"(?:平均风速|风速).*风功率密度",
                    r"扇区.*(?:风向|风能).*分布",
                    r"湍流(?:强度)?(?:统计结果|计算成果|比较)?表",
                    r"[A-Za-z0-9]+#.*测风塔.*(?:风能参数统计成果表|各高度风能参数|风切变指数|切变统计表|湍流)",
                ],
            },
            {
                "key_prefix": "generationOriginalTable",
                "name": "发电量章节原表",
                "title_only": True,
                "patterns": [
                    r"风电场工程.*(?:推荐方案)?(?:发电量|年上网电量)计算(?:成果)?表",
                    r"风电场发电量计算成果表",
                    r"推荐机型单机发电量统计表",
                    r"单台风机年上网电量计算成果表",
                ],
                "exclude_patterns": [r"备选机型", r"5\.3-2[A-Za-z0-9]", r"5\.4-2[A-Za-z0-9]"],
            },
            {
                "key_prefix": "electricalPrimaryOriginalTable",
                "name": "电气一次原表",
                "title_only": True,
                "patterns": [
                    r"110\s*kV\s*升压站本期规模",
                    r"升压站电气一次主要设备材料工程量表",
                    r"主要\s*电气\s*一次\s*设备",
                    r"电气一次.*(?:主要设备|设备材料|材料工程量)",
                ],
            },
            {
                "key_prefix": "electricalSecondaryOriginalTable",
                "name": "电气二次原表",
                "title_only": True,
                "patterns": [
                    r"升压站\s*电气\s*二次\s*主要设备表",
                    r"电气\s*二次\s*主要设备表",
                    r"电气\s*二次\s*设备材料清册表?",
                    r"主要\s*通信\s*设备表",
                    r"通信.*设备表",
                ],
            },
            {
                "key_prefix": "collectorLineOriginalTable",
                "name": "集电线路原表",
                "title_only": True,
                "patterns": [
                    r"电气部分材料清册",
                    r"杆塔部分材料清册",
                    r"基础部分材料清册",
                    r"光缆部分材料清册",
                    r"电缆部分材料清册",
                    r"铁塔接地装置材料",
                    r"集电线路.*(?:主要设备及材料清册|主要设备.*材料清册|设备及材料清册)",
                ],
            },
            {"key_prefix": "substationCivilOriginalTable", "name": "土建升压站原表", "title_only": True, "patterns": [r"升压站\s*主要\s*土建\s*工程量表", r"土建\s*主要\s*工程量表", r"升压站\s*土建\s*清单"]},
            {"key_prefix": "windFoundationOriginalTable", "name": "风机基础原表", "title_only": True, "patterns": [r"基础尺寸及参数表", r"基础断面表"]},
            {"key_prefix": "boxFoundationOriginalTable", "name": "箱变基础原表", "title_only": True, "patterns": [r"箱变基础工程量表", r"箱变基础单台工程量表", r"风电场主要工程量清单"]},
            {"key_prefix": "roadOriginalTable", "name": "道路原表", "title_only": True, "patterns": [r"进站道路.*(?:主要工程数量表|工程数量表|主要工程量表)", r"道路.*主要工程数量表"]},
            {"key_prefix": "landOriginalTable", "name": "用地面积原表", "title_only": True, "patterns": [r"工程永久征地面积汇总表", r"工程临时征地面积汇总表", r"工程征用地计算合计表", r"工程总征地", r"工程面积汇总", r"工程征用地"]},
            {"key_prefix": "earthworkOriginalTable", "name": "土石方平衡原表", "title_only": True, "patterns": [r"场内土石方平衡", r"土石方平衡表"]},
            {"key_prefix": "investmentOriginalTable", "name": "技经概算原表", "title_only": True, "patterns": [r"主要技术经济指标表", r"工程总概算表", r"施工辅助工程概算表", r"设备及安装工程概算表", r"建筑工程概算表", r"其他费用概算表"]},
            {
                "key_prefix": "financeOriginalTable",
                "name": "财务原表",
                "title_only": True,
                "patterns": [
                    r"附表\s*(?:16\.)?1\s*[：:]?\s*财务指标汇总表",
                    r"附表\s*(?:16\.)?2\s*[：:]?\s*项目总投资使用计划与资金筹措表",
                    r"附表\s*(?:16\.)?3\s*[：:]?\s*总成本费用估算表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?4\s*[：:]?\s*资产折旧摊销估算表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?5\s*[：:]?\s*利润与利润分配表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?6\s*[：:]?\s*借款还本付息计划表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?7\s*[：:]?\s*财务计划现金流量表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?8\s*[：:]?\s*项目投资现金流量表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?9\s*[：:]?\s*项目资本金现金流量表(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?10\s*[：:]?\s*投资各方现金流量表[^\n]*投资方\s*1(?:[^\n]*续)?",
                    r"附表\s*(?:16\.)?11\s*[：:]?\s*资产负债表(?:[^\n]*续)?",
                ],
            },
        ]

    def _default_combined_table_specs(self) -> list[dict[str, Any]]:
        return [
            {"builder": "resource_details"},
            {"builder": "collector_line_combined"},
            {"builder": "electrical_primary_details"},
            {"builder": "electrical_secondary_details"},
            {"builder": "substation_civil_combined"},
            {"builder": "road_parameters"},
        ]

    def _load_combined_detail_field_specs(self, specs: Any) -> dict[str, dict[str, Any]]:
        defaults = self._default_combined_detail_field_specs_config()
        if not isinstance(specs, dict):
            return defaults
        result = deepcopy(defaults)
        for detail_key, detail_spec in specs.items():
            if not isinstance(detail_spec, dict):
                continue
            fields = detail_spec.get("fields")
            if not isinstance(fields, dict):
                continue
            key = str(detail_key)
            base = result.get(key, {})
            merged_fields = dict(base.get("fields") or {})
            merged_fields.update({str(code): str(source_key) for code, source_key in fields.items() if code and source_key})
            result[str(detail_key)] = {
                "multi": bool(detail_spec.get("multi", base.get("multi", False))),
                "fields": merged_fields,
            }
        return result

    def _default_combined_detail_field_specs_config(self) -> dict[str, dict[str, Any]]:
        return {
            "windResourceCombined": {
                "multi": True,
                "fields": {
                    "windResourceTowerCodes": "测风塔编号",
                    "windFarmAirDensities": "该风电场的空气密度",
                    "windResourceAirDensities": "高度对应的空气密度",
                    "windResourceAirDensity10m": "10m高度空气密度",
                    "windResourceAirDensity160m": "160m高度空气密度",
                    "hubHeightAnnualAverageWindSpeed": "轮毂高度平均风速m/s",
                    "hubHeightWindPowerDensity": "轮毂高度平均风功率密度W/m²",
                    "windResourceMainWindDirections": "轮毂高度处的主风向",
                    "windResourceSecondaryWindDirections": "轮毂高度处的次风向",
                    "windResourceMainWindEnergyDirections": "轮毂高度处的主风能方向",
                    "windResourceSecondaryWindEnergyDirections": "轮毂高度处的次风能方向",
                    "representativeTurbulenceIntensity": "最大高度处代表性湍流强度",
                    "windShearExponent": "综合风切变",
                    "windResourceGenerationUses": "发电量计算是否使用",
                },
            },
            "electricalPrimaryAccessStationCombined": {
                "fields": {
                    "accessStationName": "accessStationName",
                    "accessibleVoltage": "accessibleVoltage",
                    "accessibleCapacity": "accessibleCapacity",
                },
            },
            "electricalPrimaryMainConnectionCombined": {
                "fields": {
                    "plannedCapacity": "plannedCapacity",
                    "currentCapacity": "currentCapacity",
                    "connectionType": "connectionType",
                },
            },
            "electricalPrimaryLightningRodCombined": {
                "fields": {
                    "independentLightningRodCount": "independentLightningRodCount",
                    "frameLightningRodCount": "frameLightningRodCount",
                },
            },
            "collectorLineCombined": {
                "fields": {
                    "collectorVoltage": "collectorVoltage",
                    "circuitCount": "circuitCount",
                    "newRouteLength": "newRouteLength",
                    "newOverheadLineLength": "newOverheadLineLength",
                    "newSingleCircuitLineLength": "newSingleCircuitLineLength",
                    "newDoubleCircuitLineLength": "newDoubleCircuitLineLength",
                    "newCableLineLength": "newCableLineLength",
                    "totalCollectorRouteLength": "totalCollectorRouteLength",
                    "doubleCircuitOverheadRouteLength": "doubleCircuitOverheadRouteLength",
                    "singleCircuitOverheadRouteLength": "singleCircuitOverheadRouteLength",
                    "boxToTerminalTowerCableRouteLength": "boxToTerminalTowerCableRouteLength",
                    "singleCircuitCableRouteLength": "singleCircuitCableRouteLength",
                    "doubleCircuitCableRouteLength": "doubleCircuitCableRouteLength",
                },
            },
            "substationCivilCombined": {
                "fields": {
                    "totalLandArea": "totalLandArea",
                    "insideWallLandArea": "insideWallLandArea",
                },
            },
            "roadParameters": {
                "fields": {
                    "accessRoadLength": "accessRoadLength",
                    "accessRoadSubgradeWidth": "accessRoadSubgradeWidth",
                    "accessRoadPavementWidth": "accessRoadPavementWidth",
                    "newRoadLength": "newRoadLength",
                    "rebuiltRoadLength": "rebuiltRoadLength",
                    "subgradeWidth": "subgradeWidth",
                    "pavementWidth": "pavementWidth",
                    "siteRoadLength": "siteRoadLength",
                    "maintenanceRoadLength": "maintenanceRoadLength",
                    "maintenanceRoadSubgradeWidth": "maintenanceRoadSubgradeWidth",
                    "maintenanceRoadPavementWidth": "maintenanceRoadPavementWidth",
                },
            },
        }

    def _load_table_key_specs(self, specs: Any, defaults: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = deepcopy(defaults)
        if not isinstance(specs, list):
            return result
        index_by_key = {str(spec.get("key")): index for index, spec in enumerate(result) if spec.get("key")}
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            key = spec.get("key")
            patterns = [str(pattern) for pattern in (spec.get("patterns") or []) if pattern]
            all_patterns = [str(pattern) for pattern in (spec.get("all_patterns") or []) if pattern]
            exclude_patterns = [str(pattern) for pattern in (spec.get("exclude_patterns") or []) if pattern]
            if not key or (not patterns and not all_patterns and not exclude_patterns):
                continue
            key = str(key)
            configured = {
                "key": key,
                "patterns": patterns,
                "all_patterns": all_patterns,
                "exclude_patterns": exclude_patterns,
            }
            if key not in index_by_key and not (patterns or all_patterns):
                continue
            if bool(spec.get("replace_defaults")) or key not in index_by_key:
                if key in index_by_key:
                    result[index_by_key[key]] = configured
                else:
                    index_by_key[key] = len(result)
                    result.append(configured)
                continue
            base = result[index_by_key[key]]
            base["patterns"] = self._dedupe_patterns([*(base.get("patterns") or []), *patterns])
            base["all_patterns"] = self._dedupe_patterns([*(base.get("all_patterns") or []), *all_patterns])
            base["exclude_patterns"] = self._dedupe_patterns([*(base.get("exclude_patterns") or []), *exclude_patterns])
        return result or deepcopy(defaults)

    def _dedupe_patterns(self, patterns: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            if pattern in seen:
                continue
            seen.add(pattern)
            result.append(pattern)
        return result

    def _default_resource_table_key_specs_config(self) -> list[dict[str, Any]]:
        return [
            {"key": "windResourceTowerBasic", "patterns": [r"测风塔基本情况表"]},
            {"key": "windResourceShearStatistics", "patterns": [r"风切变指数统计表"]},
            {"key": "windResourceSpeedPowerStatistics", "patterns": [r"平均风速", r"风功率密度"]},
            {"key": "windResourceSectorDistribution", "patterns": [r"(?=.*扇区)(?=.*(?:风能|风向))"]},
            {"key": "windResourceDirectionEnergyFrequency", "patterns": [r"测风塔.*风向风能频率统计成果表", r"风向风能频率统计成果表", r"风向.*风能.*频率统计(?:成果)?表"]},
            {"key": "windResourceTurbulenceComparison", "patterns": [r"湍流(?:强度)?(?:统计结果|计算成果|比较)?表"]},
        ]

    def _default_electrical_secondary_table_key_specs_config(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "electricalSecondaryMainEquipment",
                "patterns": [r"升压站\s*电气\s*二次\s*主要设备表", r"电气\s*二次\s*主要设备表", r"电气\s*二次\s*设备材料清册表?", r"(?:6\.4\.4-3|6\.3\.16-1|6\.5\.3).*电气\s*二次.*(?:主要设备|设备材料清册)"],
            },
            {
                "key": "electricalSecondaryCommunicationEquipment",
                "patterns": [r"主要\s*通信\s*设备表", r"(?:6\.5-1|6\.5\.\d+).*通信.*设备表"],
            },
        ]

    def _load_generation_text_field_specs(self, specs: Any) -> dict[str, dict[str, Any]]:
        defaults = self._default_generation_text_field_specs_config()
        if not isinstance(specs, dict):
            return defaults
        result = deepcopy(defaults)
        for code, spec in specs.items():
            if isinstance(spec, list):
                patterns = [str(pattern) for pattern in spec if pattern]
                replace_defaults = False
                rule_source = "configs/output_schema.yaml"
            elif isinstance(spec, dict):
                patterns = [str(pattern) for pattern in (spec.get("patterns") or []) if pattern]
                replace_defaults = bool(spec.get("replace_defaults"))
                rule_source = str(spec.get("ruleSource") or spec.get("rule_source") or "configs/output_schema.yaml")
            else:
                continue
            if not patterns:
                continue
            key = str(code)
            base = result.get(key, {"patterns": [], "ruleSource": "configs/output_schema.yaml"})
            merged_patterns = patterns if replace_defaults else self._dedupe_patterns([*(base.get("patterns") or []), *patterns])
            result[key] = {"patterns": merged_patterns, "ruleSource": rule_source}
        return result

    def _default_generation_text_field_specs_config(self) -> dict[str, dict[str, Any]]:
        rule_source = "parser_engine.output.result_builder._merge_generation_text_fields"
        return {
            "installedCapacity": {
                "ruleSource": rule_source,
                "patterns": [
                    r"(?:规划容量为|装机容量为|装机容量)\s*([0-9]+(?:\.[0-9]+)?)\s*MW",
                    r"(?:规划容量为|装机容量为|装机容量)\s*([0-9]+(?:\.[0-9]+)?)\s*万千瓦",
                ],
            },
            "turbineCount": {
                "ruleSource": rule_source,
                "patterns": [r"(?:安装|选择安装|拟建风电场安装|拟建风电场选择安装)\s*([0-9]+)\s*台"],
            },
            "turbineCapacity": {
                "ruleSource": rule_source,
                "patterns": [r"单机容量为\s*([0-9]+(?:\.[0-9]+)?)\s*kW"],
            },
            "generationHubHeight": {
                "ruleSource": rule_source,
                "patterns": [r"轮毂高度[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(?:m|米)"],
            },
            "nonWakeLossFactor": {
                "ruleSource": rule_source,
                "patterns": [
                    r"不考虑尾流效应的折减系数\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*%",
                    r"综合折减系数\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*%",
                ],
            },
            "gridAnnualEnergy": {
                "ruleSource": rule_source,
                "patterns": [
                    r"年上网(?:发)?电量\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*万\s*kW\s*[·\.]?\s*h",
                    r"年上网(?:发)?电量\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*万\s*kWh",
                ],
            },
            "equivalentFullLoadHours": {
                "ruleSource": rule_source,
                "patterns": [r"年等效满负荷小时数\D{0,12}?([0-9]+(?:\.[0-9]+)?)\s*h"],
            },
        }

    def _combined_detail_field_specs_from_config(self, specs: Any) -> dict[str, dict[str, dict[str, str]]]:
        default_specs = self._default_combined_detail_field_specs()
        if not isinstance(specs, dict):
            return default_specs
        result = deepcopy(default_specs)
        for detail_key, detail_spec in specs.items():
            if not isinstance(detail_spec, dict):
                continue
            fields = detail_spec.get("fields")
            if not isinstance(fields, dict):
                continue
            result[str(detail_key)] = {str(code): str(source_key) for code, source_key in fields.items() if code and source_key}
        return result

    def _default_combined_detail_field_specs(self) -> dict[str, dict[str, str]]:
        return {
            "windResourceCombined": {
                "windResourceTowerCodes": "测风塔编号",
                "windFarmAirDensities": "该风电场的空气密度",
                "windResourceAirDensities": "高度对应的空气密度",
                "windResourceAirDensity10m": "10m高度空气密度",
                "windResourceAirDensity160m": "160m高度空气密度",
                "hubHeightAnnualAverageWindSpeed": "轮毂高度平均风速m/s",
                "hubHeightWindPowerDensity": "轮毂高度平均风功率密度W/m²",
                "windResourceMainWindDirections": "轮毂高度处的主风向",
                "windResourceSecondaryWindDirections": "轮毂高度处的次风向",
                "windResourceMainWindEnergyDirections": "轮毂高度处的主风能方向",
                "windResourceSecondaryWindEnergyDirections": "轮毂高度处的次风能方向",
                "representativeTurbulenceIntensity": "最大高度处代表性湍流强度",
                "windShearExponent": "综合风切变",
                "windResourceGenerationUses": "发电量计算是否使用",
            },
            "electricalPrimaryAccessStationCombined": {
                "accessStationName": "accessStationName",
                "accessibleVoltage": "accessibleVoltage",
                "accessibleCapacity": "accessibleCapacity",
            },
            "electricalPrimaryMainConnectionCombined": {
                "plannedCapacity": "plannedCapacity",
                "currentCapacity": "currentCapacity",
                "connectionType": "connectionType",
            },
            "electricalPrimaryLightningRodCombined": {
                "independentLightningRodCount": "independentLightningRodCount",
                "frameLightningRodCount": "frameLightningRodCount",
            },
            "collectorLineCombined": {
                "collectorVoltage": "collectorVoltage",
                "circuitCount": "circuitCount",
                "newRouteLength": "newRouteLength",
                "newOverheadLineLength": "newOverheadLineLength",
                "newSingleCircuitLineLength": "newSingleCircuitLineLength",
                "newDoubleCircuitLineLength": "newDoubleCircuitLineLength",
                "newCableLineLength": "newCableLineLength",
                "totalCollectorRouteLength": "totalCollectorRouteLength",
                "doubleCircuitOverheadRouteLength": "doubleCircuitOverheadRouteLength",
                "singleCircuitOverheadRouteLength": "singleCircuitOverheadRouteLength",
                "boxToTerminalTowerCableRouteLength": "boxToTerminalTowerCableRouteLength",
                "singleCircuitCableRouteLength": "singleCircuitCableRouteLength",
                "doubleCircuitCableRouteLength": "doubleCircuitCableRouteLength",
            },
            "substationCivilCombined": {
                "totalLandArea": "totalLandArea",
                "insideWallLandArea": "insideWallLandArea",
            },
            "roadParameters": {
                "accessRoadLength": "accessRoadLength",
                "accessRoadSubgradeWidth": "accessRoadSubgradeWidth",
                "accessRoadPavementWidth": "accessRoadPavementWidth",
                "newRoadLength": "newRoadLength",
                "rebuiltRoadLength": "rebuiltRoadLength",
                "subgradeWidth": "subgradeWidth",
                "pavementWidth": "pavementWidth",
                "siteRoadLength": "siteRoadLength",
            },
        }

    def _table_key_specs_from_config(self, specs: Any, default_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(specs, list):
            return deepcopy(default_specs)
        result: list[dict[str, Any]] = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            patterns = [str(pattern) for pattern in (spec.get("patterns") or []) if pattern]
            if not patterns:
                continue
            result.append(
                {
                    "key": spec.get("key"),
                    "patterns": patterns,
                    "exclude_patterns": [str(pattern) for pattern in (spec.get("exclude_patterns") or []) if pattern],
                }
            )
        return result or deepcopy(default_specs)

    def _default_resource_table_key_specs(self) -> list[dict[str, Any]]:
        return [
            {"key": "windResourceTowerBasic", "patterns": [r"\u6d4b\u98ce\u5854\u57fa\u672c\u60c5\u51b5\u8868"]},
            {"key": "windResourceShearStatistics", "patterns": [r"\u98ce\u5207\u53d8\u6307\u6570\u7edf\u8ba1\u8868"]},
            {"key": "windResourceSpeedPowerStatistics", "patterns": [r"\u5e73\u5747\u98ce\u901f", r"\u98ce\u529f\u7387\u5bc6\u5ea6"]},
            {"key": "windResourceSectorDistribution", "patterns": [r"\u6247\u533a", r"\u98ce\u80fd", r"\u98ce\u5411"]},
            {"key": "windResourceDirectionEnergyFrequency", "patterns": [r"\u6d4b\u98ce\u5854.*\u98ce\u5411\u98ce\u80fd\u9891\u7387\u7edf\u8ba1\u6210\u679c\u8868", r"\u98ce\u5411\u98ce\u80fd\u9891\u7387\u7edf\u8ba1\u6210\u679c\u8868", r"\u98ce\u5411.*\u98ce\u80fd.*\u9891\u7387\u7edf\u8ba1(?:\u6210\u679c)?\u8868"]},
            {"key": "windResourceTurbulenceComparison", "patterns": [r"\u6e4d\u6d41(?:\u5f3a\u5ea6)?(?:\u7edf\u8ba1\u7ed3\u679c|\u8ba1\u7b97\u6210\u679c|\u6bd4\u8f83)?\u8868"]},
        ]

    def _default_electrical_secondary_table_key_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "electricalSecondaryMainEquipment",
                "patterns": [r"\u5347\u538b\u7ad9\s*\u7535\u6c14\s*\u4e8c\u6b21\s*\u4e3b\u8981\u8bbe\u5907\u8868", r"\u7535\u6c14\s*\u4e8c\u6b21\s*\u4e3b\u8981\u8bbe\u5907\u8868", r"\u7535\u6c14\s*\u4e8c\u6b21\s*\u8bbe\u5907\u6750\u6599\u6e05\u518c\u8868?", r"(?:6\.4\.4-3|6\.3\.16-1|6\.5\.3).*\u7535\u6c14\s*\u4e8c\u6b21.*(?:\u4e3b\u8981\u8bbe\u5907|\u8bbe\u5907\u6750\u6599\u6e05\u518c)"]
            },
            {
                "key": "electricalSecondaryCommunicationEquipment",
                "patterns": [r"\u4e3b\u8981\s*\u901a\u4fe1\s*\u8bbe\u5907\u8868", r"(?:6\.5-1|6\.5\.\d+).*\u901a\u4fe1.*\u8bbe\u5907\u8868"]
            },
        ]
