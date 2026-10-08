"""对已有 result.json 执行表内字段二次抽取。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    # 独立运行 tools/scripts 下脚本时，显式把项目根目录加入导入路径。
    sys.path.insert(0, str(ROOT))

from parser_engine.tables.table_values import default_table_value_details_path, enhance_result_file


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="基于 result.json 合并二次抽取结果。")
    parser.add_argument("--input", required=True, help="主解析链路导出的 result.json 路径。")
    parser.add_argument("--output", help="最终 result.json 输出路径，默认回写 --input。")
    parser.add_argument("--details-output", help="二次抽取过程明细输出路径，默认追加到同目录 *_details.json。")
    parser.add_argument("--config", default="configs/table_field_extractors.yaml", help="二次抽取配置文件路径。")
    return parser.parse_args()


def main() -> None:
    """执行二次抽取并打印摘要。"""
    args = parse_args()
    enhanced = enhance_result_file(args.input, args.output, args.config, args.details_output)
    summary = enhanced.get("tableValueExtraction", {}).get("summary", {})
    output_path = Path(args.output) if args.output else Path(args.input)
    details_path = Path(args.details_output) if args.details_output else default_table_value_details_path(args.input)
    print(json.dumps({"output": str(output_path), "details": str(details_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
