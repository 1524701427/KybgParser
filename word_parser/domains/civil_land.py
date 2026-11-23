"""永久征地、长期租地和临时用地数据抽取。"""

from __future__ import annotations

import re
from typing import Any

from word_parser.document.ast.document import DocumentAST
from word_parser.document.ast.evidence import ParsedField


class LandAreaRulesMixin:
    """永久征地、长期租地和临时用地数据抽取，通过 CivilRulesMixin 组合到结果构建器。"""

    def _build_land_area_details(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "permanentLandArea": [],
            "longTermLeaseArea": [],
            "temporaryLandArea": [],
        }
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if len(matrix) < 2:
                continue
            header = matrix[0]
            row = matrix[1]
            header_text = " | ".join(header)
            if "永久性占地项目" in header_text:
                details["permanentLandArea"] = [
                    {
                        "item": self._cell_at_alias(header, row, ["永久性占地项目"]),
                        "windFoundation": self._cell_at_alias(header, row, ["风机基础"]),
                        "boxTransformerFoundation": self._cell_at_alias(header, row, ["箱变基础"]),
                        "substation110kv": self._cell_at_alias(header, row, ["升压站", "110kV升压站"]),
                        "collectorTower": self._cell_at_alias(header, row, ["集电线路杆塔征地", "杆塔"]),
                        "accessRoad": self._cell_at_alias(header, row, ["进升压站道路"]),
                        "total": self._cell_at_alias(header, row, ["合计"]),
                    }
                ]
            elif "长期租地项目" in header_text:
                details["longTermLeaseArea"] = [
                    {
                        "category": row[0] if len(row) > 0 else None,
                        "item": self._header_value_pair(header, row, ["电缆直埋征地", "场内永久道路", "进站道路"])[0],
                        "area": self._header_value_pair(header, row, ["电缆直埋征地", "场内永久道路", "进站道路"])[1],
                        "compensationCategory": None,
                        "compensationItem": None,
                        "compensationArea": None,
                    }
                ]
            elif "临时性占地项目" in header_text:
                details["temporaryLandArea"] = [
                    {
                        "item": self._cell_at_alias(header, row, ["临时性占地项目"]),
                        "road": self._cell_at_alias(header, row, ["风场道路", "临时施工道路"]),
                        "platform": self._cell_at_alias(header, row, ["吊装平台", "安装平台", "场内平整"]),
                        "collectorLine": self._cell_at_alias(header, row, ["集电线路"]),
                        "directBuriedCable": self._cell_at_alias(header, row, ["电缆直埋"]),
                        "constructionSite": self._cell_at_alias(header, row, ["施工临建场地", "生活临建"]),
                        "total": self._cell_at_alias(header, row, ["合计"]),
                    }
                ]
            elif self._looks_like_mixed_land_header(header_text):
                land = self._land_area_rows_from_mixed_table(matrix)
                for key, value in land.items():
                    if value:
                        details[key] = value
            elif "占地面积" in header_text and any("永久用地" in " ".join(item) for item in matrix):
                # 多级分组表以“永久/长期/临时”行划分口径，不能只凭同名道路跨组取数。
                land = self._land_area_rows_from_sectioned_table(matrix)
                for key, value in land.items():
                    if value:
                        details[key] = value
            elif all(keyword in header_text for keyword in ("项目", "面积")) and any("风机基础" in " | ".join(row) for row in matrix):
                permanent = self._permanent_land_from_item_area_table(matrix)
                if permanent:
                    details["permanentLandArea"] = [permanent]
            elif "临时征地面积汇总表" in header_text or all(keyword in header_text for keyword in ("项目", "临时用地")):
                temporary, compensation = self._temporary_land_from_item_area_table(matrix)
                if temporary:
                    details["temporaryLandArea"] = [temporary]
                if compensation:
                    details["longTermLeaseArea"] = [compensation]
        block_land = self._land_area_from_text_blocks(ast)
        for key, rows in block_land.items():
            if rows and (not details.get(key) or not self._detail_rows_have_values(details[key])):
                details[key] = rows
        self._merge_land_continuation_tables(ast, details)
        return details

    def _land_area_rows_from_sectioned_table(self, matrix: list[list[str]]) -> dict[str, list[dict[str, Any]]]:
        """读取“项目/占地面积”表中按用地性质分组的平方米数据。"""
        if not any("m2" in " ".join(row).lower() or "㎡" in " ".join(row) for row in matrix[:3]):
            return {}
        grouped: dict[str, dict[str, Any]] = {"permanent": {}, "long": {}, "temporary": {}}
        category: str | None = None
        for row in matrix[1:]:
            cells = [self._clean_text(str(cell or "")) for cell in row]
            label = cells[1] if len(cells) > 1 else ""
            if any(key in label for key in ("永久用地", "永久征地")):
                category = "permanent"
                continue
            if any(key in label for key in ("长期租地", "长期用地")):
                category = "long"
                continue
            if any(key in label for key in ("临时租地", "临时用地")):
                category = "temporary"
                continue
            if category is None:
                continue
            if "合计" in cells[0]:
                label, value_text = "合计", cells[1] if len(cells) > 1 else ""
            else:
                value_text = cells[2] if len(cells) > 2 else ""
            value = self._normalize_table_cell(value_text)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                grouped[category][label] = value

        permanent = grouped["permanent"]
        long_term = grouped["long"]
        temporary = grouped["temporary"]
        road_areas = [value for label, value in long_term.items() if "场内" in label and "道路" in label]
        rows = {
            "permanentLandArea": [{
                "item": "面积",
                "windFoundation": self._first_present(permanent.get("风力发电机组基础"), permanent.get("风机基础")),
                "boxTransformerFoundation": self._first_present(permanent.get("箱式变电站基础"), permanent.get("箱变基础")),
                "substation110kv": self._first_present(permanent.get("升压站"), permanent.get("110kV升压站")),
                "accessRoad": self._first_present(permanent.get("进站道路"), permanent.get("新建进站道路")),
                "total": permanent.get("合计"),
            }],
            "longTermLeaseArea": [{
                "category": "面积", "item": "长期租地",
                "accessRoad": self._first_present(long_term.get("进站道路"), long_term.get("新建进站道路")),
                "maintenanceRoad": self._clean_number(sum(road_areas)) if road_areas else None,
                "towerFoundation": self._first_present(long_term.get("铁塔基础"), long_term.get("杆塔基础")),
                "total": long_term.get("合计"),
                "area": long_term.get("合计"),
            }],
            "temporaryLandArea": [{
                "item": "面积",
                "road": self._first_present(temporary.get("施工道路"), temporary.get("临时施工道路")),
                "temporaryRoad": self._first_present(temporary.get("施工道路"), temporary.get("临时施工道路")),
                "platform": self._first_present(temporary.get("施工吊装平台"), temporary.get("吊装平台")),
                "directBuriedCable": self._first_present(temporary.get("直埋电缆"), temporary.get("电缆直埋")),
                "constructionSite": self._first_present(temporary.get("临时施工区"), temporary.get("施工临建场地")),
                "total": temporary.get("合计"),
            }],
        }
        return {key: value for key, value in rows.items() if any(item is not None for name, item in value[0].items() if name not in {"item", "category"})}

    def _detail_rows_have_values(self, rows: list[dict[str, Any]]) -> bool:
        return any(any(value is not None for value in row.values()) for row in rows)

    def _land_area_from_text_blocks(self, ast: DocumentAST) -> dict[str, list[dict[str, Any]]]:
        details: dict[str, list[dict[str, Any]]] = {
            "permanentLandArea": [],
            "longTermLeaseArea": [],
            "temporaryLandArea": [],
        }
        texts = [
            self._clean_text(block.text)
            for block in ast.blocks
            if block.text and ("永久性占地" in block.text or "长期租地" in block.text or "临时性占地" in block.text)
        ]
        for text in texts:
            if "永久性占地" in text:
                permanent = {
                    "item": "面积",
                    "windFoundation": self._area_value_after_label(text, ["风机基础"]),
                    "boxTransformerFoundation": self._area_value_after_label(text, ["箱变基础", "箱式变电站基础"]),
                    "substation110kv": self._area_value_after_label(text, ["110kV升压站", "升压站"]),
                    "collectorTower": self._area_value_after_label(text, ["集电线路杆塔征地", "杆塔基础"]),
                    "accessRoad": self._area_value_after_label(text, ["进升压站道路", "进站道路"]),
                    "total": self._area_value_after_label(text, ["永久性占地合计", "永久用地合计"]),
                }
                if permanent["total"] is None:
                    permanent["total"] = self._sum_present(value for key, value in permanent.items() if key != "item")
                if any(value is not None for key, value in permanent.items() if key != "item"):
                    details["permanentLandArea"] = [permanent]
            if "长期租地" in text:
                long_term = {
                    "category": "面积",
                    "item": "长期租地",
                    "directBuriedCable": self._area_value_after_label(text, ["电缆直埋征地", "电缆直埋"]),
                    "permanentRoad": self._area_value_after_label(text, ["场内永久道路", "永久道路"]),
                    "accessRoad": self._area_value_after_label(text, ["进站道路", "进升压站道路"]),
                    "area": None,
                    "compensationCategory": None,
                    "compensationItem": None,
                    "compensationArea": None,
                    "total": self._area_value_after_label(text, ["长期租地合计", "长期租地总计"]),
                }
                if long_term["total"] is None:
                    long_term["total"] = self._sum_present(long_term.get(key) for key in ("directBuriedCable", "permanentRoad", "accessRoad"))
                long_term["area"] = long_term["total"]
                if any(value is not None for key, value in long_term.items() if key not in {"category", "item"}):
                    details["longTermLeaseArea"] = [long_term]
            if "临时性占地" in text:
                road = self._area_value_after_label(text, ["临时施工道路", "风场道路"])
                construction_site = self._area_value_after_label(text, ["生活临建", "施工临建场地", "临时施工设施"])
                temporary = {
                    "item": "面积",
                    "road": road,
                    "platform": self._area_value_after_label(text, ["场地平整（安装平台）", "安装平台", "吊装平台", "场内平整"]),
                    "collectorLine": self._area_value_after_label(text, ["集电线路"]),
                    "directBuriedCable": self._area_value_after_label(text, ["电缆直埋"]),
                    "constructionSite": construction_site,
                    "temporaryRoad": road,
                    "livingFacility": construction_site,
                    "total": self._area_value_after_label(text, ["临时性占地合计", "临时用地合计", "临时性占地总计"]),
                }
                if temporary["total"] is None:
                    temporary["total"] = self._sum_present(temporary.get(key) for key in ("road", "platform", "collectorLine", "directBuriedCable", "constructionSite"))
                if any(value is not None for key, value in temporary.items() if key != "item"):
                    details["temporaryLandArea"] = [temporary]
        return details

    def _area_value_after_label(self, text: str, labels: list[str]) -> Any:
        for label in labels:
            pattern = rf"{re.escape(label)}\s*\|\s*(?:m2|m²|㎡|平方米)?\s*\|\s*([0-9]+(?:\.[0-9]+)?)"
            match = re.search(pattern, text)
            if match:
                return self._normalize_scalar(match.group(1))
        return None

    def _merge_land_continuation_tables(self, ast: DocumentAST, details: dict[str, list[dict[str, Any]]]) -> None:
        if not details.get("temporaryLandArea"):
            return
        target = details["temporaryLandArea"][0]
        for table in ast.tables:
            matrix = self._table_matrix(table)
            if not matrix:
                continue
            labels = {row[0].strip() for row in matrix if row}
            if not ({"电缆直埋", "施工临建场地"} & labels):
                continue
            for row in matrix:
                label = row[0].strip() if row else ""
                if label not in {"电缆直埋", "施工临建场地", "合计"}:
                    continue
                value = self._normalize_table_cell(row[3]) if len(row) > 3 else self._last_numeric_cell(row)
                if value is None:
                    continue
                if label == "电缆直埋":
                    target["directBuriedCable"] = value
                elif label == "施工临建场地":
                    target["constructionSite"] = value
                elif label == "合计":
                    target["total"] = value

    def _permanent_land_from_item_area_table(self, matrix: list[list[str]]) -> dict[str, Any] | None:
        header = matrix[0]
        item_index = self._find_header_index(header, ["项目"])
        area_index = self._find_header_index(header, ["面积（㎡）", "面积(m2)", "面积"])
        if item_index is None or area_index is None:
            return None
        values: dict[str, Any] = {}
        for row in matrix[1:]:
            if item_index >= len(row) or area_index >= len(row):
                continue
            label = row[item_index]
            value = self._normalize_table_cell(row[area_index])
            if value is not None:
                values[label] = value
        result = {
            "item": "面积",
            "windFoundation": values.get("风机基础"),
            "boxTransformerFoundation": values.get("箱变基础"),
            "substation110kv": self._first_present(values.get("升压站"), values.get("110kV升压站")),
            "collectorTower": self._first_present(values.get("集电线路杆塔征地"), values.get("杆塔基础")),
            "accessRoad": self._first_present(values.get("进升压站道路"), values.get("进站道路")),
            "total": values.get("合计"),
        }
        if result["total"] is None:
            result["total"] = self._sum_present(value for key, value in result.items() if key != "item")
        return result if any(value is not None for key, value in result.items() if key != "item") else None

    def _temporary_land_from_item_area_table(self, matrix: list[list[str]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        header = matrix[1] if matrix and len(matrix[0]) == 1 and len(matrix) > 1 else matrix[0]
        data_rows = matrix[2:] if matrix and len(matrix[0]) == 1 and len(matrix) > 1 else matrix[1:]
        item_index = self._find_header_index(header, ["项目"])
        temp_index = self._find_header_index(header, ["临时用地", "临时征地"])
        compensation_index = self._find_header_index(header, ["临征永补"])
        if item_index is None:
            return None, None
        values: dict[str, Any] = {}
        compensation_values: dict[str, Any] = {}
        for row in data_rows:
            if item_index >= len(row):
                continue
            label = row[item_index]
            if temp_index is not None and temp_index < len(row):
                value = self._normalize_table_cell(row[temp_index])
                if value is not None:
                    values[label] = value
            if compensation_index is not None and compensation_index < len(row):
                value = self._normalize_table_cell(row[compensation_index])
                if value is not None:
                    compensation_values[label] = value
        temporary = {
            "item": "面积",
            "road": self._first_present(values.get("检修道路"), values.get("风场道路"), values.get("施工道路"), values.get("临时施工道路")),
            "platform": self._first_present(values.get("吊装平台"), values.get("安装平台")),
            "collectorLine": self._first_present(values.get("杆塔基础"), values.get("集电线路")),
            "directBuriedCable": self._first_present(values.get("电缆"), values.get("直埋电缆"), values.get("电缆直埋")),
            "constructionSite": self._first_present(values.get("临时施工设施"), values.get("施工临建场地"), values.get("施工临建"), values.get("生活临建")),
            "total": values.get("合计"),
        }
        if temporary["total"] is None:
            temporary["total"] = self._sum_present(value for key, value in temporary.items() if key != "item")
        compensation = None
        compensation_total = self._first_present(compensation_values.get("合计"), self._sum_present(compensation_values.values()))
        if compensation_total is not None:
            compensation = {
                "category": "临征永补",
                "item": "临征永补",
                "area": compensation_total,
                "compensationCategory": "临征永补项目",
                "compensationItem": "杆塔基础/检修道路",
                "compensationArea": compensation_total,
            }
        return (temporary if any(value is not None for key, value in temporary.items() if key != "item") else None), compensation

    def _land_area_rows_from_mixed_table(self, matrix: list[list[str]]) -> dict[str, list[dict[str, Any]]]:
        header = matrix[0]
        permanent_index = self._find_header_index(header, ["永久征地", "永久占地", "征地", "永久"])
        long_index = self._find_header_index(header, ["长期租地"])
        temporary_index = self._find_header_index(header, ["短期租地", "临时性占地", "临时租地", "临时"])
        values: dict[str, Any] = {}
        for row in matrix[1:]:
            label = row[0] if row else ""
            if not label:
                continue
            for key, index in (("permanent", permanent_index), ("long", long_index), ("temporary", temporary_index)):
                if index is not None and index < len(row):
                    number = self._normalize_table_cell(row[index])
                    if number is not None:
                        values[f"{key}:{label}"] = number
        permanent = {
            "item": "面积",
            "windFoundation": values.get("permanent:风机基础"),
            "boxTransformerFoundation": self._first_present(values.get("permanent:箱变"), values.get("permanent:箱变基础")),
            "substation110kv": self._first_present(values.get("permanent:升压站"), values.get("permanent:110kV升压站")),
            "collectorTower": self._first_present(values.get("permanent:集电线路杆塔征地"), values.get("permanent:杆塔基础")),
            "accessRoad": self._first_present(values.get("permanent:升压站进站道路"), values.get("permanent:进升压站道路"), values.get("permanent:进站道路")),
        }
        permanent["total"] = self._first_present(values.get("permanent:合计"), self._sum_present(permanent.values()))
        long_term = {
            "category": "面积",
            "item": "长期租地",
            "directBuriedCable": self._first_present(values.get("long:电缆直埋"), values.get("long:电缆直埋征地")),
            "permanentRoad": values.get("long:场内永久道路"),
            "maintenanceRoad": self._first_present(values.get("long:检修道路"), values.get("long:场内永久道路")),
            "accessRoad": self._first_present(values.get("long:进站道路"), values.get("long:进升压站道路")),
            "towerFoundation": self._first_present(values.get("long:塔基础"), values.get("long:铁塔基础"), values.get("long:杆塔基础")),
            "area": None,
            "compensationCategory": None,
            "compensationItem": None,
            "compensationArea": None,
        }
        long_term["total"] = self._first_present(values.get("long:合计"), self._sum_present(long_term.get(key) for key in ("directBuriedCable", "permanentRoad", "maintenanceRoad", "accessRoad", "towerFoundation")))
        long_term["area"] = long_term["total"]
        temporary = {
            "item": "面积",
            "road": self._first_present(values.get("temporary:风场道路"), values.get("temporary:施工道路"), values.get("temporary:临时施工道路")),
            "temporaryRoad": self._first_present(values.get("temporary:施工道路"), values.get("temporary:临时施工道路"), values.get("temporary:风场道路")),
            "platform": self._first_present(values.get("temporary:吊装平台"), values.get("temporary:安装平台"), values.get("temporary:施工吊装平台")),
            "collectorLine": values.get("temporary:集电线路"),
            "directBuriedCable": self._first_present(values.get("temporary:电缆"), values.get("temporary:直埋电缆"), values.get("temporary:电缆直埋")),
            "constructionSite": self._first_present(values.get("temporary:施工临建场地"), values.get("temporary:施工临建"), values.get("temporary:生活临建")),
        }
        temporary["livingFacility"] = temporary["constructionSite"]
        temporary["total"] = self._first_present(values.get("temporary:合计"), self._sum_present(temporary.values()))
        return {
            "permanentLandArea": [permanent] if any(value is not None for value in permanent.values()) else [],
            "longTermLeaseArea": [long_term] if long_term["area"] is not None else [],
            "temporaryLandArea": [temporary] if any(value is not None for value in temporary.values()) else [],
        }

    def _looks_like_mixed_land_header(self, header_text: str) -> bool:
        return (
            "项目" in header_text
            and any(keyword in header_text for keyword in ("永久征地", "永久占地", "征地"))
            and any(keyword in header_text for keyword in ("长期租地", "短期租地", "临时性占地", "临时租地"))
        )

    def _apply_land_field_overrides(self, fields: dict[str, ParsedField], details: dict[str, list[dict[str, Any]]]) -> None:
        mapping = {
            "permanentLandWindFoundationArea": ("风机基础征地面积", "permanentLandArea", "windFoundation"),
            "permanentLandBoxTransformerArea": ("箱变基础征地面积", "permanentLandArea", "boxTransformerFoundation"),
            "permanentLandSubstationArea": ("升压站征地面积", "permanentLandArea", "substation110kv"),
            "permanentLandCollectorTowerArea": ("\u6c38\u4e45\u5360\u5730-\u96c6\u7535\u7ebf\u8def\u6746\u5854\u5f81\u5730", "permanentLandArea", "collectorTower"),
            "permanentLandAccessRoadArea": ("进站道路征地面积", "permanentLandArea", "accessRoad"),
            "permanentLandTotalArea": ("永久征地总面积", "permanentLandArea", "total"),
            "longTermLeaseCableBuriedArea": ("\u957f\u671f\u79df\u5730-\u7535\u7f06\u76f4\u57cb\u5f81\u5730", "longTermLeaseArea", "directBuriedCable"),
            "longTermLeasePermanentRoadArea": ("\u957f\u671f\u79df\u5730-\u573a\u5185\u6c38\u4e45\u9053\u8def", "longTermLeaseArea", "permanentRoad"),
            "longTermLeaseMaintenanceRoadArea": ("检修道路征地总面积", "longTermLeaseArea", "maintenanceRoad"),
            "longTermLeaseAccessRoadArea": ("进站道路征地总面积", "longTermLeaseArea", "accessRoad"),
            "longTermLeaseTowerFoundationArea": ("铁塔基础征地总面积", "longTermLeaseArea", "towerFoundation"),
            "longTermLeaseTotalArea": ("长期征地总面积", "longTermLeaseArea", "total"),
            "temporaryLandPlatformArea": ("施工吊装平台征地总面积", "temporaryLandArea", "platform"),
            "temporaryLandConstructionRoadArea": ("施工道路征地总面积", "temporaryLandArea", "temporaryRoad"),
            "temporaryLandDirectBuriedCableArea": ("直埋电缆征地总面积", "temporaryLandArea", "directBuriedCable"),
            "temporaryLandConstructionSiteArea": ("临时施工区征地总面积", "temporaryLandArea", "constructionSite"),
            "temporaryLandLivingArea": ("\u4e34\u65f6\u5360\u5730-\u751f\u6d3b\u4e34\u5efa", "temporaryLandArea", "livingFacility"),
            "temporaryLandTotalArea": ("临时征地总面积", "temporaryLandArea", "total"),
        }
        for code, (name, detail_key, value_key) in mapping.items():
            rows = details.get(detail_key) or []
            if not rows:
                continue
            value = rows[0].get(value_key)
            if value is not None:
                self._set_field(fields, code, name, value, "m2", f"{detail_key}.{value_key}")
