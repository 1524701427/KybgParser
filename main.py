"""项目命令行入口，同时保留供旧调用方导入的 Python 函数。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from word_parser.core import create_parser, enhance_parse_result, parse_document, parse_document_with_table_values


def main(argv: list[str] | None = None) -> int:
    """解析命令行指定的报告，并打印输出文件路径与二次抽取摘要。"""
    parser = argparse.ArgumentParser(description="解析风电可研 Word/PDF 报告")
    parser.add_argument("report", nargs="?", type=Path, help="待解析的 .doc、.docx 或 .pdf 文件；不填时交互输入")
    parser.add_argument("--config-root", type=Path, default=Path("configs"), help="配置目录，默认：configs")
    parser.add_argument("--primary-only", action="store_true", help="只执行前置扫描和一次抽取")
    args = parser.parse_args(argv)

    report_path = args.report
    if report_path is None:
        try:
            entered = input("请输入报告路径（可将文件拖入终端）：").strip().strip('"').strip("'")
        except (EOFError, KeyboardInterrupt):
            print("\n未提供报告路径。用法：python main.py <报告路径>", file=sys.stderr)
            return 2
        if not entered:
            print("未提供报告路径。用法：python main.py <报告路径>", file=sys.stderr)
            return 2
        report_path = Path(entered)

    report = report_path.expanduser().resolve()
    if not report.is_file():
        parser.error(f"报告文件不存在：{report}")
    if report.suffix.lower() not in {".doc", ".docx", ".pdf"}:
        parser.error(f"不支持的报告格式：{report.suffix}")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.primary_only:
        result = parse_document(str(report), config_root=args.config_root)
    else:
        table_config = args.config_root / "table_field_extractors.yaml"
        result = parse_document_with_table_values(
            str(report), config_root=args.config_root, table_value_config=table_config
        )
    print(json.dumps({
        "outputFiles": result.get("outputFiles", {}),
        "tableValueSummary": result.get("tableValueSummary", {}),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
