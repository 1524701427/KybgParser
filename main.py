"""项目级可导入入口。

这个文件保留给 PyCharm、Notebook 或本地命令行直接使用。
业务代码优先从 word_parser.core 导入同名函数。
例如：

    from main import create_parser

    parser = create_parser()
    result = parser.parse(r"C:/path/to/report.docx")
"""

import json
import sys
from pathlib import Path

from word_parser.core import create_parser, enhance_parse_result, parse_document, parse_document_with_table_values


def default_document_path() -> str:
    """返回 main.py 直接运行时使用的默认文档路径。

    优先使用 Downloads 里的文件；如果样例文档已经放在 samples/reports，
    则自动回退到样例目录，避免本地路径变化导致入口直接报错。
    """
    file_name = '陕西华电靖边韩家沟200MW风电项目可行性研究报告.doc'
    preferred = Path(r"C:\Users\EDY\Downloads") / file_name
    if preferred.exists():
        return str(preferred)

    root = Path(__file__).resolve().parent
    for local_copy in (root / "samples" / "reports" / file_name, root / file_name):
        if local_copy.exists():
            return str(local_copy)

    raise FileNotFoundError(f"默认测试文档不存在：{preferred}；samples/reports 也未找到同名文件")


if __name__ == '__main__':
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = parse_document_with_table_values(default_document_path())
    print(json.dumps({"outputFiles": res.get("outputFiles", {}), "tableValueSummary": res.get("tableValueSummary", {})}, ensure_ascii=False, indent=2))
