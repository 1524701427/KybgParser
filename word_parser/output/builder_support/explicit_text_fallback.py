"""对报告正文中明确给出的数值进行保守兜底抽取。"""

from __future__ import annotations

import re
from typing import Any


def explicit_text_values(ast: Any) -> dict[str, tuple[Any, str, int | None]]:
    pages = [
        (str(item.get("text") or ""), item.get("page"))
        for item in ((ast.meta or {}).get("pdf_page_lines") or (ast.meta or {}).get("pdf_page_texts") or [])
        if isinstance(item, dict)
    ]
    if not pages:
        pages = [(str(block.text or ""), block.page) for block in ast.blocks]

    found: dict[str, tuple[Any, str, int | None]] = {}

    def add(code: str, pattern: str, value_group: str = "value", flags: int = 0, transform=None) -> None:
        if code in found:
            return
        for text, page in pages:
            match = re.search(pattern, text, flags | re.MULTILINE)
            if match:
                value = match.group(value_group).strip()
                if transform:
                    value = transform(value)
                found[code] = (value, match.group(0).strip(), page)
                return

    # 重复的页眉标题及明确标注的概况值。
    add("projectName", r"^(?![^\n]*(?:证书|资信|编号|有限公司|集团公司|设计院|承担|编制|《|规范|规程))(?P<value>[^\n]{3,80}?(?:风电场|风电项目|风力发电项目|光伏项目|光伏电站)[^\n]{0,25}?)(?:可行性研究报告|可研报告)")
    add("designUnit", r"^(?P<value>[^\n]{2,70}?(?:有限公司|设计院))\s*编制\s*$")
    add("investmentOwnerCompany", r"(?:本项目|本工程)\s*建设方为\s*(?P<value>[\u4e00-\u9fa5]{2,60}?(?:有限公司|集团公司))")
    add("investmentOwnerCompany", r"(?:建设单位|项目单位|项目法人)\s*[:：]?\s*\n\s*(?P<value>[\u4e00-\u9fa5\s]{2,70}?(?:有限\s*公司|集团\s*公司))\s*\n", transform=lambda x: re.sub(r"\s+", "", x))
    add("projectAddressDetail", r"(?:本项目|本工程|风电场工程)(?:（[^）]{1,30}）)?\s*位于\s*(?P<value>[^，。；;]{2,100}?县[^，。；;]{0,50}?(?:镇|乡)(?:、[^，。；;]{1,10}?(?:镇|乡))*\s*一带)", transform=lambda x: re.sub(r"\s+", "", x))
    add("projectAddressDetail", r"建设地点\s*[:：]?\s*\n\s*(?P<value>[^\n]{2,30}省[^\n]{0,30}\n[^\n]{0,30}(?:县|区|市))\s*\n", transform=lambda x: re.sub(r"\s+", "", x))
    add("projectAddressDetail", r"(?:建设地点|项目位置)\s*[:：]?\s*\n\s*(?P<value>[^\n]{2,90}?(?:县|区|市))\s*$", transform=lambda x: re.sub(r"\s+", "", x))
    add("projectAddressDetail", r"(?:本项目|本工程|风电场工程)\s*位于\s*(?P<value>[^，。；;\n]{2,80}?(?:县|区|市))\s*境内")
    if "projectAddressDetail" in found:
        detail, evidence, page = found["projectAddressDetail"]
        city = re.search(r"(?:省|自治区)([^省]{2,24}?(?:自治州|地区|市))", detail)
        county = re.search(r"([^省州市]{2,12}?(?:县|区|旗))", detail)
        if city:
            found["projectAddressCity"] = (city.group(1), evidence, page)
        if county:
            found["projectAddressCounty"] = (county.group(1), evidence, page)
        towns = re.findall(r"(?:[县区][东西南北中]部|[县区]|、)([\u4e00-\u9fa5]{2,8}(?:镇|乡))", detail)
        if towns:
            found["projectAddressTown"] = ("、".join(dict.fromkeys(towns)), evidence, page)

    add("siteElevationRange", r"(?:场区|风电场|项目区)[^。；;\n]{0,24}?海拔(?:高程)?(?:在|为|约)?\s*(?P<value>\d{3,4}\s*[~～—-]\s*\d{3,4})\s*m", transform=lambda x: re.sub(r"\s+", "", x))
    add("projectGeomorphology", r"(?:场址|场区|拟建场址)[^。；;]{0,30}?(?:属于|为)\s*(?P<value>[^，。；;\n]{2,50}?地貌)")
    add("maxWindSpeed50Year", r"(?:综上|综合分析)[^。；;]{0,20}?本项目\s*50\s*年一遇最大风速[^。；;]{0,40}?(?:即|为|采用)\s*(?P<value>\d{2}(?:\.\d+)?)\s*m/s", flags=re.IGNORECASE, transform=float)

    # 每条规则都应保留设备上下文：单独的电压或容量存在歧义。
    add("electricalPrimarySubstationVoltageLevel", r"(?:新建|拟建|建设)\s*\d+\s*座\s*(?P<value>\d{2,3})\s*kV\s*升压(?:变电)?站", transform=int)
    add("electricalPrimarySubstationConstructionType", r"(?P<value>新建)\s*\d+\s*座\s*\d{2,3}\s*kV\s*升压(?:变电)?站")
    add("circuitCount", r"(?P<value>\d+)\s*回\s*\d{2,3}\s*kV\s*集电线路", transform=int)
    add("electricalPrimaryCurrentOutgoingLineCount", r"(?:风电场以|本期|升压站以)\s*(?P<value>\d+)\s*回\s*\d{2,3}\s*kV\s*出线", transform=int)
    add("electricalPrimaryCurrentOutgoingLineCount", r"\d{2,3}\s*kV\s*出线间隔回路数\s*(?P<value>\d+)\s*回", transform=int)
    add("electricalPrimaryFutureOutgoingLineCount", r"\d{2,3}\s*kV\s*出线间隔回路数\s*\d+\s*回\s*(?P<value>\d+)\s*回", transform=int)
    add("accessStationName", r"(?:出线至|送至)\s*(?P<value>[\u4e00-\u9fa5]{2,12}\s*\d{2,3}\s*kV\s*(?:汇集站|变电站))", transform=lambda x: re.sub(r"\s+", "", x))
    add("accessStationName", r"(?:接入|送至)\s*(?P<value>[\u4e00-\u9fa5]{2,12}\s*\d{2,3}\s*kV\s*变电站)", transform=lambda x: re.sub(r"\s+", "", x))
    add("connectionType", r"\d{2,3}\s*kV\s*侧采用\s*(?P<value>[^，。；;\n]{2,35}?接线方式)")
    add("mainTransformerRatedCapacity", r"(?:升压站规模按|主变(?:压器)?(?:容量|规模)?(?:按|为|采用|选用)?|规模按)\s*\d+\s*[×xX]\s*(?P<value>\d{2,4})\s*MVA", flags=re.IGNORECASE, transform=lambda value: int(value) * 1000)
    add("mainTransformerType", r"主变压器选用\s*\d+\s*台\s*(?P<value>[^。；;\n]{4,60}?变压器)")
    add("mainTransformerModel", r"主变压器\s*\n\s*(?P<value>SZ\d{1,3}[-－]\d{4,6}/\d{2,3})", flags=re.IGNORECASE)
    add("mainTransformerNum", r"主变压器容量及数量\s*(?P<value>\d+)\s*[×xX]\s*\d+(?:\.\d+)?\s*MVA", transform=int)
    add("mainTransformerType", r"(?:主变压器技术参数|主变压器参数)[\s\S]{0,150}?型式\s*(?P<value>三相[^\n]{3,50}变压器)")
    add("mainTransformerVoltageRatio", r"(?:主变压器技术参数|主变压器参数)[\s\S]{0,240}?电压比\s*(?P<value>\d{2,3}\s*[±+\-]\s*\d+(?:\.\d+)?\s*[×xX]\s*\d+(?:\.\d+)?%\s*/\s*\d{2,3}\s*kV)", transform=lambda x: re.sub(r"\s+", "", x))
    add("connectionGroupType", r"(?:主变压器技术参数|主变压器参数)[\s\S]{0,300}?联结组别\s*(?P<value>Y[NnDd0-9]+)")
    add("electricalPrimaryGisType", r"\d{2,3}\s*kV\s*配电装置采用\s*(?P<value>GIS\s*组合电器)", transform=lambda x: re.sub(r"\s+", "", x))
    add("electricalPrimaryGisType", r"\d{2,3}\s*kV\s*(?:高压)?配电装置采用\s*(?P<value>SF6\s*全封闭组合电器)", transform=lambda x: re.sub(r"\s+", "", x))
    add("electricalPrimaryGisModelInfo", r"\d{2,3}\s*kV\s*(?:高压)?配电装置[^。；;\n]{0,60}?GIS[^。；;\n]{0,80}[\s\S]{0,130}?型号\s*(?P<value>ZF[-－]\d{2,3})", flags=re.IGNORECASE)
    add("totalLandArea", r"升压站(?:红线)?占地面积(?:为)?\s*(?P<value>\d{3,8}(?:\.\d+)?)\s*(?:m2|m²|㎡|平方米)", transform=float)
    add("totalLandArea", r"升压站红线面积\s*(?:m2|m²|㎡|平方米)\s*(?P<value>\d{3,8}(?:\.\d+)?)", transform=float)
    add("financeCurtailmentRateSingle", r"预计年限电率\s*(?P<value>\d+(?:\.\d+)?)\s*%", transform=float)
    add("financeCurtailmentAnnualOnGridEnergyMwh", r"预计年限电率\s*\d+(?:\.\d+)?\s*%\s*平\s*均上网电量约?\s*(?P<value>\d+(?:\.\d+)?)\s*MWh", flags=re.IGNORECASE, transform=float)
    add("financeWorkingCapitalValue", r"(?:本项目|本工程)流动资金[^。；;]{0,100}?总计\s*(?P<value>\d+(?:\.\d+)?)\s*万元", transform=float)
    add("investmentPriceLevel", r"按\s*(?P<value>20\d{2}\s*年\s*\d{1,2}\s*月)份?材料价格水平计算", transform=lambda x: re.sub(r"\s+", "", x))
    add("environmentalInvestment", r"(?:工程或费用名称[\s\S]{0,100}?合计\s*[（(]万元[）)][\s\S]{0,500}?)?环境保护工程\s*项\s*\d+(?:\.\d+)?\s*\d+(?:\.\d+)?\s*(?P<value>\d+(?:\.\d+)?)", transform=float)
    add("waterSoilConservationInvestment", r"水土保持工程\s*项\s*\d+(?:\.\d+)?\s*\d+(?:\.\d+)?\s*(?P<value>\d+(?:\.\d+)?)", transform=float)
    add("groundingTransformerModel", r"接地变\s*\n\s*(?P<value>DKSC[-－]\d{3,5}/\d{2,3})", flags=re.IGNORECASE)
    add("groundingStationTransformerQuantity", r"(?:配置|设置)\s*(?P<value>\d+|一|两)\s*台\s*(?:容量为\s*\d+\s*kVA\s*)?接地变兼站用变", transform=lambda x: {"一": 1, "两": 2}.get(x, int(x) if x.isdigit() else x))
    add("electricalPrimaryGisType", r"(?:本报告|本项目|本工程)[^。；;\n]{0,60}?(?:推荐|确定|选用|采用)[^。；;\n]{0,40}?(?P<value>户内\s*GIS|户外\s*GIS)", flags=re.IGNORECASE, transform=lambda x: re.sub(r"\s+", "", x))
    for text, page in pages:
        gis_equipment = re.search(r'\d{2,3}\s*kV\s*GIS\s*\n\s*成套设备[\s\S]{0,450}', text, re.IGNORECASE)
        if not gis_equipment:
            continue
        specification = gis_equipment.group(0)
        for code, pattern in (
            ('electricalPrimaryCircuitBreakerModel', r'SF6\s*断路器\s*(GCB\s*\d{2,3}\s*kV\s*[,，]\s*\d+\s*A\s*[,，]\s*\d+\s*kA/\d+\s*s)'),
            ('electricalPrimaryDisconnectorModel', r'三工位隔离开关\s*(TPS\s*\d{2,3}\s*kV\s*\d+\s*A[-－]\d+\s*kA)'),
        ):
            match = re.search(pattern, specification, re.IGNORECASE)
            if match:
                found.setdefault(code, (re.sub(r'\s+', '', match.group(1)), match.group(0), page))
        break
    add("electricalPrimaryVoltageTransformerModel", r"电压互感器[^。；;\n]{0,40}?型号\s*(?:为|是|[:：])\s*(?P<value>[A-Z]{2,8}[-－]\d{2,4}(?:[/√A-Z0-9.－-]{0,40})?)\b", flags=re.IGNORECASE)
    add("electricalPrimaryBoxTransformerCapacity", r"箱变容量(?:为|是|[:：])\s*(?P<value>\d{3,5})\s*kVA", flags=re.IGNORECASE, transform=int)
    add("electricalPrimaryBoxTransformerModel", r"箱式变压器\s*\n\s*(?P<value>[A-Z]{1,5}\d{1,3}[-－]\d{3,6}/\d{2,3})", flags=re.IGNORECASE)

    for text, page in pages:
        gis_set = re.search(r"\d{2,3}\s*kV\s*GIS\s*成套设备\s*\n\s*[^\n]{1,40}间隔\s*\n\s*(?P<unit>套|组)\s*\n\s*(?P<count>\d+)", text, re.IGNORECASE)
        if gis_set:
            found.setdefault("electricalPrimaryGisQuantity", (int(gis_set.group("count")), gis_set.group(0), page))
            found.setdefault("electricalPrimaryGisUnit", (gis_set.group("unit"), gis_set.group(0), page))
        if "风力发电机组基础设计" in text or "风机基础型式" in text:
            foundation = re.search(
                r"(?:本项目|本工程)(?:拟定|推荐|最终)?采用\s*(?:φ\s*\d+\s*mm\s*)?"
                r"(?P<value>(?:扩底|钻孔)?灌注桩基础|预制桩基础|独立基础|桩基础)", text
            )
            if foundation:
                found.setdefault("windFoundationType", (foundation.group("value"), foundation.group(0), page))
        combined_model = re.search(r"(?:接地变兼站用变|接地\s*兼站用变)[\s\S]{0,70}?(DKSC-\d{3,5}/\d{2}-\d{2,5}/\d(?:\.\d+)?)", text)
        if combined_model:
            model = combined_model.group(1)
            found.setdefault("groundingStationTransformerCapacity", (int(re.search(r"DKSC-(\d+)", model).group(1)), combined_model.group(0), page))
        grounding_resistance = re.search(r"接地电阻\s*[：:]\s*(?P<value>\d+(?:\.\d+)?)\s*Ω\s*\n\s*数量\s*[：:]\s*(?P<count>\d+)\s*(?P<unit>台)", text)
        if grounding_resistance and "DKSC-" in text:
            found.setdefault("groundingStationTransformerResistance", (float(grounding_resistance.group("value")), grounding_resistance.group(0), page))
            found.setdefault("groundingStationTransformerQuantity", (int(grounding_resistance.group("count")), grounding_resistance.group(0), page))
            found.setdefault("groundingStationTransformerUnit", (grounding_resistance.group("unit"), grounding_resistance.group(0), page))
        battery = re.search(r"蓄电池组\s*\n\s*(?P<spec>\d{2,3}\s*V\s*/\s*\d{2,4}\s*Ah\s*[,，]\s*\d+\s*节)\s*\n\s*(?P<unit>组)\s*\n\s*(?P<count>\d+)", text, re.IGNORECASE)
        battery = battery or re.search(r"蓄电池屏\s*\n\s*(?P<spec>阀控[^\n]{0,65}?\d+\s*Ah[^\n]{0,45}?)\s*\n\s*(?P<unit>套|组|面)\s*\n\s*(?P<count>\d+)", text, re.IGNORECASE)
        if battery:
            for code, value in (("electricalSecondaryBatterySpec", battery.group("spec")),
                                ("electricalSecondaryBatteryUnit", battery.group("unit")),
                                ("electricalSecondaryBatteryQuantity", int(battery.group("count")))):
                found.setdefault(code, (value, battery.group(0), page))
        ups = re.search(r"UPS\s*逆变电源屏\s*\n\s*(?P<spec>\d+(?:\.\d+)?\s*kVA)\s*\n\s*(?P<unit>面|套)\s*\n\s*(?P<count>\d+)", text, re.IGNORECASE)
        ups = ups or re.search(r"UPS\s*电源屏\s*\n\s*(?P<spec>容量为\s*\d+(?:\.\d+)?\s*kVA)\s*\n\s*(?P<unit>台|面|套)\s*\n\s*(?P<count>\d+)", text, re.IGNORECASE)
        if ups:
            for code, value in (("electricalSecondaryUpsSpec", ups.group("spec")),
                                ("electricalSecondaryUpsUnit", ups.group("unit")),
                                ("electricalSecondaryUpsQuantity", int(ups.group("count")))):
                found.setdefault(code, (value, ups.group(0), page))

    # 型号在同一报告中出现互相矛盾的版本时，保留一致的容量等参数，不猜测型号和电压。
    combined_models = {
        match.group(1)
        for text, _ in pages
        for match in re.finditer(
            r"(?:接地变兼站用变|接地\s*兼站用变)[\s\S]{0,70}?(DKSC-\d{3,5}/\d{2}-\d{2,5}/\d(?:\.\d+)?)",
            text,
        )
    }
    detailed_models = {
        match.group(1)
        for text, _ in pages
        if '接地变' in text and '接地电阻' in text
        for match in re.finditer(r'型号\s*[：:]\s*(DKSC-\d{3,5}/\d{2}-\d{2,5}/\d(?:\.\d+)?)', text)
    }
    # 设备参数页的明确“型号”优先于方案比选表中的型号。
    selected_models = detailed_models if len(detailed_models) == 1 else combined_models
    if len(selected_models) == 1:
        model = next(iter(selected_models))
        found["groundingStationTransformerModel"] = (model, model, None)
        voltage = re.search(r"DKSC-\d+/(\d{2})-", model)
        if voltage:
            found["groundingStationTransformerVoltage"] = (int(voltage.group(1)), model, None)

    return found
