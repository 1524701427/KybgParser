"""针对文档原生指标发现功能的测试。"""

import json

from word_parser.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell
from word_parser.discovery.indicators import IndicatorDiscovery, IndicatorLexicon, IndicatorValueParser
from word_parser.primary.normalizer import Normalizer
from word_parser.primary.candidate_resolver import CandidateResolver
from word_parser.primary.candidate_retriever import CandidateRetriever
from word_parser.primary.field_matcher import FieldMatcher
from word_parser.primary.value_extractor import ValueExtractor
from word_parser.output.json_exporter import JsonExporter
from word_parser.application.factory import create_default_parser
from word_parser.application import pipeline as pipeline_module


def test_table_indicator_fills_only_absent_exact_field():
    """结构化表格可为缺失的映射字段提供证据。"""
    fields = {"hubHeight": {"name": "轮毂高度", "aliases": ["轮毂高度"],
                             "value_type": "number", "standard_unit": "m", "unit_aliases": ["米"]}}
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="t1", order=0, page=3, section_path=["风机参数"], rows=[
            [TableCell("轮毂高度", 0, 0), TableCell("米", 0, 1), TableCell("120", 0, 2)],
        ],
    )])
    discovery = IndicatorDiscovery(fields)
    indicators = discovery.discover(ast)
    extractions = discovery.fallback_extractions(indicators, [])

    assert len(extractions) == 1
    assert extractions[0].raw_value == "120"
    assert extractions[0].evidence.table_id == "t1"
    assert extractions[0].evidence.page == 3
    assert discovery.fallback_extractions(indicators, extractions) == []

    normalized = Normalizer(fields).normalize_candidates(extractions)
    resolved = CandidateResolver(fields).resolve(normalized)

    class MappingSchema:
        """用于映射契约的小型输出结构。"""

        output_field_codes = {"hubHeight": "${hub_height}"}

        @staticmethod
        def _required_table_keys():
            return []

    exporter = JsonExporter(result_builder=MappingSchema())
    mapped = exporter._build_mapped_json({"fieldIndex": {
        "hubHeight": {"value": resolved["hubHeight"].value},
    }})
    assert mapped == {"${hub_height}": 120}


def test_appendix_indicator_can_hint_primary_across_section_boundary():
    """附表中的名称变体可以提示一次抽取，普通跨章节表格仍受章节限制。"""
    fields = {"avgWindSpeed": {
        "name": "平均风速", "aliases": ["平均风速"],
        "value_type": "number", "standard_unit": "m/s", "unit_aliases": ["m/s"],
        "sections": {"include": ["风资源"], "exclude": []},
    }}
    ast = DocumentAST(file_name="sample.pdf", tables=[
        DocumentTable(id="appendix", order=1, section_path=["附表"],
                      rows=[[TableCell("测风塔平均风速", 0, 0), TableCell("m/s", 0, 1), TableCell("6.42", 0, 2)]]),
        DocumentTable(id="other", order=2, section_path=["财务"],
                      rows=[[TableCell("测风塔平均风速", 0, 0), TableCell("m/s", 0, 1), TableCell("8.00", 0, 2)]]),
    ])
    discovery = IndicatorDiscovery(fields)
    hints = discovery.recall_hints(discovery.discover(ast))
    assert hints["avgWindSpeed"]["table"] == {"appendix"}


def test_unknown_indicator_is_retained_without_mapping():
    """字段词典之外的文档指标仍可供复核。"""
    discovery = IndicatorDiscovery({})
    ast = DocumentAST(file_name="sample.docx", blocks=[DocumentBlock(
        id="p1", type="paragraph", text="新指标：42 kV", order=0, page=2,
    )])

    indicators = discovery.discover(ast)

    assert len(indicators) == 1
    assert indicators[0].name == "新指标"
    assert indicators[0].field_code is None
    assert discovery.fallback_extractions(indicators, []) == []


def test_pre_scan_keeps_multiple_values_and_text_in_one_paragraph():
    """一个段落中的多项数值和文本属性都进入预抽取结果。"""
    discovery = IndicatorDiscovery({})
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
        id="p1", type="paragraph", text="装机容量为300MW，年发电量为600MWh；场址：河北省张家口市。",
        order=0, page=1,
    )])

    indicators = discovery.discover(ast)

    assert {(item.name, item.raw_value) for item in indicators} >= {
        ("装机容量", "300"), ("年发电量", "600"), ("场址", "河北省张家口市"),
    }
    assert all(item.block_id == "p1" for item in indicators)


