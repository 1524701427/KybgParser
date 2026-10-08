
"""Cover-page image OCR helpers for common project metadata."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from parser_engine.document.ast.document import DocumentAST
from parser_engine.core.logger import logger
from parser_engine.document.loaders.aspose_loader import AsposeWordsLoader


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NAMESPACE = {"w": W_NS, "r": R_NS, "a": A_NS, "rel": REL_NS}


@dataclass
class CoverOcrResult:
    values: dict[str, str]
    text: str
    image_count: int


class CoverOcrExtractor:
    """OCR only images that appear before the table of contents."""

    def __init__(
        self,
        ocr_runner: Callable[[bytes, str], list[str]] | None = None,
        max_images: int = 32,
        min_image_bytes: int = 4096,
        debug_save_dir: str | Path | None = None,
    ):
        self.ocr_runner = ocr_runner
        self.max_images = self._env_int("COVER_OCR_MAX_IMAGES", max_images)
        self.min_image_bytes = self._env_int("COVER_OCR_MIN_IMAGE_BYTES", min_image_bytes)
        debug_dir = debug_save_dir or os.getenv("COVER_OCR_DEBUG_DIR")
        self.debug_save_dir = Path(debug_dir) if debug_dir else None
        self._paddle_ocr: Any | None = None
        self._paddle_ocr_unavailable = False
        self._rapid_ocr: Any | None = None
        self._rapid_ocr_unavailable = False

    def extract(self, file_path: str | None, ast: DocumentAST | None = None) -> CoverOcrResult:
        if not file_path:
            logger.info("Cover OCR skipped: no source file path")
            return CoverOcrResult(values={}, text="", image_count=0)
        images = self._images_before_toc(file_path, ast)
        if not images:
            logger.info(f"Cover OCR skipped: no images before TOC in {Path(file_path).name}")
            return CoverOcrResult(values={}, text="", image_count=0)

        logger.info(f"Cover OCR scanning {min(len(images), self.max_images)} / {len(images)} images before TOC")
        lines: list[str] = []
        
        processed_count = min(len(images), self.max_images)
        for index, (name, content) in enumerate(images[: processed_count], start=1):
            self._save_debug_image(index, name, content)
            try:
                lines.extend(self._ocr_image(content, name))
            except Exception as exc:  # pragma: no cover - defensive fallback for optional OCR engines
                logger.warning(f"Cover OCR failed for image {index} ({name}): {exc}")
        text = self._normalize_ocr_text("\n".join(lines))
        values = self._extract_common_fields(text, ast if text else None)
        if text:
            preview = " | ".join(text.splitlines()[:12])
            logger.info(f"Cover OCR text preview: {preview[:500]}")
        logger.info(f"Cover OCR finished: lines={len(text.splitlines())}, fields={sorted(values)}")
        return CoverOcrResult(values=values, text=text, image_count=processed_count)

    def _images_before_toc(self, file_path: str, ast: DocumentAST | None = None) -> list[tuple[str, bytes]]:
        path = Path(file_path)
        if not path.exists():
            return []
        if path.suffix.lower() == ".pdf":
            return self._pdf_page_images_before_toc(path, ast)
        if path.suffix.lower() == ".doc":
            return self._legacy_doc_images_before_toc(path, ast)
        if path.suffix.lower() != ".docx":
            return []
        return self._docx_images_before_toc(path)

    def _docx_images_before_toc(self, path: Path) -> list[tuple[str, bytes]]:
        try:
            with zipfile.ZipFile(path) as package:
                document_xml = package.read("word/document.xml")
                rels = self._document_relationships(package)
                image_targets = self._image_targets_before_toc(document_xml, rels)
                images: list[tuple[str, bytes]] = []
                seen: set[str] = set()
                for target in image_targets:
                    if target in seen:
                        continue
                    seen.add(target)
                    try:
                        content = package.read(target)
                    except KeyError:
                        continue
                    if len(content) < self.min_image_bytes:
                        continue
                    images.append((target, content))
                return images
        except Exception as exc:
            logger.warning(f"Cover OCR image extraction skipped: {exc}")
            return []

    def _legacy_doc_images_before_toc(self, path: Path, ast: DocumentAST | None = None) -> list[tuple[str, bytes]]:
        loader = AsposeWordsLoader()
        runtime = loader._load_aspose_runtime()
        if runtime is None:
            logger.warning("Cover OCR legacy .doc image extraction skipped: Aspose runtime is unavailable")
            return []
        _mode, aw = runtime
        try:
            with tempfile.TemporaryDirectory(prefix="cover_ocr_doc_") as temp_dir:
                converted = Path(temp_dir) / f"{path.stem}.docx"
                doc = aw.Document(str(path))
                if hasattr(doc, "save"):
                    doc.save(str(converted))
                else:
                    doc.Save(str(converted))
                return self._docx_images_before_toc(converted)
        except Exception as exc:
            logger.warning(f"Cover OCR legacy .doc image extraction skipped: {exc}")
            return []

    def _pdf_page_images_before_toc(self, path: Path, ast: DocumentAST | None = None) -> list[tuple[str, bytes]]:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            logger.warning(f"PDF cover OCR skipped: PyMuPDF is unavailable: {exc}")
            return []
        self._quiet_mupdf_warnings(fitz)
        try:
            with fitz.open(path) as doc:
                toc_page = self._toc_page_from_ast(ast) or self._toc_page_from_pdf(doc)
                page_count = self._pdf_cover_page_count(doc.page_count, toc_page)
                images: list[tuple[str, bytes]] = []
                for page_index in range(page_count):
                    page = doc.load_page(page_index)
                    if self._is_pdf_text_page_without_images(page):
                        continue
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    content = pix.tobytes("png")
                    if len(content) < self.min_image_bytes:
                        continue
                    images.append((f"pdf_page_{page_index + 1:03d}.png", content))
                    if len(images) >= self.max_images:
                        break
                return images
        except Exception as exc:
            logger.warning(f"PDF cover OCR image extraction skipped: {exc}")
            return []

    def _quiet_mupdf_warnings(self, fitz_module: Any) -> None:
        tools = getattr(fitz_module, "TOOLS", None)
        if tools is None:
            return
        for method_name in ("mupdf_display_errors", "mupdf_display_warnings"):
            method = getattr(tools, method_name, None)
            if method is None:
                continue
            try:
                method(False)
            except Exception:
                continue

    def _toc_page_from_ast(self, ast: DocumentAST | None) -> int | None:
        if ast is None:
            return None
        pages: list[int] = []
        for block in ast.blocks[:200]:
            if self._is_toc_heading(block.text or "") and block.page is not None:
                pages.append(block.page)
        return min(pages) if pages else None

    def _toc_page_from_pdf(self, doc: Any) -> int | None:
        max_probe_pages = min(getattr(doc, "page_count", 0) or 0, max(self.max_images + 8, 12))
        for page_index in range(max_probe_pages):
            try:
                text = doc.load_page(page_index).get_text("text") or ""
            except Exception:
                continue
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if any(self._is_toc_heading(line) for line in lines[:8]):
                return page_index + 1
            compact = re.sub(r"\s+", "", text)
            if "目录" in compact[:80] and re.search(r"\d+(?:\.\d+)+[^\n]{0,40}\.{3,}\d+", text):
                return page_index + 1
        return None

    def _pdf_cover_page_count(self, total_pages: int, toc_page: int | None) -> int:
        if total_pages <= 0:
            return 0
        if toc_page is not None and toc_page > 1:
            return min(total_pages, toc_page - 1, self.max_images)
        return min(total_pages, self.max_images)

    def _is_pdf_text_page_without_images(self, page: Any) -> bool:
        try:
            if page.get_images(full=True):
                return False
        except Exception:
            return False
        try:
            text = re.sub(r"\s+", "", page.get_text("text") or "")
        except Exception:
            return False
        return len(text) > 80

    def _document_relationships(self, package: zipfile.ZipFile) -> dict[str, str]:
        try:
            rels_xml = package.read("word/_rels/document.xml.rels")
        except KeyError:
            return {}
        root = ET.fromstring(rels_xml)
        result: dict[str, str] = {}
        for rel in root.findall("rel:Relationship", NAMESPACE):
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            rel_type = rel.attrib.get("Type", "")
            if not rel_id or not target or "image" not in rel_type:
                continue
            result[rel_id] = self._normalize_word_target(target)
        return result

    def _image_targets_before_toc(self, document_xml: bytes, rels: dict[str, str]) -> list[str]:
        root = ET.fromstring(document_xml)
        body = root.find("w:body", NAMESPACE)
        if body is None:
            return []
        namespaces = {**NAMESPACE, "v": "urn:schemas-microsoft-com:vml"}
        targets: list[str] = []
        for child in list(body):
            text = self._node_text(child)
            if self._is_toc_heading(text):
                break
            for blip in child.findall(".//a:blip", namespaces):
                rel_id = blip.attrib.get(f"{{{R_NS}}}embed") or blip.attrib.get(f"{{{R_NS}}}link")
                target = rels.get(rel_id or "")
                if target:
                    targets.append(target)
            for image_data in child.findall(".//v:imagedata", namespaces):
                rel_id = image_data.attrib.get(f"{{{R_NS}}}id") or image_data.attrib.get(f"{{{R_NS}}}embed")
                target = rels.get(rel_id or "")
                if target:
                    targets.append(target)
        return targets

    def _normalize_word_target(self, target: str) -> str:
        cleaned = target.replace("\\", "/")
        if cleaned.startswith("/"):
            cleaned = cleaned.lstrip("/")
        elif not cleaned.startswith("word/"):
            cleaned = f"word/{cleaned}"
        parts: list[str] = []
        for part in cleaned.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        return "/".join(parts)

    def _node_text(self, node: ET.Element) -> str:
        return "".join(text_node.text or "" for text_node in node.findall(".//w:t", NAMESPACE)).strip()

    def _is_toc_heading(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text or "")
        if not normalized:
            return False
        if normalized in {"\u76ee\u5f55", "\u76ee\u9304", "contents", "Contents"}:
            return True
        return bool(re.fullmatch(r"(?:\u7b2c?[0-9\u4e00-\u9fa5]{0,4}[\.?\s]*)?\u76ee\u5f55", normalized))

    def _ocr_image(self, content: bytes, name: str) -> list[str]:
        if self.ocr_runner is not None:
            return self.ocr_runner(content, name)
        lines = self._ocr_image_with_rapidocr(content, name)
        if lines:
            return lines
        return self._ocr_image_with_paddle(content, name)

    def _ocr_image_with_paddle(self, content: bytes, name: str) -> list[str]:
        ocr = self._load_paddle_ocr()
        if ocr is None:
            return []
        suffix = Path(name).suffix or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        try:
            try:
                result = ocr.ocr(str(temp_path), cls=True)
            except TypeError:
                result = ocr.ocr(str(temp_path))
            return self._flatten_ocr_result(result)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _load_paddle_ocr(self):
        if self._paddle_ocr_unavailable:
            return None
        if self._paddle_ocr is not None:
            return self._paddle_ocr
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception as exc:
            logger.warning(f"PaddleOCR is unavailable; cover image OCR skipped: {exc}")
            self._paddle_ocr_unavailable = True
            return None
        try:
            self._paddle_ocr = self._create_paddle_ocr(PaddleOCR)
        except Exception as exc:
            logger.warning(f"PaddleOCR initialization failed; cover image OCR skipped: {exc}")
            self._paddle_ocr_unavailable = True
            return None
        return self._paddle_ocr

    def _ocr_image_with_rapidocr(self, content: bytes, name: str) -> list[str]:
        ocr = self._load_rapid_ocr()
        if ocr is None:
            return []
        try:
            result = ocr(content)
        except TypeError:
            suffix = Path(name).suffix or ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            try:
                result = ocr(str(temp_path))
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
        return self._flatten_ocr_result(result)

    def _load_rapid_ocr(self):
        if self._rapid_ocr_unavailable:
            return None
        if self._rapid_ocr is not None:
            return self._rapid_ocr
        try:
            from rapidocr import RapidOCR  # type: ignore
        except Exception as exc:
            logger.warning(f"RapidOCR is unavailable; cover image OCR skipped: {exc}")
            self._rapid_ocr_unavailable = True
            return None
        try:
            self._rapid_ocr = RapidOCR(params={"Global.log_level": "error"})
        except Exception as exc:
            logger.warning(f"RapidOCR initialization failed; cover image OCR skipped: {exc}")
            self._rapid_ocr_unavailable = True
            return None
        return self._rapid_ocr

    def _create_paddle_ocr(self, paddle_ocr_cls):
        """Create PaddleOCR across versions with different constructor args."""
        try:
            return paddle_ocr_cls(use_angle_cls=True, lang="ch", show_log=False)
        except Exception as exc:
            if not self._is_unknown_argument_error(exc, "show_log"):
                raise
            logger.warning("PaddleOCR does not support show_log; retrying without it")
            return paddle_ocr_cls(use_angle_cls=True, lang="ch")

    def _is_unknown_argument_error(self, exc: Exception, argument: str) -> bool:
        message = str(exc)
        return argument in message and "Unknown argument" in message

    def _flatten_ocr_result(self, result: Any) -> list[str]:
        lines: list[str] = []
        if result is None:
            return lines
        if isinstance(result, dict):
            for key in ("rec_texts", "texts"):
                values = result.get(key)
                if isinstance(values, list):
                    lines.extend(str(item) for item in values if item)
            return lines
        txts = getattr(result, "txts", None)
        if isinstance(txts, (list, tuple)):
            lines.extend(str(item) for item in txts if item)
            return lines
        if isinstance(result, tuple) and result and isinstance(result[0], str):
            return [result[0]]
        if isinstance(result, list):
            for item in result:
                if isinstance(item, str):
                    lines.append(item)
                elif isinstance(item, tuple) and item and isinstance(item[0], str):
                    lines.append(item[0])
                elif isinstance(item, list):
                    if len(item) >= 2 and isinstance(item[1], tuple) and item[1] and isinstance(item[1][0], str):
                        lines.append(item[1][0])
                    else:
                        lines.extend(self._flatten_ocr_result(item))
                elif isinstance(item, dict):
                    lines.extend(self._flatten_ocr_result(item))
        return lines

    def _normalize_ocr_text(self, text: str) -> str:
        lines = [re.sub(r"\s+", "", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    def _env_int(self, name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError:
            logger.warning(f"Invalid integer for {name}: {raw!r}; using default {default}")
            return default
        return value if value > 0 else default

    def _save_debug_image(self, index: int, name: str, content: bytes) -> None:
        if self.debug_save_dir is None:
            return
        try:
            self.debug_save_dir.mkdir(parents=True, exist_ok=True)
            target_name = Path(name).name.replace("/", "_").replace("\\", "_")
            debug_path = self.debug_save_dir / f"{index:02d}_{target_name}"
            debug_path.write_bytes(content)
            logger.info(f"Cover OCR debug image saved: {debug_path}")
        except Exception as exc:
            logger.warning(f"Cover OCR debug image save failed for {name}: {exc}")

    def _extract_common_fields(self, text: str, ast: DocumentAST | None = None) -> dict[str, str]:
        values: dict[str, str] = {}
        project_name = self._project_name_from_ocr(text, ast)
        if project_name:
            values["projectName"] = project_name
        design_unit = self._design_unit_from_ocr(text)
        if design_unit:
            values["designUnit"] = design_unit
        qualification = self._design_unit_qualification_from_ocr(text)
        if qualification:
            values["designUnitQualification"] = qualification
        return values

    def _project_name_from_ocr(self, text: str, ast: DocumentAST | None = None) -> str | None:
        for line in text.splitlines()[:20]:
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9()（）\-]{6,80}(?:\u98ce\u7535|\u98ce\u529b\u53d1\u7535)[\u4e00-\u9fa5A-Za-z0-9()（）\-]{0,20}\u9879\u76ee)", line)
            if match:
                return self._clean_value(match.group(1))
        if ast is not None:
            stem = re.sub(r"\.(?:docx?|pdf)$", "", ast.file_name, flags=re.IGNORECASE)
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9()（）\-]{6,80}(?:\u98ce\u7535|\u98ce\u529b\u53d1\u7535)[\u4e00-\u9fa5A-Za-z0-9()（）\-]{0,20}\u9879\u76ee)", stem)
            if match:
                return self._clean_value(match.group(1))
        return None

    def _design_unit_from_ocr(self, text: str) -> str | None:
        compact = text.replace("\n", " ")
        no_space = re.sub(r"\s+", "", text)
        patterns = [
            r"(?:\u8bbe\u8ba1\u5355\u4f4d|\u7f16\u5236\u5355\u4f4d|\u5355\u4f4d\u540d\u79f0)[:\uff1a\s]*([\u4e00-\u9fa5A-Za-z0-9()（）\-]{4,90}(?:\u516c\u53f8|\u7814\u7a76\u9662|\u8bbe\u8ba1\u9662|\u5de5\u7a0b\u9662))",
            r"([\u4e00-\u9fa5A-Za-z0-9()（）\-]{4,90}(?:\u8bbe\u8ba1\u7814\u7a76\u9662|\u8bbe\u8ba1\u9662|\u7814\u7a76\u9662|\u79d1\u6280\u5de5\u7a0b\u80a1\u4efd\u6709\u9650\u516c\u53f8|\u5de5\u7a0b\u6709\u9650\u516c\u53f8))",
        ]
        candidates: list[str] = []
        for source_text in (compact, no_space):
            for pattern in patterns:
                for match in re.finditer(pattern, source_text):
                    value = self._clean_value(match.group(1))
                    if self._looks_like_design_unit(value):
                        candidates.append(value)
        if candidates:
            return max(candidates, key=len)
        for line in text.splitlines():
            value = self._clean_value(line)
            if self._looks_like_design_unit(value):
                return value
        return None

    def _design_unit_qualification_from_ocr(self, text: str) -> str | None:
        compact = text.replace("\n", " ")
        no_space = self._normalize_grade_ocr_text(re.sub(r"\s+", "", text))
        compact = self._normalize_grade_ocr_text(compact)
        patterns = [
            r"(?:\u7b49\u7ea7|\u7ea7\u522b)[:\uff1a\s]*([\u7532\u4e59\u4e19\u4e01]\u7ea7)",
            r"(?:\u8d44\u8d28\u7b49\u7ea7|\u8bbe\u8ba1\u8d44\u8d28|\u5de5\u7a0b\u8bbe\u8ba1|\u8d44\u4fe1\u8bc1\u4e66|\u8d44\u4fe1)[^\u7532\u4e59\u4e19\u4e01]{0,30}([\u7532\u4e59\u4e19\u4e01]\u7ea7)",
            r"([\u7532\u4e59\u4e19\u4e01]\u7ea7)[^\n]{0,20}(?:\u8d44\u4fe1|\u8d44\u8d28|\u8bc1\u4e66)",
        ]
        for source_text in (compact, no_space):
            for pattern in patterns:
                match = re.search(pattern, source_text)
                if match:
                    return match.group(1)
        grade = re.search(r"([\u7532\u4e59\u4e19\u4e01]\u7ea7)", no_space or compact)
        return grade.group(1) if grade else None

    def _normalize_grade_ocr_text(self, text: str) -> str:
        """Normalize common OCR confusions around qualification grades."""
        normalized = text or ""
        normalized = re.sub(r"[申用田][级極极圾]", "甲级", normalized)
        normalized = re.sub(r"甲[極极圾]", "甲级", normalized)
        normalized = re.sub(r"乙[極极圾]", "乙级", normalized)
        normalized = re.sub(r"丙[極极圾]", "丙级", normalized)
        normalized = re.sub(r"丁[極极圾]", "丁级", normalized)
        return normalized

    def _looks_like_design_unit(self, value: str | None) -> bool:
        if not value or len(value) > 90:
            return False
        if any(token in value for token in ("\u53d1\u8bc1\u5355\u4f4d", "\u8d44\u8d28", "\u8bc1\u4e66", "\u76ee\u5f55")):
            return False
        return any(token in value for token in ("\u8bbe\u8ba1", "\u7814\u7a76\u9662", "\u5de5\u7a0b", "\u516c\u53f8", "\u9662"))

    def _clean_value(self, value: str) -> str:
        cleaned = re.sub(r"\s+", "", value or "")
        cleaned = cleaned.strip(" :\uff1a,\uff0c\u3002;\uff1b|_")
        return cleaned
