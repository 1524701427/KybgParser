"""Aspose.Words 加载器。

支持两种合法加载方式：

1. `aspose-words` Python 包。
2. `pythonnet + Aspose.Words.dll + Aspose.Total.NET.lic`，默认读取项目 `runtime/` 目录。

注意：本模块只调用官方 `License.SetLicense` 设置授权文件，不包含任何绕授权逻辑。
"""

from __future__ import annotations

import gc
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from parser_engine.document.ast.document import DocumentAST, DocumentBlock, DocumentTable, TableCell, TextStyle
from parser_engine.core.logger import logger
from parser_engine.document.loaders.simple_docx_loader import SimpleDocxLoader
from parser_engine.document.loaders.word_loader import WordLoader


class AsposeWordsLoader(WordLoader):
    """基于 Aspose.Words 的生产级 Word 加载器。"""

    def __init__(
        self,
        fallback_to_simple: bool = True,
        dll_dir: str | Path | None = None,
        license_path: str | Path | None = None,
    ):
        """初始化加载器。

        Args:
            fallback_to_simple: Aspose 不可用时是否退回 SimpleDocxLoader。
            dll_dir: Aspose.Words.dll 所在目录；默认读取项目 `runtime/` 目录。
            license_path: Aspose license 文件路径；默认读取 `runtime/Aspose.Total.NET.lic`。
        """
        self.fallback_to_simple = fallback_to_simple
        self.project_root = Path(__file__).resolve().parents[3]
        self.runtime_dir = self.project_root / "runtime"
        self.dll_dir = Path(dll_dir or os.getenv("ASPOSE_WORDS_DLL_DIR") or self._default_dll_dir())
        self.license_path = Path(
            license_path
            or os.getenv("ASPOSE_WORDS_LICENSE_PATH")
            or self._default_license_path()
        )
        self._native_dll_handles: list[Any] = []

    def _default_dll_dir(self) -> Path:
        """返回默认 Aspose DLL 目录，兼容旧的根目录摆放方式。"""
        if (self.runtime_dir / "Aspose.Words.dll").exists():
            return self.runtime_dir
        return self.project_root

    def _default_license_path(self) -> Path:
        """返回默认 Aspose license 路径，兼容旧的根目录摆放方式。"""
        runtime_license = self.runtime_dir / "Aspose.Total.NET.lic"
        if runtime_license.exists():
            return runtime_license
        return self.project_root / "Aspose.Total.NET.lic"

    def load(self, file_path: str) -> DocumentAST:
        """加载 Word 文档。

        Args:
            file_path: Word 文档路径。

        Returns:
            DocumentAST: 统一文档对象。
        """
        runtime = self._load_aspose_runtime()
        if runtime is None:
            suffix = Path(file_path).suffix.lower()
            if suffix != ".docx":
                raise RuntimeError(
                    "Aspose 运行时不可用，且当前文件不是 docx，无法使用 SimpleDocxLoader 兜底；"
                    "请确认 pythonnet、Aspose.Words.dll、Aspose.Total.NET.lic 可用。"
                )
            if self.fallback_to_simple:
                logger.warning("Aspose 运行时不可用，自动切换到 SimpleDocxLoader")
                return SimpleDocxLoader().load(file_path)
            raise RuntimeError("Aspose 运行时不可用，请安装 aspose-words 或 pythonnet 并提供 Aspose.Words.dll")

        mode, aw = runtime
        logger.info(f"使用 Aspose.Words 解析 Word 文档，运行模式：{mode}")
        doc, temp_dir = self._open_document_with_path_fallback(aw, file_path)
        try:
            self._update_list_labels(doc)
            if mode == "python-package":
                ast = self._parse_python_package_doc(doc, aw, file_path)
            else:
                ast = self._parse_dotnet_doc(doc, aw, file_path)
            return ast
        finally:
            # 解析完成后尽快释放 Aspose/.NET 临时对象，避免后续 BGE 加载时叠加占用内存。
            del doc
            if temp_dir is not None:
                temp_dir.cleanup()
            self._collect_runtime_memory()

    def export_pdf(self, file_path: str, output_path: str | Path) -> bool:
        """把 Word 文档导出为 PDF，供版面 sidecar 使用。

        Args:
            file_path: Word 文档路径。
            output_path: PDF 输出路径。

        Returns:
            bool: 导出成功返回 True；运行时不可用或导出失败返回 False。
        """
        runtime = self._load_aspose_runtime()
        if runtime is None:
            logger.warning("Aspose 运行时不可用，跳过 Word->PDF layout sidecar")
            return False
        mode, aw = runtime
        if mode == "dotnet-dll" and not self._skia_native_available():
            logger.warning("缺少 libSkiaSharp.dll，跳过 Word->PDF layout sidecar，避免 SkiaSharp native 依赖崩溃")
            return False
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc, temp_dir = self._open_document_with_path_fallback(aw, file_path)
            try:
                if mode == "python-package":
                    doc.save(str(output_path), aw.SaveFormat.PDF)
                else:
                    doc.Save(str(output_path), aw.SaveFormat.Pdf)
            finally:
                del doc
                if temp_dir is not None:
                    temp_dir.cleanup()
                self._collect_runtime_memory()
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            logger.warning(f"Word 转 PDF 失败，跳过 layout sidecar：{exc}")
            return False

    def _open_document_with_path_fallback(self, aw: Any, file_path: str) -> tuple[Any, tempfile.TemporaryDirectory | None]:
        """打开 Word 文档，中文路径失败时复制到临时英文路径再重试。

        Args:
            aw: Aspose.Words 模块。
            file_path: 原始 Word 文件路径。

        Returns:
            tuple[Any, tempfile.TemporaryDirectory | None]: Aspose 文档对象，以及需要延迟清理的临时目录。
        """
        try:
            return aw.Document(file_path), None
        except Exception as exc:
            source = Path(file_path)
            if not source.exists():
                raise
            temp_dir = tempfile.TemporaryDirectory(prefix="aspose_word_path_")
            temp_path = Path(temp_dir.name) / f"input{source.suffix.lower() or '.docx'}"
            try:
                shutil.copy2(source, temp_path)
                logger.warning(f"Aspose 直接打开原路径失败，改用临时英文路径重试：{exc}")
                return aw.Document(str(temp_path)), temp_dir
            except Exception:
                temp_dir.cleanup()
                raise

    def _load_aspose_runtime(self) -> tuple[str, Any] | None:
        """加载可用的 Aspose 运行时。

        Returns:
            tuple[str, Any] | None: `(运行模式, Aspose.Words 模块)`，不可用时返回 None。
        """
        python_runtime = self._try_load_python_package()
        if python_runtime is not None:
            return python_runtime
        return self._try_load_dotnet_dll()

    def _try_load_python_package(self) -> tuple[str, Any] | None:
        """尝试加载 `aspose-words` Python 包。

        Returns:
            tuple[str, Any] | None: 成功时返回运行模式和模块。
        """
        try:
            import aspose.words as aw  # type: ignore
        except Exception:
            return None
        self._apply_license(aw)
        return "python-package", aw

    def _try_load_dotnet_dll(self) -> tuple[str, Any] | None:
        """尝试通过 pythonnet 加载 Aspose.Words.dll。

        Returns:
            tuple[str, Any] | None: 成功时返回运行模式和模块。
        """
        dll_path = self.dll_dir / "Aspose.Words.dll"
        if not dll_path.exists():
            logger.warning(f"未找到 Aspose.Words.dll：{dll_path}")
            return None

        try:
            import pythonnet  # type: ignore
            runtime_config = self.dll_dir / "runtimeconfig.json"
            if not pythonnet.get_runtime_info():
                if runtime_config.exists():
                    pythonnet.load("coreclr", runtime_config=str(runtime_config))
                    logger.info(f"已通过 runtimeconfig 加载 CoreCLR：{runtime_config}")
                else:
                    pythonnet.load("coreclr")
                    logger.info("已加载默认 CoreCLR 运行时")
            import clr  # type: ignore
        except Exception as exc:
            logger.warning(f"pythonnet/CoreCLR 加载失败：{exc}")
            return None

        skia_path = self.dll_dir / "SkiaSharp.dll"
        try:
            if skia_path.exists():
                if self._configure_skia_runtime(clr, skia_path):
                    logger.info(f"已加载 SkiaSharp.dll：{skia_path}")
            clr.AddReference(str(dll_path))
            import Aspose.Words as aw  # type: ignore
        except Exception as exc:
            logger.warning(f"Aspose.Words.dll 加载失败：{exc}")
            return None

        self._apply_license(aw)
        return "dotnet-dll", aw

    def _configure_skia_runtime(self, clr: Any, skia_path: Path) -> bool:
        """配置 SkiaSharp 托管 DLL 和 native DLL 搜索路径。

        Args:
            clr: pythonnet 的 clr 模块。
            skia_path: SkiaSharp.dll 路径。

        Returns:
            bool: native 依赖完整时返回 True，否则跳过 SkiaSharp 托管 DLL 加载。
        """
        native_path = self._find_skia_native_library()
        if native_path is None:
            logger.warning(f"找到 SkiaSharp.dll 但缺少 libSkiaSharp.dll：{skia_path}")
            return False
        native_dir = str(native_path.parent)
        if hasattr(os, "add_dll_directory"):
            try:
                self._native_dll_handles.append(os.add_dll_directory(native_dir))
            except OSError as exc:
                logger.warning(f"添加 SkiaSharp native DLL 目录失败：{native_dir}，{exc}")
                return False
        os.environ["PATH"] = f"{native_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        clr.AddReference(str(skia_path))
        return True

    def _find_skia_native_library(self) -> Path | None:
        """查找 SkiaSharp Windows native DLL。"""
        candidates = [
            self.dll_dir / "libSkiaSharp.dll",
            self.dll_dir / "runtimes" / "win-x64" / "native" / "libSkiaSharp.dll",
            self.dll_dir / "runtimes" / "win-x86" / "native" / "libSkiaSharp.dll",
            self.dll_dir / "runtimes" / "win-arm64" / "native" / "libSkiaSharp.dll",
        ]
        return next((path for path in candidates if path.exists()), None)

    def _skia_native_available(self) -> bool:
        """判断当前 .NET Aspose 运行目录是否具备 PDF 渲染所需的 Skia native 依赖。"""
        if not (self.dll_dir / "SkiaSharp.dll").exists():
            return True
        return self._find_skia_native_library() is not None

    def _apply_license(self, aw: Any) -> None:
        """设置 Aspose 官方 license。

        Args:
            aw: Aspose.Words 模块。
        """
        if not self.license_path.exists():
            logger.warning(f"未找到 Aspose license 文件，将以评估模式运行：{self.license_path}")
            return
        try:
            license_obj = aw.License()
            if hasattr(license_obj, "set_license"):
                license_obj.set_license(str(self.license_path))
            else:
                license_obj.SetLicense(str(self.license_path))
            logger.info(f"Aspose license 设置成功：{self.license_path}")
        except Exception as exc:
            logger.warning(f"Aspose license 设置失败：{exc}")

    def _parse_python_package_doc(self, doc: Any, aw: Any, file_path: str) -> DocumentAST:
        """解析 Python 包版本的 Aspose 文档对象。

        Args:
            doc: Aspose Document 对象。
            aw: Aspose.Words 模块。
            file_path: 原始文件路径。

        Returns:
            DocumentAST: 统一文档对象。
        """
        ast = DocumentAST(file_name=Path(file_path).name, meta={"loader": "AsposeWordsLoader", "mode": "python-package"})
        order = 0
        paragraph_index = 0
        table_index = 0
        for section in doc.sections:
            for node in section.body.child_nodes:
                node_type = node.node_type
                if node_type == aw.NodeType.PARAGRAPH:
                    paragraph_index += self._append_python_paragraph(ast, node, aw, paragraph_index, order)
                    if ast.blocks and ast.blocks[-1].order == order:
                        order += 1
                elif node_type == aw.NodeType.TABLE:
                    table_index += 1
                    table = self._parse_python_table(node, aw, table_index, order)
                    self._append_table(ast, table, order)
                    order += 1
        return ast

    def _parse_dotnet_doc(self, doc: Any, aw: Any, file_path: str) -> DocumentAST:
        """解析 .NET DLL 版本的 Aspose 文档对象。

        Args:
            doc: Aspose Document 对象。
            aw: Aspose.Words 模块。
            file_path: 原始文件路径。

        Returns:
            DocumentAST: 统一文档对象。
        """
        ast = DocumentAST(file_name=Path(file_path).name, meta={"loader": "AsposeWordsLoader", "mode": "dotnet-dll"})
        order = 0
        paragraph_index = 0
        table_index = 0
        for section in doc.Sections:
            # pythonnet 对 .NET 属性暴露不完全，当前 DLL 版本需要通过 GetChildNodes 遍历。
            for node in section.Body.GetChildNodes(aw.NodeType.Any, False):
                node_type = node.NodeType
                if node_type == aw.NodeType.Paragraph:
                    paragraph_index += self._append_dotnet_paragraph(ast, node, paragraph_index, order)
                    if ast.blocks and ast.blocks[-1].order == order:
                        order += 1
                elif node_type == aw.NodeType.Table:
                    table_index += 1
                    table = self._parse_dotnet_table(node, table_index, order)
                    self._append_table(ast, table, order)
                    order += 1
        return ast

    def _append_python_paragraph(self, ast: DocumentAST, node: Any, aw: Any, index: int, order: int) -> int:
        """追加 Python 包模式下的段落块。

        Args:
            ast: 文档 AST。
            node: Aspose 段落节点。
            aw: Aspose.Words 模块。
            index: 当前段落序号。
            order: 文档顺序。

        Returns:
            int: 实际新增段落数。
        """
        text = node.to_string(aw.SaveFormat.TEXT).strip()
        if not text:
            return 0
        label = self._python_list_label(node)
        if label:
            text = f"{label} {text}"
        style = self._python_paragraph_style(node)
        meta = {"list_label": label} if label else {}
        layout = self._python_paragraph_layout(node)
        if layout:
            # Word 自身没有稳定页码/bbox，这里先保留能从段落对象读取到的样式版面信号。
            meta["paragraph_layout"] = layout
        ast.blocks.append(DocumentBlock(id=f"p_{index + 1:04d}", type="paragraph", text=text, order=order, style=style, meta=meta))
        return 1

    def _append_dotnet_paragraph(self, ast: DocumentAST, node: Any, index: int, order: int) -> int:
        """追加 .NET DLL 模式下的段落块。

        Args:
            ast: 文档 AST。
            node: Aspose 段落节点。
            index: 当前段落序号。
            order: 文档顺序。

        Returns:
            int: 实际新增段落数。
        """
        text = self._clean_aspose_text(node.GetText())
        if not text:
            return 0
        label = self._dotnet_list_label(node)
        if label:
            text = f"{label} {text}"
        style = self._dotnet_paragraph_style(node)
        meta = {"list_label": label} if label else {}
        layout = self._dotnet_paragraph_layout(node)
        if layout:
            # Word 自身没有稳定页码/bbox，这里先保留能从段落对象读取到的样式版面信号。
            meta["paragraph_layout"] = layout
        ast.blocks.append(DocumentBlock(id=f"p_{index + 1:04d}", type="paragraph", text=text, order=order, style=style, meta=meta))
        return 1

    def _python_paragraph_style(self, node: Any) -> TextStyle:
        """读取 Python 包模式下的段落样式。"""
        runs = list(getattr(node, "runs", []) or [])
        font_sizes = [self._to_float(getattr(getattr(run, "font", None), "size", None)) for run in runs]
        font_sizes = [value for value in font_sizes if value is not None]
        return TextStyle(
            style_name=getattr(getattr(node.paragraph_format, "style", None), "name", None),
            font_size=font_sizes[0] if font_sizes else None,
            bold=any(bool(getattr(getattr(run, "font", None), "bold", False)) for run in runs),
            italic=any(bool(getattr(getattr(run, "font", None), "italic", False)) for run in runs),
            alignment=self._alignment_text(getattr(node.paragraph_format, "alignment", None)),
        )

    def _dotnet_paragraph_style(self, node: Any) -> TextStyle:
        """读取 .NET DLL 模式下的段落样式。"""
        runs = list(getattr(node, "Runs", []) or [])
        font_sizes = [self._to_float(getattr(getattr(run, "Font", None), "Size", None)) for run in runs]
        font_sizes = [value for value in font_sizes if value is not None]
        return TextStyle(
            style_name=getattr(getattr(node.ParagraphFormat, "Style", None), "Name", None),
            font_size=font_sizes[0] if font_sizes else None,
            bold=any(bool(getattr(getattr(run, "Font", None), "Bold", False)) for run in runs),
            italic=any(bool(getattr(getattr(run, "Font", None), "Italic", False)) for run in runs),
            alignment=self._alignment_text(getattr(node.ParagraphFormat, "Alignment", None)),
        )

    def _python_paragraph_layout(self, node: Any) -> dict[str, Any]:
        """读取 Python 包模式下可用的段落缩进信息。"""
        fmt = getattr(node, "paragraph_format", None)
        return self._drop_none(
            {
                "leftIndent": self._to_float(getattr(fmt, "left_indent", None)),
                "firstLineIndent": self._to_float(getattr(fmt, "first_line_indent", None)),
                "rightIndent": self._to_float(getattr(fmt, "right_indent", None)),
            }
        )

    def _dotnet_paragraph_layout(self, node: Any) -> dict[str, Any]:
        """读取 .NET DLL 模式下可用的段落缩进信息。"""
        fmt = getattr(node, "ParagraphFormat", None)
        return self._drop_none(
            {
                "leftIndent": self._to_float(getattr(fmt, "LeftIndent", None)),
                "firstLineIndent": self._to_float(getattr(fmt, "FirstLineIndent", None)),
                "rightIndent": self._to_float(getattr(fmt, "RightIndent", None)),
            }
        )

    def _alignment_text(self, value: Any) -> str | None:
        """把 Aspose alignment 枚举转成稳定文本。"""
        if value is None:
            return None
        text = str(value)
        return text.rsplit(".", 1)[-1].lower()

    def _to_float(self, value: Any) -> float | None:
        """把 Aspose 数值对象宽松转成 float。"""
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _drop_none(self, data: dict[str, Any]) -> dict[str, Any]:
        """删除值为 None 的元信息字段。"""
        return {key: value for key, value in data.items() if value is not None}

    def _update_list_labels(self, doc: Any) -> None:
        try:
            doc.update_list_labels()
        except Exception:
            try:
                doc.UpdateListLabels()
            except Exception:
                return

    def _python_list_label(self, node: Any) -> str | None:
        try:
            if not node.list_format.is_list_item:
                return None
            return self._normalize_numeric_list_label(node.list_label.label_string)
        except Exception:
            return None

    def _dotnet_list_label(self, node: Any) -> str | None:
        try:
            if not node.ListFormat.IsListItem:
                return None
            return self._normalize_numeric_list_label(node.ListLabel.LabelString)
        except Exception:
            return None

    def _normalize_numeric_list_label(self, label: Any) -> str | None:
        cleaned = str(label or "").strip().rstrip(".")
        if not re.fullmatch(r"\d+(?:\.\d+)+", cleaned):
            return None
        return cleaned

    def _parse_python_table(self, table_node: Any, aw: Any, index: int, order: int) -> DocumentTable:
        """解析 Python 包模式下的表格。"""
        rows: list[list[TableCell]] = []
        for row_index, row in enumerate(table_node.rows):
            parsed_row: list[TableCell] = []
            for col_index, cell in enumerate(row.cells):
                text = cell.to_string(aw.SaveFormat.TEXT).strip()
                parsed_row.append(TableCell(text=text, row=row_index, col=col_index, is_header=row_index == 0))
            rows.append(parsed_row)
        return DocumentTable(id=f"t_{index:04d}", order=order, rows=rows)

    def _parse_dotnet_table(self, table_node: Any, index: int, order: int) -> DocumentTable:
        """解析 .NET DLL 模式下的表格。"""
        rows: list[list[TableCell]] = []
        for row_index, row in enumerate(table_node.Rows):
            parsed_row: list[TableCell] = []
            for col_index, cell in enumerate(row.Cells):
                text = self._clean_aspose_text(cell.GetText())
                parsed_row.append(TableCell(text=text, row=row_index, col=col_index, is_header=row_index == 0))
            rows.append(parsed_row)
        return DocumentTable(id=f"t_{index:04d}", order=order, rows=rows)

    def _append_table(self, ast: DocumentAST, table: DocumentTable, order: int) -> None:
        """追加表格和表格占位块。

        Args:
            ast: 文档 AST。
            table: 表格对象。
            order: 文档顺序。
        """
        ast.tables.append(table)
        ast.blocks.append(
            DocumentBlock(
                id=f"tb_{len(ast.tables):04d}",
                type="table",
                text="\n".join(" | ".join(cell.text for cell in row) for row in table.rows),
                order=order,
                meta={"table_id": table.id},
            )
        )

    def _clean_aspose_text(self, text: str) -> str:
        """清洗 Aspose GetText 返回的控制字符。

        Args:
            text: 原始文本。

        Returns:
            str: 清洗后的文本。
        """
        return (text or "").replace("\r", " ").replace("\n", " ").replace("\x07", " ").strip()

    def _collect_runtime_memory(self) -> None:
        """主动触发 Python 和 .NET 垃圾回收。"""
        gc.collect()
        try:
            import System  # type: ignore

            System.GC.Collect()
            System.GC.WaitForPendingFinalizers()
            System.GC.Collect()
        except Exception:
            # 没有加载 .NET 运行时时忽略。
            return
