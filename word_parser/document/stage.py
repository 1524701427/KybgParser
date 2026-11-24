from __future__ import annotations

from time import perf_counter
from word_parser.document.structure_index import build_structure_index

def read_document(parser, ctx) -> None:
    stage_started = perf_counter()
    ctx.ast = parser.loader.load(ctx.file_path)
    parser._log_stage("文档加载", stage_started, 段落块=len(ctx.ast.blocks), 表格=len(ctx.ast.tables))

    stage_started = perf_counter()
    ctx.ast = parser.structure_parser.parse(ctx.ast)
    ctx.ast = parser.section_detector.detect(ctx.ast)
    policy = getattr(parser.structure_parser, "policy", None)
    if policy is not None:
        snapshot = build_structure_index(ctx.ast, policy)
        if snapshot is not None:
            ctx.ast.meta["structure_index"] = snapshot
    parser._log_stage("结构与章节识别", stage_started, 段落块=len(ctx.ast.blocks), 表格=len(ctx.ast.tables))

