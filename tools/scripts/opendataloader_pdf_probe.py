"""OpenDataLoader PDF 解析探针脚本。

这个脚本是独立调试工具，不接入主解析流水线。它直接调用
``opendataloader_pdf.convert`` 解析 PDF，并额外生成便于人工检查的
summary/report，重点观察段落、题注、表格、bbox 和表前候选标题。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def main() -> None:
    """解析命令行参数并执行 PDF 探针。"""
    args = parse_args()
    input_path = Path(args.input_pdf).resolve()
    if input_path.suffix.lower() != ".pdf":
        raise SystemExit(f"只支持 PDF 文件：{input_path}")
    if not input_path.exists():
        raise SystemExit(f"文件不存在：{input_path}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_json_path = run_opendataloader(
        input_path=input_path,
        output_dir=output_dir,
        table_method=args.table_method,
        reading_order=args.reading_order,
        image_output=args.image_output,
        quiet=not args.verbose,
    )
    data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    summary = build_summary(data, max_table_rows=args.max_table_rows)

    copied_raw_json = output_dir / "raw_opendataloader.json"
    if raw_json_path.resolve() != copied_raw_json.resolve():
        shutil.copyfile(raw_json_path, copied_raw_json)

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_markdown_report(input_path, summary), encoding="utf-8")

    print(f"OpenDataLoader 原始 JSON: {copied_raw_json}")
    print(f"解析摘要 JSON: {summary_path}")
    print(f"人工检查报告: {report_path}")


def parse_args() -> argparse.Namespace:
    """定义脚本命令行参数。"""
    parser = argparse.ArgumentParser(description="用 opendataloader-pdf 解析 PDF 并输出结构检查报告。")
    parser.add_argument("input_pdf", help="待解析的 PDF 文件路径。")
    parser.add_argument("-o", "--output-dir", help="输出目录；默认写入 data/opendataloader_probe/<pdf_stem>。")
    parser.add_argument("--table-method", default="cluster", help="OpenDataLoader 表格解析方法，默认 cluster。")
    parser.add_argument("--reading-order", default="xycut", help="OpenDataLoader 阅读顺序方法，默认 xycut。")
    parser.add_argument("--image-output", default="off", help="图片输出策略，默认 off。")
    parser.add_argument("--max-table-rows", type=int, default=8, help="报告里每张表最多预览多少行。")
    parser.add_argument("--verbose", action="store_true", help="显示 OpenDataLoader 解析日志。")
    return parser.parse_args()


def default_output_dir(input_path: Path) -> Path:
    """根据 PDF 文件名生成默认输出目录。"""
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_.-]+", "_", input_path.stem).strip("_") or "pdf"
    return Path("data") / "opendataloader_probe" / safe_name


def run_opendataloader(
    input_path: Path,
    output_dir: Path,
    table_method: str,
    reading_order: str,
    image_output: str,
    quiet: bool,
) -> Path:
    """调用 opendataloader_pdf.convert 并返回生成的 JSON 路径。"""
    try:
        from opendataloader_pdf import convert  # type: ignore
    except Exception as exc:
        raise RuntimeError("缺少 opendataloader-pdf，请先安装 requirements.txt。") from exc

    convert(
        input_path=str(input_path),
        output_dir=str(output_dir),
        format="json",
        quiet=quiet,
        table_method=table_method,
        reading_order=reading_order,
        image_output=image_output,
    )
    return find_output_json(output_dir, input_path)


def find_output_json(output_dir: Path, input_path: Path) -> Path:
    """查找 OpenDataLoader 生成的 JSON 文件。"""
    direct = output_dir / f"{input_path.stem}.json"
    if direct.exists():
        return direct
    matches = sorted(output_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    raise RuntimeError(f"OpenDataLoader 未生成 JSON：{output_dir}")


def build_summary(data: dict[str, Any], max_table_rows: int) -> dict[str, Any]:
    """把 OpenDataLoader 原始 JSON 转成便于检查的摘要。"""
    nodes = list(data.get("kids") or [])
    type_counts = Counter(str(node.get("type") or "unknown").lower() for node in nodes)
    pages: dict[int | str, list[dict[str, Any]]] = defaultdict(list)
    caption_by_target = caption_links(nodes)
    previous_text_by_page: dict[int | str, list[dict[str, Any]]] = defaultdict(list)

    tables: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    paragraphs: list[dict[str, Any]] = []

    for index, node in enumerate(nodes):
        node_type = str(node.get("type") or "unknown").lower()
        page = page_number(node)
        item = base_node_summary(node, index)

        if node_type == "table":
            table = table_summary(node, caption_by_target, previous_text_by_page.get(page, []), max_table_rows)
            item.update(table)
            tables.append(item)
        elif node_type == "caption":
            item["text"] = clean_text(str(node.get("content") or ""))
            item["linkedContentId"] = node.get("linked content id")
            captions.append(item)
            previous_text_by_page[page].append(item)
        elif node_type == "paragraph":
            item["text"] = clean_text(str(node.get("content") or ""))
            item["looksLikeTitle"] = looks_like_table_title(item["text"])
            paragraphs.append(item)
            previous_text_by_page[page].append(item)
        else:
            item["text"] = clean_text(str(node.get("content") or ""))

        pages[page].append(item)

    return {
        "typeCounts": dict(type_counts),
        "pageCount": len(pages),
        "pages": {str(page): items for page, items in sorted(pages.items(), key=lambda pair: str(pair[0]))},
        "captions": captions,
        "paragraphs": paragraphs,
        "tables": tables,
    }


def base_node_summary(node: dict[str, Any], index: int) -> dict[str, Any]:
    """提取所有节点共有的摘要字段。"""
    return {
        "index": index,
        "id": node.get("id"),
        "type": node.get("type"),
        "page": page_number(node),
        "bbox": node.get("bounding box"),
    }


def caption_links(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """提取 caption 到 linked content id 的映射。"""
    links: dict[str, str] = {}
    for node in nodes:
        if str(node.get("type") or "").lower() != "caption":
            continue
        target_id = node.get("linked content id")
        text = clean_text(str(node.get("content") or ""))
        if target_id is not None and text:
            links[str(target_id)] = text
    return links


def table_summary(
    node: dict[str, Any],
    caption_by_target: dict[str, str],
    previous_text_items: list[dict[str, Any]],
    max_table_rows: int,
) -> dict[str, Any]:
    """提取单张表格的矩阵、题注和表前候选标题。"""
    matrix = table_matrix(node)
    linked_caption = caption_by_target.get(str(node.get("id")))
    nearby_titles = nearby_title_candidates(previous_text_items)
    caption = linked_caption or (nearby_titles[0]["text"] if nearby_titles else "")
    return {
        "caption": caption,
        "linkedCaption": linked_caption,
        "nearbyTitleCandidates": nearby_titles,
        "rowCount": len(matrix),
        "columnCount": max((len(row) for row in matrix), default=0),
        "previewRows": matrix[:max_table_rows],
    }


def table_matrix(node: dict[str, Any]) -> list[list[str]]:
    """从 OpenDataLoader table 节点中抽取二维文本矩阵。"""
    matrix: list[list[str]] = []
    for row in node.get("rows") or []:
        cells = row.get("cells") or []
        parsed = [cell_text(cell) for cell in cells]
        if any(parsed):
            matrix.append(parsed)
    max_cols = max((len(row) for row in matrix), default=0)
    return [row + [""] * (max_cols - len(row)) for row in matrix]


def cell_text(cell: dict[str, Any]) -> str:
    """读取单元格 kids 中的文本。"""
    parts: list[str] = []
    for kid in cell.get("kids") or []:
        text = clean_text(str(kid.get("content") or ""))
        if text:
            parts.append(text)
    return clean_text(" ".join(parts))


def nearby_title_candidates(items: list[dict[str, Any]], window: int = 8) -> list[dict[str, Any]]:
    """从同页表前文本中筛出疑似表题。"""
    candidates: list[dict[str, Any]] = []
    for distance, item in enumerate(reversed(items[-window:]), start=1):
        text = clean_text(item.get("text") or "")
        if not text:
            continue
        score = score_title_text(text, distance, item)
        if score <= 0:
            continue
        candidates.append({"text": text, "score": score, "sourceType": item.get("type"), "id": item.get("id"), "distance": distance, "bbox": item.get("bbox")})
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def score_title_text(text: str, distance: int, item: dict[str, Any]) -> float:
    """用轻量规则给表前标题候选打分。"""
    score = 0.0
    if str(item.get("type") or "").lower() == "caption":
        score += 3.0
    if looks_like_table_title(text):
        score += 2.0
    if len(text) <= 80:
        score += 0.5
    if distance <= 2:
        score += 0.8
    elif distance <= 5:
        score += 0.3
    if text.endswith(("。", "；", ";")):
        score -= 2.0
    return round(score, 3)


def looks_like_table_title(text: str) -> bool:
    """判断文本是否像表题。"""
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) > 120:
        return False
    if re.search(r"^(?:附表|表|Table)\s*[\d一二三四五六七八九十A-Za-z.\-－]+", cleaned, flags=re.IGNORECASE):
        return True
    return any(keyword in cleaned for keyword in ("表", "清单", "工程量", "概算", "估算", "汇总", "统计", "成果", "计算", "参数", "材料", "设备"))


def page_number(node: dict[str, Any]) -> int | str:
    """读取页码，无法解析时返回 unknown。"""
    value = node.get("page number")
    try:
        return int(value) if value is not None else "unknown"
    except (TypeError, ValueError):
        return "unknown"


def clean_text(text: str) -> str:
    """清理控制字符和重复空白。"""
    return re.sub(r"\s+", " ", str(text or "").replace("\x00", " ")).strip()


def build_markdown_report(input_path: Path, summary: dict[str, Any]) -> str:
    """把摘要转换成人工检查用 Markdown 报告。"""
    lines: list[str] = []
    lines.append(f"# OpenDataLoader PDF Probe")
    lines.append("")
    lines.append(f"- 文件: `{input_path}`")
    lines.append(f"- 页数: {summary['pageCount']}")
    lines.append(f"- 节点统计: `{summary['typeCounts']}`")
    lines.append("")

    lines.append("## 表格清单")
    lines.append("")
    for table_index, table in enumerate(summary["tables"], start=1):
        lines.append(f"### Table {table_index}: id={table.get('id')} page={table.get('page')}")
        lines.append(f"- bbox: `{table.get('bbox')}`")
        lines.append(f"- caption: {table.get('caption') or ''}")
        lines.append(f"- linkedCaption: {table.get('linkedCaption') or ''}")
        lines.append(f"- rows/cols: {table.get('rowCount')} / {table.get('columnCount')}")
        if table.get("nearbyTitleCandidates"):
            lines.append("- nearbyTitleCandidates:")
            for candidate in table["nearbyTitleCandidates"][:5]:
                lines.append(f"  - score={candidate['score']} distance={candidate['distance']} text={candidate['text']}")
        lines.append("")
        lines.append("```text")
        for row in table.get("previewRows") or []:
            lines.append(" | ".join(str(cell) for cell in row))
        lines.append("```")
        lines.append("")

    lines.append("## 按页节点")
    lines.append("")
    for page, items in summary["pages"].items():
        lines.append(f"### Page {page}")
        for item in items:
            text = item.get("text") or item.get("caption") or ""
            preview = clean_text(text)[:120]
            extra = ""
            if item.get("type") == "table":
                extra = f" rows={item.get('rowCount')} cols={item.get('columnCount')} caption={item.get('caption') or ''}"
            lines.append(f"- `{item.get('type')}` id={item.get('id')} bbox=`{item.get('bbox')}`{extra} {preview}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
