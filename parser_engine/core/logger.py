"""中文日志工具。

优先使用 loguru；如果环境未安装 loguru，则退回标准库 logging。
"""

from __future__ import annotations

import logging


def _build_std_logger():
    """创建标准库日志器。

    Returns:
        logging.Logger: 标准库日志器。
    """
    logger = logging.getLogger("word_parser")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


try:
    from loguru import logger as logger  # type: ignore
except Exception:  # pragma: no cover - 只在缺少 loguru 时触发
    logger = _build_std_logger()