def test_high_recall_keeps_discovered_candidate_for_covered_field():
    """一次抽取已有值时，预抽取的另一处证据仍可供规则选值。"""
    fields = {"hubHeight": {"name": "轮毂高度", "aliases": ["轮毂高度"],
                             "value_type": "number", "standard_unit": "m", "unit_aliases": ["米"]}}
    discovery = IndicatorDiscovery(fields)
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
        id="p1", type="paragraph", text="轮毂高度：120米", order=0, page=1,
    )])
    indicators = discovery.discover(ast)
    existing = discovery.fallback_extractions(indicators, [])

    assert discovery.fallback_extractions(indicators, existing) == []
    retained = discovery.fallback_extractions(indicators, existing, include_covered=True)
    assert len(retained) == 1
    assert retained[0].raw_value == "120"


def test_pre_scan_can_supply_an_exact_text_field():
    """文档中的短文本属性也可作为一次抽取候选。"""
    fields = {"site": {"name": "场址", "aliases": ["场址"], "value_type": "string"}}
    discovery = IndicatorDiscovery(fields)
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
        id="p1", type="paragraph", text="场址：河北省张家口市", order=0, page=1,
    )])

    extracted = discovery.fallback_extractions(discovery.discover(ast), [], include_covered=True)

    assert len(extracted) == 1
    assert extracted[0].raw_value == "河北省张家口市"
    assert extracted[0].evidence.block_id == "p1"


def test_primary_keeps_candidates_beyond_previous_top_k(tmp_path):
    """长文档中靠后的字段证据仍进入一次抽取候选池。"""
    ast = DocumentAST(file_name="sample.pdf", blocks=[
        DocumentBlock(id=f"p{index}", type="paragraph",
                      text=f"轮毂高度：{100 + index}米", order=index, page=index + 1)
        for index in range(35)
    ])

    class StaticLoader:
        @staticmethod
        def load(_path):
            return ast

    parser = create_default_parser()
    parser.pipeline.loader = StaticLoader()
    parser.pipeline.exporter.output_dir = tmp_path
    assert parser.pipeline.funnel_pruner.enabled is False

    parser.parse("sample.pdf")
    details = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    candidates = [item for item in details["extractionCandidates"]
                  if item["fieldCode"] == "hubHeight"]

    assert any(item["blockId"] == "p34" for item in candidates)
    assert len({item["blockId"] for item in candidates}) == 35




def test_ambiguous_exact_alias_does_not_fill_a_field():
    """多个字段共享的别名不能直接决定映射结果。"""
    lexicon = IndicatorLexicon({
        "a": {"name": "装机容量", "aliases": ["容量"]},
        "b": {"name": "单机容量", "aliases": ["容量"]},
    })

    assert lexicon.match("容量") == (None, "ambiguous", 100.0)
    assert lexicon.match("设计装机容量")[0] is None


def test_state_parser_handles_unit_after_value_and_second_column_label():
    """表格单元格中的单位可以位于数值任一侧。"""
    parser = IndicatorValueParser()

    assert parser.parse_table_row(["轮毂高度", "120", "米"]) == ("轮毂高度", "120", "米", 1)
    assert parser.parse_table_row(["项目", "轮毂高度", "米", "120"]) == ("轮毂高度", "120", "米", 3)
    assert parser.parse_paragraph("年上网发电量为120MWh") == ("年上网发电量", "120", "MWh")
    assert parser.parse_paragraph("年上网发电量为1,234.5MWh") == ("年上网发电量", "1234.5", "MWh")


