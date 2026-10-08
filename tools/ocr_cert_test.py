"""Manual PaddleOCR probe for consulting certificate images.

Usage:
    python tools\\ocr_cert_test.py C:\\path\\to\\certificate.png

If no path is provided, the script tries cert_test.png in the project root.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from importlib import metadata
from pathlib import Path
from pprint import pprint

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser_engine.output.cover_ocr import CoverOcrExtractor


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="手动测试单张证书图片的 OCR 和规则抽取结果。")
    parser.add_argument("image", nargs="?", default="cert_test.png", help="证书图片路径，默认 cert_test.png。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = Path(args.image)
    image_path = image_path.expanduser().resolve()

    print(f"python = {sys.executable}")
    print(f"python_version = {sys.version}")
    for package in ("paddleocr", "paddlepaddle", "paddlex", "opencv-python", "numpy"):
        try:
            print(f"{package} = {metadata.version(package)}")
        except metadata.PackageNotFoundError:
            print(f"{package} = NOT INSTALLED")

    print(f"image_exists = {image_path.exists()}")
    print(f"image_path = {image_path}")
    if not image_path.exists():
        print("Image file not found. Pass the image path as the first argument.")
        return 1

    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        print(f"paddleocr_import_failed = {exc!r}")
        traceback.print_exc()
        return 1

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    except Exception as exc:
        print(f"init_with_show_log_failed = {exc!r}")
        try:
            ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        except Exception as fallback_exc:
            print(f"init_without_show_log_failed = {fallback_exc!r}")
            traceback.print_exc()
            return 1

    try:
        raw = ocr.ocr(str(image_path), cls=True)
    except TypeError:
        raw = ocr.ocr(str(image_path))

    print("\n=== RAW OCR RESULT ===")
    pprint(raw)

    extractor = CoverOcrExtractor()
    lines = extractor._flatten_ocr_result(raw)
    text = extractor._normalize_ocr_text("\n".join(lines))

    print("\n=== OCR LINES ===")
    for index, line in enumerate(text.splitlines(), start=1):
        print(f"{index:02d}: {line}")

    print("\n=== PROJECT RULE RESULT ===")
    normalized_for_grade = extractor._normalize_grade_ocr_text("".join(text.split()))
    print(f"gradeNormalizedText = {normalized_for_grade}")
    print(f"designUnit = {extractor._design_unit_from_ocr(text)}")
    print(f"designUnitQualification = {extractor._design_unit_qualification_from_ocr(text)}")
    print("commonFields =")
    pprint(extractor._extract_common_fields(text))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
