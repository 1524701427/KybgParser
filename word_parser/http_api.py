"""历史 HTTP 入口兼容模块，新代码使用 ``word_parser.application.http_api``。"""

from __future__ import annotations

import sys

from word_parser.application import http_api as _implementation


# 让旧模块名直接指向同一个模块对象，确保依赖覆盖和测试 monkeypatch 行为不变。
sys.modules[__name__] = _implementation