def test_parallel_table_pairs_and_value_verb_are_discovered():
    """并列表格和“取”字句式无需新增字段规则也能形成观测。"""
    discovery = IndicatorDiscovery({
        "capacity": {"name": "装机容量", "value_type": "number", "standard_unit": "MW"},
        "height": {"name": "轮毂高度", "value_type": "number", "standard_unit": "m"},
        "rate": {"name": "保险费率", "value_type": "number", "standard_unit": "%"},
    })
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="t1", order=0, rows=[[
            TableCell("装机容量", 0, 0), TableCell("100MW", 0, 1),
            TableCell("轮毂高度", 0, 2), TableCell("120m", 0, 3),
        ]],
    )], blocks=[DocumentBlock(
        id="p1", type="paragraph", text="保险费率取0.25%", order=1,
    )])

    indicators = discovery.discover(ast)
    values = {(item.name, item.raw_value) for item in indicators}
    assert {("装机容量", "100"), ("轮毂高度", "120"), ("保险费率", "0.25")} <= values
    extracted = discovery.fallback_extractions(indicators, [])
    assert {item.field_code for item in extracted} == {"capacity", "height", "rate"}


def test_column_header_observations_keep_row_identity_without_scalar_backfill():
    """横向表格可以发现每列值，但多座测风塔不能误写成一个标量。"""
    discovery = IndicatorDiscovery({
        "density": {"name": "空气密度", "value_type": "number", "standard_unit": "kg/m³"},
    })
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="t1", order=0, rows=[
            [TableCell("测风塔编号", 0, 0), TableCell("高度（m）", 0, 1),
             TableCell("空气密度（kg/m³）", 0, 2)],
            [TableCell("0821#", 1, 0), TableCell("110", 1, 1), TableCell("1.05", 1, 2)],
            [TableCell("0822#", 2, 0), TableCell("120", 2, 1), TableCell("1.03", 2, 2)],
        ],
    )])

    indicators = discovery.discover(ast)
    densities = [item for item in indicators if item.name == "空气密度"]
    assert [(item.row_label, item.raw_value, item.unit) for item in densities] == [
        ("0821#", "1.05", "kg/m³"), ("0822#", "1.03", "kg/m³"),
    ]
    assert discovery.fallback_extractions(indicators, []) == []


def test_name_variant_locates_original_text_for_configured_primary_rule():
    """相似名称只指路；一次抽取必须在原文中命中明确规则。"""
    fields = {"capacity": {
        "name": "装机容量", "aliases": ["装机容量"], "standard_unit": "MW",
        "patterns": [r"装机设备容量[：:]\s*(\d+(?:\.\d+)?)\s*(MW)"],
    }}
    ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
        id="p1", type="paragraph", text="装机设备容量：100MW", order=1,
    )])
    discovery = IndicatorDiscovery(fields)
    indicators = discovery.discover(ast)
    assert indicators[0].match_method == "suggestion"
    assert CandidateRetriever(fields).retrieve(ast) == []

    hints = discovery.recall_hints(indicators)
    assert hints == {"capacity": {"paragraph": {"p1"}}}
    candidates = CandidateRetriever(fields).retrieve(ast, hints)
    assert candidates[0].meta["observation_hint"] is True
    extracted = ValueExtractor().extract(FieldMatcher().match(candidates))
    assert [(item.field_code, item.raw_value) for item in extracted] == [("capacity", "100")]

    fields["capacity"]["patterns"] = []
    assert ValueExtractor().extract(FieldMatcher().match(candidates)) == []


def test_unique_unit_confirmed_name_extension_can_fill_missing_field():
    """字段别名被普通修饰词包围时，单位和唯一性可以支持补漏。"""
    fields = {"roadLength": {
        "name": "进站道路", "aliases": ["进站道路"],
        "value_type": "number", "standard_unit": "km",
    }}
    discovery = IndicatorDiscovery(fields)
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="t1", order=0, rows=[
            [TableCell("新建进站道路长度", 0, 0), TableCell("km", 0, 1), TableCell("0.3", 0, 2)],
        ],
    )])

    indicators = discovery.discover(ast)
    assert indicators[0].match_method == "dictionary_suggestion"
    extracted = discovery.fallback_extractions(indicators, [])
    assert [(item.field_code, item.raw_value, item.debug["name_match"]) for item in extracted] == [
        ("roadLength", "0.3", "dictionary_contextual")
    ]
    resolved = CandidateResolver(fields).resolve(Normalizer(fields).normalize_candidates(extracted))
    assert resolved["roadLength"].value == 0.3


