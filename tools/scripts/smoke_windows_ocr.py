"""Run a real Windows RapidOCR inference through KybgParser's cover OCR path.

This tests installed OCR engine execution, not field accuracy on real reports.
Run on Windows with pip install rapidocr onnxruntime pillow loguru.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import os
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    from PIL import Image, ImageDraw, ImageFont
    from word_parser.document.cover_ocr import CoverOcrExtractor

    font_root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    font_path = next((p for p in (font_root / "arial.ttf", font_root / "calibri.ttf")
                      if p.exists()), None)
    if font_path is None:
        raise RuntimeError("Windows OCR smoke image font not found")
    image = Image.new("RGB", (1100, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 50), "Wind Power 200 MW", font=ImageFont.truetype(str(font_path), 64),
              fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    extractor = CoverOcrExtractor()
    lines = extractor._ocr_image(buffer.getvalue(), "ocr-smoke.png")
    print("Platform:", platform.platform())
    print("OCR recognized lines:", lines)
    if not lines or not any("200" in item for item in lines):
        raise RuntimeError("OCR inference did not return expected visible number 200")
    if extractor._rapid_ocr is None:
        raise RuntimeError("RapidOCR engine did not load; check optional OCR dependencies")
    print("Windows RapidOCR smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
