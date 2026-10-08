"""无参执行主解析，并基于 result.json 继续做表内字段二次抽取。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    # 直接运行 tools/scripts 下脚本时，先把项目根目录加入导入路径。
    sys.path.insert(0, str(ROOT))

from main import parse_document
from parser_engine.tables.table_values import enhance_result_file


DOCX_PATH = str(ROOT / "samples" / "reports" / "5.陕西华电咸阳永寿常宁镇10万千瓦风电项目可行性研究报告.docx")
TABLE_VALUE_CONFIG = ROOT / "configs" / "table_field_extractors.yaml"


def run() -> dict:
    """先运行主解析，再对主解析生成的 result.json 执行二次抽取。"""
    # import os
    # os.environ["COVER_OCR_DEBUG_DIR"] = str(ROOT / "data" / "debug-images")

    parse_result = parse_document(DOCX_PATH)
    output_files = parse_result.get("outputFiles", {}) or {}
    result_path = output_files.get("result")
    if not result_path:
        raise RuntimeError("主解析结果中没有 outputFiles.result，无法执行二次抽取。")

    enhanced = enhance_result_file(result_path, config_path=TABLE_VALUE_CONFIG)
    details_path = Path(result_path).with_name(Path(result_path).stem.replace("_result", "") + "_details.json")
    summary = enhanced.get("tableValueExtraction", {}).get("summary", {})
    return {
        "outputFiles": {**output_files, "detail": str(details_path)},
        "detail": str(details_path),
        "tableValueSummary": summary,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