def test_containment_backfill_rejects_grade_scope_and_conflicting_values():
    """型号、单机口径以及不同取值不能靠词语包含关系自动归属。"""
    fields = {
        "concrete": {"name": "风机基础混凝土", "standard_unit": "m³"},
        "capacity": {"name": "装机容量", "standard_unit": "MW"},
        "roadLength": {"name": "进站道路", "standard_unit": "km"},
    }
    discovery = IndicatorDiscovery(fields)
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="t1", order=0, rows=[
            [TableCell("风机基础混凝土C40", 0, 0), TableCell("m³", 0, 1), TableCell("15325", 0, 2)],
            [TableCell("单机装机容量", 1, 0), TableCell("MW", 1, 1), TableCell("5", 1, 2)],
            [TableCell("新建进站道路长度", 2, 0), TableCell("km", 2, 1), TableCell("0.3", 2, 2)],
            [TableCell("新建进站道路长度", 3, 0), TableCell("km", 3, 1), TableCell("0.6", 3, 2)],
        ],
    )])

    assert discovery.fallback_extractions(discovery.discover(ast), []) == []


def test_contextual_paragraph_fills_label_inside_prose_with_original_evidence():
    fields = {"capacity": {"name": "装机容量", "aliases": ["装机容量"],
                           "value_type": "number", "standard_unit": "MW"}}
    discovery = IndicatorDiscovery(fields)
    sentence = "根据建设方案，本项目装机容量为100MW，拟分期建设。"
    ast = DocumentAST(file_name="sample.docx", blocks=[DocumentBlock(
        id="p1", type="paragraph", text=sentence, order=1, page=4,
    )])

    extracted = discovery.fallback_extractions(discovery.discover(ast), [])

    assert len(extracted) == 1
    assert extracted[0].field_code == "capacity"
    assert extracted[0].raw_value == "100"
    assert extracted[0].evidence.text == sentence
    assert extracted[0].evidence.page == 4


def test_contextual_paragraph_rejects_changed_scope_and_missing_relation():
    fields = {"capacity": {"name": "装机容量", "aliases": ["装机容量"],
                           "value_type": "number", "standard_unit": "MW"}}
    discovery = IndicatorDiscovery(fields)
    for sentence in ("单机装机容量为5MW。", "本项目装机容量约100MW。"):
        ast = DocumentAST(file_name="sample.docx", blocks=[DocumentBlock(
            id="p1", type="paragraph", text=sentence, order=1,
        )])
        assert discovery.fallback_extractions(discovery.discover(ast), []) == []


def test_adjacent_paragraphs_require_layout_proximity():
    """PDF 坐标可防止无关的数字段落被配对。"""
    parser = IndicatorValueParser()
    label = DocumentBlock(id="p1", type="paragraph", text="轮毂高度：", order=1, page=2,
                          meta={"bounding_box": [10, 10, 80, 25]})
    close = DocumentBlock(id="p2", type="paragraph", text="120米", order=2, page=2,
                          meta={"bounding_box": [10, 30, 80, 45]})
    far = DocumentBlock(id="p3", type="paragraph", text="120米", order=2, page=2,
                        meta={"bounding_box": [10, 200, 80, 215]})

    assert parser.parse_adjacent_blocks(label, close) == ("轮毂高度", "120", "米")
    assert parser.parse_adjacent_blocks(label, far) is None


def test_high_confidence_typo_fills_missing_mapped_field():
    """唯一的一字之差可补充缺失的映射字段。"""
    name = "华北地区大型风电场项目一期工程全年预计上网发电总量"
    observed = name.replace("预计", "预记")
    config = {"annualEnergy": {"name": name, "aliases": ["上网发电总量"],
                               "value_type": "number", "standard_unit": "MWh"}}
    ast = DocumentAST(file_name="sample.docx", blocks=[DocumentBlock(
        id="p1", type="paragraph", text=f"{observed}：120MWh", order=1,
    )])
    discovery = IndicatorDiscovery(config)
    indicators = discovery.discover(ast)

    assert indicators[0].match_method == "rapidfuzz"
    assert indicators[0].similarity >= 96
    assert indicators[0].field_code is None
    assert indicators[0].suggested_field_code == "annualEnergy"
    extracted = discovery.fallback_extractions(indicators, [])
    assert len(extracted) == 1
    assert extracted[0].field_code == "annualEnergy"
    assert extracted[0].debug["name_match"] == "rapidfuzz"
    assert discovery.fallback_extractions(indicators, extracted) == []

    normalized = Normalizer(config).normalize_candidates(extracted)
    resolved = CandidateResolver(config).resolve(normalized)

    class MappingSchema:
        """模糊匹配候选值所需的最小映射契约。"""

        output_field_codes = {"annualEnergy": "${annual_energy}"}

        @staticmethod
        def _required_table_keys():
            return []

    mapped = JsonExporter(result_builder=MappingSchema())._build_mapped_json({"fieldIndex": {
        "annualEnergy": {"value": resolved["annualEnergy"].value},
    }})
    assert mapped == {"${annual_energy}": 120}


