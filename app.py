from __future__ import annotations

import base64
import html
import json
import sys
from dataclasses import dataclass, field
import shutil
from pathlib import Path
from typing import Any, List

from PyQt5 import QtCore, QtGui, QtWidgets


@dataclass
class DescriptionBlock:
    title: str
    content: str


@dataclass
class BridalEntry:
    slug: str
    name: str
    description: str
    price: str
    front: Path
    back: Path
    detail1: Path
    detail2: Path
    description_blocks: List[DescriptionBlock] = field(default_factory=list)
    metadata_path: Path | None = None
    raw_metadata: Any | None = None


class MainWindow(QtWidgets.QMainWindow):
    TEMPLATE_DIR_NAME = "template"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("婚纱目录管理")
        self.resize(1100, 600)
        self.entries: List[BridalEntry] = []
        default_root = Path.cwd()
        template_dir = default_root / self.TEMPLATE_DIR_NAME
        template_dir.mkdir(parents=True, exist_ok=True)

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        main_layout = QtWidgets.QHBoxLayout(root)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Left panel for controls
        left_widget = QtWidgets.QWidget()
        left_widget.setObjectName("Sidebar")
        left_panel = QtWidgets.QVBoxLayout(left_widget)
        left_panel.setContentsMargins(16, 16, 16, 16)
        left_panel.setSpacing(12)
        main_layout.addWidget(left_widget, 1)

        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit(str(default_root))
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit)
        left_panel.addLayout(path_layout)

        self.entry_list = QtWidgets.QListWidget()
        self.entry_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.entry_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.entry_list.currentRowChanged.connect(self.render_preview)
        left_panel.addWidget(self.entry_list, 1)

        add_btn = QtWidgets.QPushButton("新建产品")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.create_entry)
        left_panel.addWidget(add_btn)

        export_btn = QtWidgets.QPushButton("导出 HTML…")
        export_btn.setObjectName("PrimaryButton")
        export_btn.clicked.connect(self.export_html)
        left_panel.addWidget(export_btn)

        refresh_btn = QtWidgets.QPushButton("重新读取")
        refresh_btn.clicked.connect(self.load_entries)
        left_panel.addWidget(refresh_btn)

        # Right editor area
        self.editor = EntryEditor(self)
        main_layout.addWidget(self.editor, 2)

        self.apply_styles()

    def load_entries(self) -> None:
        try:
            template_root = self._get_template_root()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "提示", str(exc))
            return

        entries: List[BridalEntry] = []
        for folder in sorted(template_root.iterdir()):
            if (
                not folder.is_dir()
                or folder.name == "模板"
                or folder.name.startswith(".")
            ):
                continue
            try:
                metadata, meta_path, raw_meta = self._load_metadata(folder)
            except ValueError as exc:
                QtWidgets.QMessageBox.warning(self, "提示", f"{folder.name}：{exc}")
                continue

            name = metadata.get("name") or folder.name
            desc = metadata.get("description", "")
            price = metadata.get("price", "")
            desc_blocks = metadata.get("description_blocks", [])

            images = {
                "front": folder / "主图正面.jpg",
                "back": folder / "主图背面.jpg",
                "detail1": folder / "细节图一.jpg",
                "detail2": folder / "细节图二.jpg",
            }

            missing = [p.name for p, exists in ((path, path.exists()) for path in images.values()) if not exists]
            if missing:
                QtWidgets.QMessageBox.warning(
                    self, "提示", f"{folder.name} 缺少以下图片文件：{', '.join(missing)}"
                )
                continue

            entries.append(
                BridalEntry(
                    slug=folder.name,
                    name=name,
                    description=desc,
                    description_blocks=desc_blocks,
                    price=price,
                    front=images["front"],
                    back=images["back"],
                    detail1=images["detail1"],
                    detail2=images["detail2"],
                    metadata_path=meta_path,
                    raw_metadata=raw_meta,
                )
            )

        self.entries = entries
        self.entry_list.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem(entry.slug)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.entry_list.addItem(item)
            widget = self._build_entry_item(entry)
            hint = widget.sizeHint()
            hint.setHeight(max(hint.height(), 48))
            item.setSizeHint(hint)
            item.setText("")
            self.entry_list.setItemWidget(item, widget)
        if entries:
            self.entry_list.setCurrentRow(0)
        else:
            self.editor.clear()

    def render_preview(self, index: int) -> None:
        if index < 0 or index >= len(self.entries):
            self.editor.clear()
            return
        entry = self.entries[index]
        self.editor.load_entry(entry)

    def render_page(self, entry: BridalEntry, use_file_uri: bool = False) -> str:
        def to_uri(path: Path) -> str:
            if use_file_uri:
                try:
                    return path.resolve().as_uri()
                except OSError:
                    return ""
            try:
                data = path.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                suffix = path.suffix.lower().strip(".") or "jpeg"
                return f"data:image/{suffix};base64,{encoded}"
            except OSError:
                return ""

        images = {
            "front": to_uri(entry.front),
            "back": to_uri(entry.back),
            "detail1": to_uri(entry.detail1),
            "detail2": to_uri(entry.detail2),
        }
        desc_html = self._build_description_html(entry)
        slug_html = self._render_inline(entry.slug)
        name_html = self._render_inline(entry.name)
        price_html = self._render_inline(entry.price)
        alt_name = self._render_inline(entry.name)
        return f"""
        <style>
        :root {{
            --ink:#35241a;
            --accent:#c19273;
            --veil:#faf3eb;
        }}
        .page {{
            background:linear-gradient(135deg,#f9f3ec 0%,#f2e5d8 100%);
            padding:1.8rem;
            border-radius:26px;
            display:grid;
            grid-template-columns:minmax(0,38%) minmax(0,62%);
            gap:1.2rem;
            min-height:260px;
            font-family:'Cormorant Garamond','Palatino Linotype','Times New Roman',serif;
            color:var(--ink);
            box-shadow:0 25px 55px rgba(54,34,17,0.12);
        }}
        .info{{display:flex;flex-direction:column;gap:0.9rem;min-height:100%;}}
        .info h2{{margin:0;font-size:2.2rem;letter-spacing:0.08em;font-weight:500;}}
        .info p{{margin:0 0 0.4rem;font-size:1.05rem;line-height:1.7;}}
        .tag{{text-transform:uppercase;letter-spacing:0.5em;font-size:0.75rem;color:rgba(0,0,0,0.45);font-family:'Optima','Cormorant Garamond','Times New Roman',serif;}}
        .photos{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:minmax(0,1fr) minmax(0,0.6fr);gap:0.7rem;}}
        figure{{margin:0;border-radius:18px;overflow:hidden;position:relative;background:#dcd6cf;box-shadow:0 15px 40px rgba(0,0,0,0.12);}}
        figure img{{width:100%;height:100%;object-fit:cover;display:block;}}
        figure figcaption{{position:absolute;bottom:8px;left:14px;font-size:0.7rem;letter-spacing:0.2em;color:rgba(255,255,255,0.7);text-shadow:0 2px 6px rgba(0,0,0,0.45);}}
        .price{{margin-top:auto;align-self:flex-end;font-size:1.5rem;color:var(--accent);letter-spacing:0.3em;text-transform:uppercase;font-weight:500;}}
        .desc-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:0.8rem;}}
        .desc-grid article{{background:rgba(255,255,255,0.65);padding:0.9rem;border-radius:18px;box-shadow:0 12px 35px rgba(0,0,0,0.08);}}
        .desc-grid article h3{{margin:0 0 0.5rem;font-size:0.9rem;letter-spacing:0.15em;color:var(--accent);text-transform:uppercase;}}
        .desc-grid article p{{margin:0;font-size:0.95rem;line-height:1.6;}}
        </style>
        <section class='page'>
            <div class='info'>
                <div>
                    <div class='tag'>{slug_html}</div>
                    <h2>{name_html}</h2>
                    {desc_html}
                </div>
                <div class='price'>价格 ¥{price_html}</div>
            </div>
            <div class='photos'>
                <figure><img src="{images.get('front', '')}" alt="{alt_name} 主图正面" /></figure>
                <figure><img src="{images.get('back', '')}" alt="{alt_name} 主图背面" /></figure>
                <figure><img src="{images.get('detail1', '')}" alt="{alt_name} 细节一" /><figcaption>DETAIL</figcaption></figure>
                <figure><img src="{images.get('detail2', '')}" alt="{alt_name} 细节二" /><figcaption>DETAIL</figcaption></figure>
            </div>
        </section>
        """

    def export_html(self) -> None:
        if not self.entries:
            QtWidgets.QMessageBox.information(self, "提示", "请先加载素材。")
            return
        output_file, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存预览 HTML", "catalog-preview.html", "HTML Files (*.html)"
        )
        if not output_file:
            return
        pages_html = "".join(self.render_page(entry, use_file_uri=True) for entry in self.entries)
        html = f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'><title>婚纱目录预览</title></head><body style=\"font-family:'PingFang SC','Microsoft Yahei',sans-serif;background:#f4efe7;padding:20px;\">{pages_html}</body></html>"
        Path(output_file).write_text(html, encoding="utf-8")
        QtWidgets.QMessageBox.information(self, "完成", f"已导出到 {output_file}")

    def create_entry(self) -> None:
        try:
            template_root = self._get_template_root()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "提示", str(exc))
            return
        dialog = NewEntryDialog(self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        data = dialog.get_data()
        target_dir = self._make_unique_dir(template_root, data["name"])
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(data["front"], target_dir / "主图正面.jpg")
        shutil.copy(data["back"], target_dir / "主图背面.jpg")
        shutil.copy(data["detail1"], target_dir / "细节图一.jpg")
        shutil.copy(data["detail2"], target_dir / "细节图二.jpg")
        metadata = {
            "name": data["name"],
            "description": data["desc"],
            "price": data["price"],
        }
        (target_dir / "信息.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.load_entries()

    def delete_entry(self, entry: BridalEntry | None = None) -> None:
        index = self.entry_list.currentRow()
        target_entry = entry
        if target_entry is None:
            if index < 0 or index >= len(self.entries):
                QtWidgets.QMessageBox.information(self, "提示", "请先选择要删除的产品。")
                return
            target_entry = self.entries[index]
        else:
            try:
                index = self.entries.index(target_entry)
            except ValueError:
                index = next((i for i, item in enumerate(self.entries) if item.slug == target_entry.slug), -1)
        reply = QtWidgets.QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除“{target_entry.name}”吗？\n（包含图片与信息文件）",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        try:
            template_root = self._get_template_root()
            target_dir = template_root / target_entry.slug
            if target_dir.exists():
                shutil.rmtree(target_dir)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "删除失败", f"删除 {target_entry.name} 时出错：{exc}")
            return
        self.load_entries()
        if self.entries:
            self.entry_list.setCurrentRow(min(max(index, 0), len(self.entries) - 1))
        else:
            self.editor.clear()

    def edit_entry(self, entry: BridalEntry | None = None) -> None:
        index = self.entry_list.currentRow()
        target_entry = entry
        if target_entry is None:
            if index < 0 or index >= len(self.entries):
                QtWidgets.QMessageBox.information(self, "提示", "请先选择要编辑的产品。")
                return
            target_entry = self.entries[index]
        try:
            row = self.entries.index(target_entry)
        except ValueError:
            row = next((i for i, item in enumerate(self.entries) if item.slug == target_entry.slug), -1)
        if row >= 0:
            self.entry_list.setCurrentRow(row)
        self.editor.focus_first_field()

    def apply_editor_changes(self, entry: BridalEntry, data: dict) -> None:
        try:
            template_root = self._get_template_root()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "提示", str(exc))
            return
        target_dir = template_root / entry.slug
        metadata_path = entry.metadata_path or (target_dir / "信息.json")
        raw_meta = entry.raw_metadata if isinstance(entry.raw_metadata, (dict, str)) else None
        try:
            self._write_metadata(metadata_path, data, raw_meta)
            self._apply_image_updates(target_dir, data)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "编辑失败", f"更新 {entry.name} 时出错：{exc}")
            return
        previous_slug = entry.slug
        self.load_entries()
        if self.entries:
            new_index = next((i for i, item in enumerate(self.entries) if item.slug == previous_slug), None)
            if new_index is not None:
                self.entry_list.setCurrentRow(new_index)

    @staticmethod
    def _make_unique_dir(root: Path, base_name: str) -> Path:
        sanitized = base_name.strip() or "新婚纱"
        candidate = root / sanitized
        idx = 1
        while candidate.exists():
            candidate = root / f"{sanitized}-{idx}"
            idx += 1
        return candidate

    def _get_template_root(self) -> Path:
        root_text = self.path_edit.text().strip()
        if not root_text:
            raise ValueError("请选择素材根目录。")
        root_path = Path(root_text)
        if not root_path.exists():
            raise ValueError("选择的路径不存在。")
        template_root = root_path / self.TEMPLATE_DIR_NAME
        template_root.mkdir(parents=True, exist_ok=True)
        return template_root

    def _load_metadata(self, folder: Path) -> tuple[dict, Path, Any]:
        for file_name in ("信息.json", "信息.txt"):
            path = folder / file_name
            if path.exists():
                normalized, raw_meta = self._parse_metadata_file(path)
                return normalized, path, raw_meta
        raise ValueError("缺少信息文件")

    def _parse_metadata_file(self, path: Path) -> tuple[dict, Any]:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("无法读取信息文件") from exc
        if not text:
            raise ValueError("信息文件为空")
        looks_like_json = path.suffix.lower() == ".json" or text.lstrip().startswith("{")
        if looks_like_json:
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 解析失败：{exc.msg}") from exc
            return self._normalize_metadata(raw), raw
        return self._parse_legacy_metadata(text), text

    def _normalize_metadata(self, data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValueError("JSON 信息文件必须是对象结构")
        name = str(data.get("name", "")).strip()
        price = str(data.get("price", "")).strip()
        desc_text, blocks = self._coerce_desc_value(data.get("description"))
        if not desc_text and isinstance(data.get("desc"), str):
            desc_text = data["desc"].strip()
        blocks.extend(self._coerce_blocks(data.get("description_blocks")))
        blocks.extend(self._coerce_blocks(data.get("sections")))
        blocks.extend(self._coerce_blocks(data.get("highlights")))
        return {
            "name": name,
            "price": price,
            "description": desc_text,
            "description_blocks": blocks,
        }

    def _coerce_desc_value(self, value: Any) -> tuple[str, List[DescriptionBlock]]:
        if value is None:
            return "", []
        if isinstance(value, str):
            return value.strip(), []
        if isinstance(value, (int, float)):
            return str(value), []
        blocks: List[DescriptionBlock] = []
        if isinstance(value, list):
            paragraphs: List[str] = []
            for idx, item in enumerate(value):
                if isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned:
                        paragraphs.append(cleaned)
                elif isinstance(item, dict):
                    block = self._block_from_mapping(item, idx)
                    if block:
                        blocks.append(block)
            return "\n".join(paragraphs), blocks
        if isinstance(value, dict):
            block = self._block_from_mapping(value)
            return "", [block] if block else []
        return str(value).strip(), []

    def _coerce_blocks(self, value: Any) -> List[DescriptionBlock]:
        blocks: List[DescriptionBlock] = []
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    block = self._block_from_mapping(item, idx)
                    if block:
                        blocks.append(block)
                elif isinstance(item, str):
                    text = item.strip()
                    if text:
                        blocks.append(DescriptionBlock(title=f"要点 {idx + 1}", content=text))
        elif isinstance(value, dict):
            block = self._block_from_mapping(value)
            if block:
                blocks.append(block)
        return blocks

    def _block_from_mapping(self, mapping: dict, idx: int | None = None) -> DescriptionBlock | None:
        if not isinstance(mapping, dict):
            return None
        title_raw = mapping.get("title") or mapping.get("label") or mapping.get("name")
        content_raw = (
            mapping.get("text")
            or mapping.get("content")
            or mapping.get("desc")
            or mapping.get("description")
            or mapping.get("value")
        )
        if content_raw is None:
            return None
        content = str(content_raw).strip()
        if not content:
            return None
        title = str(title_raw).strip() if title_raw else ""
        if not title and idx is not None:
            title = f"要点 {idx + 1}"
        return DescriptionBlock(title=title, content=content)

    def _parse_legacy_metadata(self, text: str) -> dict:
        name, price = "", ""
        description_lines: List[str] = []
        collecting_desc = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if collecting_desc:
                    description_lines.append("")
                continue
            if line.startswith("名称："):
                name = line.split("：", 1)[1].strip()
                collecting_desc = False
            elif line.startswith("介绍："):
                description_lines = [line.split("：", 1)[1].strip()]
                collecting_desc = True
            elif line.startswith("价格："):
                price = line.split("：", 1)[1].strip()
                collecting_desc = False
            elif collecting_desc:
                description_lines.append(line)
        description = "\n".join(part for part in description_lines if part.strip() or part == "").strip()
        return {
            "name": name,
            "price": price,
            "description": description,
            "description_blocks": [],
        }

    def _write_metadata(self, path: Path, data: dict, raw_meta: Any | None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".json":
            payload = self._prepare_json_payload(raw_meta, data)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(self._build_legacy_text(data), encoding="utf-8")

    def _prepare_json_payload(self, raw_meta: Any | None, data: dict) -> dict:
        payload = raw_meta.copy() if isinstance(raw_meta, dict) else {}
        payload["name"] = data["name"]
        payload["price"] = data["price"]
        payload["description"] = self._convert_desc_for_json(payload.get("description"), data["desc"])
        if "desc" in payload:
            payload["desc"] = data["desc"]
        return payload

    def _build_legacy_text(self, data: dict) -> str:
        return f"名称：{data['name']}\n介绍：{data['desc']}\n价格：{data['price']}\n"

    def _convert_desc_for_json(self, existing_value: Any, text: str) -> Any:
        stripped = text.strip()
        if isinstance(existing_value, list):
            return self._split_paragraphs(stripped)
        return stripped

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        if not text:
            return []
        blocks: List[str] = []
        current: List[str] = []
        for line in text.splitlines():
            if line.strip():
                current.append(line.strip())
            elif current:
                blocks.append(" ".join(current))
                current = []
        if current:
            blocks.append(" ".join(current))
        return blocks

    def _apply_image_updates(self, target_dir: Path, data: dict) -> None:
        mapping = {
            "front": "主图正面.jpg",
            "back": "主图背面.jpg",
            "detail1": "细节图一.jpg",
            "detail2": "细节图二.jpg",
        }
        for key, filename in mapping.items():
            src = data.get(key)
            if src:
                shutil.copy(src, target_dir / filename)

    @staticmethod
    def _render_inline(value: str) -> str:
        return html.escape(value, quote=True) if value else ""

    def _render_paragraph(self, value: str) -> str:
        if not value:
            return ""
        return html.escape(value, quote=True).replace("\n", "<br />")

    def _build_description_html(self, entry: BridalEntry) -> str:
        blocks: List[str] = []
        if entry.description:
            blocks.append(f"<p>{self._render_paragraph(entry.description)}</p>")
        if entry.description_blocks:
            cards = "".join(
                f"<article><h3>{self._render_inline(block.title) or '亮点'}</h3><p>{self._render_paragraph(block.content)}</p></article>"
                for block in entry.description_blocks
                if block.content
            )
            if cards:
                blocks.append(f"<div class='desc-grid'>{cards}</div>")
        if not blocks:
            return "<p>暂无介绍。</p>"
        return "".join(blocks)

    def _build_entry_item(self, entry: BridalEntry) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        widget.setMinimumHeight(48)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        label = QtWidgets.QLabel(entry.slug)
        label.setStyleSheet("font-weight:500;")
        label.setMinimumHeight(28)
        label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        layout.addWidget(label, 1)
        layout.setAlignment(label, QtCore.Qt.AlignVCenter)

        def make_tool_button(text: str, tooltip: str, callback) -> QtWidgets.QToolButton:
            btn = QtWidgets.QToolButton()
            btn.setObjectName("InlineAction")
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            btn.setMinimumWidth(48)
            btn.setMinimumHeight(30)
            btn.clicked.connect(callback)
            return btn

        edit_btn = make_tool_button("编辑", "编辑", lambda _, e=entry: self.edit_entry(e))
        delete_btn = make_tool_button("删除", "删除", lambda _, e=entry: self.delete_entry(e))
        layout.setAlignment(edit_btn, QtCore.Qt.AlignVCenter)
        layout.setAlignment(delete_btn, QtCore.Qt.AlignVCenter)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        return widget

    def apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f1f3f6;
            }
            QWidget#Sidebar {
                background: #ffffff;
                border-radius: 18px;
            }
            QListWidget {
                border: none;
                background: transparent;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 10px;
                margin-bottom: 4px;
            }
            QListWidget::item:selected {
                background: #e6eefc;
                color: #2b4b85;
            }
            QPushButton {
                border: none;
                border-radius: 20px;
                font-size: 14px;
                padding: 10px;
                background: #f0f2f5;
            }
            QPushButton:hover {
                background: #e0e7f5;
            }
            QPushButton:pressed {
                background: #cdd9f0;
            }
            QPushButton#PrimaryButton {
                background: #4f6ef7;
                color: #fff;
            }
            QPushButton#PrimaryButton:hover {
                background: #3f59d4;
            }
            QToolButton#InlineAction {
                border: none;
                background: transparent;
                color: #4f6ef7;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 13px;
            }
            QToolButton#InlineAction:hover {
                background: rgba(79, 110, 247, 0.12);
                color: #2b4b85;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #dfe3ec;
                border-radius: 14px;
                padding: 10px;
                background: #f9fbff;
                font-size: 14px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #4f6ef7;
                background: #fff;
            }
            QWidget#EntryEditor {
                background: #ffffff;
                border-radius: 18px;
            }
            QWidget#EntryEditor QGroupBox {
                border: none;
                font-size: 14px;
                font-weight: 600;
                margin-top: 8px;
            }
            """
        )


class EntryEditor(QtWidgets.QWidget):
    IMAGE_FIELDS = [
        ("front", "主图正面"),
        ("back", "主图背面"),
        ("detail1", "细节图一"),
        ("detail2", "细节图二"),
    ]

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setObjectName("EntryEditor")
        self.current_entry: BridalEntry | None = None
        self.pending_files: dict[str, str] = {key: "" for key, _ in self.IMAGE_FIELDS}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        self.header_label = QtWidgets.QLabel("请选择左侧婚纱进行编辑")
        self.header_label.setStyleSheet("font-size:18px;font-weight:500;color:#2b2b2b;")
        layout.addWidget(self.header_label)

        form = QtWidgets.QGridLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        form.addWidget(QtWidgets.QLabel("名称"), 0, 0)
        self.name_edit = QtWidgets.QLineEdit()
        form.addWidget(self.name_edit, 0, 1)

        form.addWidget(QtWidgets.QLabel("价格"), 1, 0)
        self.price_edit = QtWidgets.QLineEdit()
        form.addWidget(self.price_edit, 1, 1)

        form.addWidget(QtWidgets.QLabel("介绍"), 2, 0)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setFixedHeight(140)
        form.addWidget(self.desc_edit, 2, 1)
        layout.addLayout(form)

        self.images_group = QtWidgets.QGroupBox("图片")
        image_layout = QtWidgets.QGridLayout(self.images_group)
        image_layout.setHorizontalSpacing(18)
        image_layout.setVerticalSpacing(16)
        self.image_previews: dict[str, QtWidgets.QLabel] = {}
        self.image_buttons: dict[str, QtWidgets.QPushButton] = {}
        for idx, (key, label_text) in enumerate(self.IMAGE_FIELDS):
            container = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel(label_text)
            title.setAlignment(QtCore.Qt.AlignCenter)
            title.setStyleSheet("font-weight:500;")
            preview = QtWidgets.QLabel("无图")
            preview.setAlignment(QtCore.Qt.AlignCenter)
            preview.setFixedSize(150, 150)
            preview.setStyleSheet(
                "border:1px dashed #dcdcdc;border-radius:14px;background:#fafafa;color:#9f9f9f;"
            )
            button = QtWidgets.QPushButton("更换…")
            button.clicked.connect(lambda _, k=key: self._pick_image(k))
            self.image_previews[key] = preview
            self.image_buttons[key] = button
            container.addWidget(title)
            container.addWidget(preview)
            container.addWidget(button)
            row = idx // 2
            col = idx % 2
            image_layout.addLayout(container, row, col)
        layout.addWidget(self.images_group)

        self.save_btn = QtWidgets.QPushButton("保存修改")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_changes)
        layout.addWidget(self.save_btn, alignment=QtCore.Qt.AlignRight)

        self.setEnabled(False)

    def load_entry(self, entry: BridalEntry) -> None:
        self.current_entry = entry
        self.pending_files = {key: "" for key, _ in self.IMAGE_FIELDS}
        self.header_label.setText(f"编辑：{entry.name}")
        self.name_edit.setText(entry.name)
        self.price_edit.setText(entry.price)
        self.desc_edit.setPlainText(entry.description)
        for key, _ in self.IMAGE_FIELDS:
            self._update_image_preview(key)
        self.setEnabled(True)

    def clear(self) -> None:
        self.current_entry = None
        self.pending_files = {key: "" for key, _ in self.IMAGE_FIELDS}
        self.header_label.setText("请选择左侧婚纱进行编辑")
        self.name_edit.clear()
        self.price_edit.clear()
        self.desc_edit.clear()
        for label in self.image_previews.values():
            label.clear()
            label.setText("无图")
        self.setEnabled(False)

    def focus_first_field(self) -> None:
        if self.isEnabled():
            self.name_edit.setFocus()

    def save_changes(self) -> None:
        if not self.current_entry:
            return
        name = self.name_edit.text().strip()
        price = self.price_edit.text().strip()
        if not name or not price:
            QtWidgets.QMessageBox.warning(self, "提示", "名称与价格不能为空。")
            return
        data = {
            "name": name,
            "price": price,
            "desc": self.desc_edit.toPlainText().strip(),
        }
        data.update(self.pending_files)
        self.main_window.apply_editor_changes(self.current_entry, data)

    def _pick_image(self, key: str) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.jpg *.jpeg)")
        if not file_path:
            return
        self.pending_files[key] = file_path
        self._update_image_preview(key)

    def _update_image_preview(self, key: str) -> None:
        label = self.image_previews.get(key)
        if not label:
            return
        source: str | Path
        pending = self.pending_files.get(key)
        if pending:
            source = pending
        elif self.current_entry:
            source = getattr(self.current_entry, key)
        else:
            source = ""
        pixmap = QtGui.QPixmap(str(source)) if source else QtGui.QPixmap()
        if pixmap.isNull():
            label.setPixmap(QtGui.QPixmap())
            label.setText("无图")
        else:
            scaled = pixmap.scaled(label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            label.setPixmap(scaled)
            label.setText("")


class NewEntryDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, *, existing: BridalEntry | None = None, require_images: bool = True):
        super().__init__(parent)
        self.setWindowTitle("新增婚纱产品" if existing is None else "编辑婚纱产品")
        self.resize(420, 520)
        layout = QtWidgets.QVBoxLayout(self)

        self.require_images = require_images
        self.existing = existing
        self.name_edit = QtWidgets.QLineEdit()
        self.price_edit = QtWidgets.QLineEdit()
        self.desc_edit = QtWidgets.QTextEdit()
        self.file_paths = {"front": "", "back": "", "detail1": "", "detail2": ""}
        self.file_buttons: dict[str, QtWidgets.QPushButton] = {}
        self.button_defaults: dict[str, str] = {}

        layout.addWidget(QtWidgets.QLabel("婚纱名称"))
        layout.addWidget(self.name_edit)

        layout.addWidget(QtWidgets.QLabel("婚纱价格"))
        layout.addWidget(self.price_edit)

        layout.addWidget(QtWidgets.QLabel("婚纱介绍"))
        self.desc_edit.setPlaceholderText("描述面料、剪裁与使用场景…")
        layout.addWidget(self.desc_edit)

        layout.addSpacing(6)
        layout.addWidget(QtWidgets.QLabel("上传图片"))
        self.front_btn = QtWidgets.QPushButton("选择主图正面")
        self.back_btn = QtWidgets.QPushButton("选择主图背面")
        self.detail1_btn = QtWidgets.QPushButton("选择细节图一")
        self.detail2_btn = QtWidgets.QPushButton("选择细节图二")

        self.file_buttons = {
            "front": self.front_btn,
            "back": self.back_btn,
            "detail1": self.detail1_btn,
            "detail2": self.detail2_btn,
        }
        for key, btn in self.file_buttons.items():
            self.button_defaults[key] = btn.text()
            btn.clicked.connect(lambda _, k=key, b=btn: self.pick_file(k, b))
            layout.addWidget(btn)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addStretch(1)
        layout.addWidget(buttons)

        if existing:
            self._prefill_existing(existing)

    def pick_file(self, key: str, button: QtWidgets.QPushButton) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            self.file_paths[key] = file_path
            button.setText(Path(file_path).name)

    def accept(self) -> None:
        if self.require_images and not all(self.file_paths.values()):
            QtWidgets.QMessageBox.warning(self, "提示", "四张图片必须全部选择。")
            return
        if not self.name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "提示", "请填写婚纱名称。")
            return
        if not self.price_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "提示", "请填写价格。")
            return
        super().accept()

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "price": self.price_edit.text().strip(),
            "desc": self.desc_edit.toPlainText().strip(),
            **self.file_paths,
        }

    def _prefill_existing(self, entry: BridalEntry) -> None:
        self.name_edit.setText(entry.name)
        self.price_edit.setText(entry.price)
        self.desc_edit.setPlainText(entry.description)
        mapping = {
            "front": entry.front,
            "back": entry.back,
            "detail1": entry.detail1,
            "detail2": entry.detail2,
        }
        for key, path in mapping.items():
            btn = self.file_buttons.get(key)
            if btn:
                btn.setText(path.name)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