def test_fuzzy_match_rejects_changed_scope_unit_and_excluded_section():
    """名称相似度高也不能覆盖字段语义或单位约束。"""
    name = "华北地区大型风电场项目一期工程单机额定装机容量"
    config = {"capacity": {"name": name, "value_type": "number", "standard_unit": "MW",
                           "sections": {"include": ["风机参数"], "exclude": ["财务评价"]}}}
    discovery = IndicatorDiscovery(config)

    def candidates(label, unit="MW", section=None):
        ast = DocumentAST(file_name="sample.pdf", blocks=[DocumentBlock(
            id="p1", type="paragraph", text=f"{label}：12{unit}", order=1,
            section_path=section or [],
        )])
        return discovery.fallback_extractions(discovery.discover(ast), [])

    assert candidates(name.replace("单机", "双机")) == []
    assert candidates(name.replace("额定", "额订"), unit="kV") == []
    assert candidates(name.replace("额定", "额订"), unit="") == []
    assert candidates(name.replace("额定", "额订"), section=["财务评价"]) == []
    assert candidates(name.replace("额定", "额订"), section=["其他章节"]) == []
    assert len(candidates(name.replace("额定", "额订"), section=["风机参数"])) == 1


def test_discovered_value_reaches_existing_mapped_output(tmp_path, monkeypatch):
    """漏识别的已知表格值仍走正常的映射和单位处理流程。"""
    ast = DocumentAST(file_name="sample.pdf", tables=[DocumentTable(
        id="table_1", order=0, page=2, rows=[
            [TableCell("年上网发电量", 0, 0), TableCell("MWh", 0, 1), TableCell("120", 0, 2)],
        ],
    )])

    class StaticLoader:
        """提供已解析文档，避免依赖 PDF 软件。"""

        @staticmethod
        def load(_path):
            return ast

    parser = create_default_parser()
    parser.pipeline.loader = StaticLoader()
    parser.pipeline.value_extractor.table_rule_enabled = False
    parser.pipeline.value_extractor.regex_enabled = False
    parser.pipeline.exporter.output_dir = tmp_path

    class LogCollector:
        """捕获流水线阶段摘要，不修改组件日志。"""

        def __init__(self):
            self.messages = []

        def info(self, message):
            self.messages.append(message)

    log = LogCollector()
    monkeypatch.setattr(pipeline_module, "logger", log)

    active_discovery = parser.pipeline.indicator_discovery
    assert active_discovery.mode == "active"
    parser.pipeline.indicator_discovery = None
    original_result = parser.parse("sample.pdf")
    parser.pipeline.indicator_discovery = active_discovery
    parser.pipeline.indicator_discovery.mode = "shadow"
    shadow_result = parser.parse("sample.pdf")
    assert shadow_result["mapped"] == original_result["mapped"]

    parser.pipeline.indicator_discovery.mode = "active"
    result = parser.parse("sample.pdf")

    assert result["mapped"]["${projectSelectedDeviceYearPower}"] == 12
    assert (tmp_path / "sample_mapped.json").exists()
    details = json.loads((tmp_path / "sample_details.json").read_text(encoding="utf-8"))
    assert details["discoveredIndicators"][0]["table_id"] == "table_1"
    assert any("阶段=词典匹配" in message and "精确=1" in message for message in log.messages)
    assert any("阶段=字段相似度" in message and "模式=RapidFuzz" in message for message in log.messages)
    assert any("阶段=映射输出" in message and "非空=" in message for message in log.messages)
