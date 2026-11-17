from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List

from PyQt6 import QtCore, QtGui, QtWidgets
from PIL import Image

from .annotations import AnnotationFile, AnnotationItem, annotation_path, load_annotations, save_annotations
from .i18n import get_language, set_language, tr
from .pipeline import STEP_DEFS, Step, apply_pipeline, default_step
from .project import ensure_project_structure, list_raw_images, load_pipeline, save_pipeline
from .yolo_export import export_yolo_dataset
from .yolo_infer import cascade_detect


class AnnotationCanvas(QtWidgets.QGraphicsView):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QtWidgets.QGraphicsPixmapItem | None = None
        self._drawing_enabled = False
        self._drawing = False
        self._start_pos = QtCore.QPointF()
        self._temp_rect: QtWidgets.QGraphicsRectItem | None = None
        self.on_rect_created = None
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)

    def set_image(self, qimage: QtGui.QImage | None) -> None:
        self._scene.clear()
        self._pixmap_item = None
        if qimage is None:
            return
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QtCore.QRectF(0, 0, qimage.width(), qimage.height()))
        self.fitInView(self._scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def clear_annotations(self) -> None:
        if not self._pixmap_item:
            self._scene.clear()
            return
        items = [item for item in self._scene.items() if item is not self._pixmap_item]
        for item in items:
            self._scene.removeItem(item)

    def enable_drawing(self, enabled: bool) -> None:
        self._drawing_enabled = enabled
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag if enabled else QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)

    def add_rect(self, rect: QtCore.QRectF, color: QtGui.QColor, annotation_id: int) -> QtWidgets.QGraphicsRectItem:
        pen = QtGui.QPen(color, 2)
        pen.setCosmetic(True)
        brush = QtGui.QBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 18))
        item = self._scene.addRect(rect, pen, brush)
        item.setData(0, annotation_id)
        return item

    def highlight_item(self, annotation_id: int | None) -> None:
        for item in self._scene.items():
            if isinstance(item, QtWidgets.QGraphicsRectItem):
                pen = item.pen()
                pen.setWidth(2)
                if item.data(0) == annotation_id:
                    pen.setWidth(4)
                item.setPen(pen)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drawing_enabled and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drawing = True
            self._start_pos = self.mapToScene(event.position().toPoint())
            self._temp_rect = self._scene.addRect(QtCore.QRectF(self._start_pos, self._start_pos), QtGui.QPen(QtGui.QColor("#ff8800"), 2, QtCore.Qt.PenStyle.DashLine))
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drawing and self._temp_rect is not None:
            current = self.mapToScene(event.position().toPoint())
            rect = QtCore.QRectF(self._start_pos, current).normalized()
            self._temp_rect.setRect(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drawing and self._temp_rect is not None:
            rect = self._temp_rect.rect().normalized()
            self._scene.removeItem(self._temp_rect)
            self._temp_rect = None
            self._drawing = False
            if rect.width() >= 5 and rect.height() >= 5 and self.on_rect_created:
                self.on_rect_created(rect)
            return
        super().mouseReleaseEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        ensure_project_structure(self.root)

        self.language = get_language()
        if self.language not in ("uk", "sk"):
            self.language = "sk"
            set_language(self.language)

        self.setWindowTitle(tr("app.title"))
        self.resize(1280, 800)

        self.steps: List[Step] = load_pipeline(self.root)
        self.current_image_path: Path | None = None
        self.current_image: Image.Image | None = None
        self.current_original_qimage: QtGui.QImage | None = None
        self.current_processed_qimage: QtGui.QImage | None = None
        self.preview_dirty = True
        self.annotation_items: List[AnnotationItem] = []
        self.annotation_next_id = 1
        self.annotation_dirty = False
        self.annotation_level = "L1"
        self.annotation_rects: dict[int, QtWidgets.QGraphicsRectItem] = {}
        self.load_saved_annotations = True

        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._render_preview)

        self._build_ui()
        self._build_actions()
        self.apply_language(self.language)
        self.refresh_images()
        self.refresh_steps_list()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel: images
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)

        self.image_list = QtWidgets.QListWidget()
        self.image_list.currentItemChanged.connect(self.on_image_selected)
        self.lbl_images_title = QtWidgets.QLabel(tr("label.project_images"))
        left_layout.addWidget(self.lbl_images_title)
        left_layout.addWidget(self.image_list, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_import = QtWidgets.QPushButton(tr("button.import"))
        self.btn_import.clicked.connect(self.import_images)
        self.btn_refresh = QtWidgets.QPushButton(tr("button.refresh"))
        self.btn_refresh.clicked.connect(self.refresh_images)
        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(self.btn_refresh)
        left_layout.addLayout(btn_row)

        self.btn_apply_current = QtWidgets.QPushButton(tr("button.save_processed_current"))
        self.btn_apply_current.clicked.connect(self.save_current_processed)
        left_layout.addWidget(self.btn_apply_current)

        self.btn_apply_all = QtWidgets.QPushButton(tr("button.process_all"))
        self.btn_apply_all.clicked.connect(self.save_all_processed)
        left_layout.addWidget(self.btn_apply_all)

        splitter.addWidget(left_panel)

        # Center panel: tabs (preview + annotation)
        center_panel = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center_panel)
        center_layout.setContentsMargins(6, 6, 6, 6)

        self.center_tabs = QtWidgets.QTabWidget()
        center_layout.addWidget(self.center_tabs, 1)

        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(6, 6, 6, 6)

        preview_header = QtWidgets.QHBoxLayout()
        self.lbl_preview_title = QtWidgets.QLabel(tr("label.preview"))
        preview_header.addWidget(self.lbl_preview_title)
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setObjectName("statusLabel")
        self.lbl_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        preview_header.addWidget(self.lbl_status)
        preview_layout.addLayout(preview_header)

        preview_row = QtWidgets.QHBoxLayout()
        self.lbl_original = QtWidgets.QLabel(tr("label.original"))
        self.lbl_original.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_original.setMinimumSize(320, 320)
        self.lbl_original.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        self.lbl_processed = QtWidgets.QLabel(tr("label.processed"))
        self.lbl_processed.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_processed.setMinimumSize(320, 320)
        self.lbl_processed.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        preview_row.addWidget(self.lbl_original, 1)
        preview_row.addWidget(self.lbl_processed, 1)
        preview_layout.addLayout(preview_row, 1)

        self.center_tabs.addTab(preview_panel, tr("tab.preview"))

        annotation_panel = QtWidgets.QWidget()
        annotation_layout = QtWidgets.QHBoxLayout(annotation_panel)
        annotation_layout.setContentsMargins(6, 6, 6, 6)

        self.annotation_canvas = AnnotationCanvas()
        self.annotation_canvas.on_rect_created = self.on_rect_created
        self.annotation_canvas.enable_drawing(True)
        annotation_layout.addWidget(self.annotation_canvas, 1)

        annotation_side = QtWidgets.QWidget()
        annotation_side_layout = QtWidgets.QVBoxLayout(annotation_side)
        annotation_side_layout.setContentsMargins(6, 6, 6, 6)

        self.level_group = QtWidgets.QGroupBox(tr("group.annotation_level"))
        level_layout = QtWidgets.QVBoxLayout(self.level_group)
        self.level_l1 = QtWidgets.QRadioButton(tr("radio.l1_sections"))
        self.level_l2 = QtWidgets.QRadioButton(tr("radio.l2_pairs"))
        self.level_l3 = QtWidgets.QRadioButton(tr("radio.l3_elements"))
        self.level_l1.setChecked(True)
        self.level_l1.toggled.connect(lambda checked: checked and self.set_annotation_level("L1"))
        self.level_l2.toggled.connect(lambda checked: checked and self.set_annotation_level("L2"))
        self.level_l3.toggled.connect(lambda checked: checked and self.set_annotation_level("L3"))
        level_layout.addWidget(self.level_l1)
        level_layout.addWidget(self.level_l2)
        level_layout.addWidget(self.level_l3)
        annotation_side_layout.addWidget(self.level_group)

        self.annotation_hint = QtWidgets.QLabel(tr("hint.draw_select_level"))
        self.annotation_hint.setWordWrap(True)
        annotation_side_layout.addWidget(self.annotation_hint)

        self.chk_load_annotations = QtWidgets.QCheckBox(tr("checkbox.load_annotations"))
        self.chk_load_annotations.setChecked(True)
        self.chk_load_annotations.toggled.connect(self.set_load_saved_annotations)
        annotation_side_layout.addWidget(self.chk_load_annotations)

        self.list_l1 = QtWidgets.QListWidget()
        self.list_l2 = QtWidgets.QListWidget()
        self.list_l3 = QtWidgets.QListWidget()
        self.list_l3.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_l1.currentItemChanged.connect(self.on_l1_selected)
        self.list_l2.currentItemChanged.connect(self.on_l2_selected)
        self.list_l3.currentItemChanged.connect(self.on_l3_selected)

        self.lbl_l1_title = QtWidgets.QLabel(tr("label.l1_sections"))
        annotation_side_layout.addWidget(self.lbl_l1_title)
        annotation_side_layout.addWidget(self.list_l1, 1)
        self.btn_delete_l1 = QtWidgets.QPushButton(tr("button.delete_l1"))
        self.btn_delete_l1.clicked.connect(lambda: self.delete_selected("L1"))
        annotation_side_layout.addWidget(self.btn_delete_l1)

        self.lbl_l2_title = QtWidgets.QLabel(tr("label.l2_pairs"))
        annotation_side_layout.addWidget(self.lbl_l2_title)
        annotation_side_layout.addWidget(self.list_l2, 1)
        self.btn_delete_l2 = QtWidgets.QPushButton(tr("button.delete_l2"))
        self.btn_delete_l2.clicked.connect(lambda: self.delete_selected("L2"))
        annotation_side_layout.addWidget(self.btn_delete_l2)

        self.lbl_l3_title = QtWidgets.QLabel(tr("label.l3_elements"))
        annotation_side_layout.addWidget(self.lbl_l3_title)
        annotation_side_layout.addWidget(self.list_l3, 1)
        self.btn_delete_l3 = QtWidgets.QPushButton(tr("button.delete_l3"))
        self.btn_delete_l3.clicked.connect(lambda: self.delete_selected("L3"))
        annotation_side_layout.addWidget(self.btn_delete_l3)

        self.btn_mark_symbol = QtWidgets.QPushButton(tr("button.mark_symbol"))
        self.btn_mark_symbol.clicked.connect(lambda: self.mark_selected_l3_label("symbol"))
        annotation_side_layout.addWidget(self.btn_mark_symbol)

        self.btn_mark_not_symbol = QtWidgets.QPushButton(tr("button.mark_not_symbol"))
        self.btn_mark_not_symbol.clicked.connect(lambda: self.mark_selected_l3_label("not_symbol"))
        annotation_side_layout.addWidget(self.btn_mark_not_symbol)

        self.btn_clear_symbol = QtWidgets.QPushButton(tr("button.clear_l3_label"))
        self.btn_clear_symbol.clicked.connect(lambda: self.mark_selected_l3_label(""))
        annotation_side_layout.addWidget(self.btn_clear_symbol)

        self.btn_mark_rest_not_symbol = QtWidgets.QPushButton(tr("button.mark_rest_not_symbol"))
        self.btn_mark_rest_not_symbol.clicked.connect(self.mark_rest_l3_not_symbol)
        annotation_side_layout.addWidget(self.btn_mark_rest_not_symbol)

        self.btn_save_annotations = QtWidgets.QPushButton(tr("button.save_annotations"))
        self.btn_save_annotations.clicked.connect(self.save_annotations_current)
        annotation_side_layout.addWidget(self.btn_save_annotations)

        self.btn_auto_annotations = QtWidgets.QPushButton(tr("button.auto_annotate"))
        self.btn_auto_annotations.clicked.connect(self.auto_annotate)
        annotation_side_layout.addWidget(self.btn_auto_annotations)

        self.btn_auto_annotations_batch = QtWidgets.QPushButton(tr("button.auto_annotate_batch"))
        self.btn_auto_annotations_batch.clicked.connect(self.auto_annotate_batch)
        annotation_side_layout.addWidget(self.btn_auto_annotations_batch)

        self.btn_export_yolo = QtWidgets.QPushButton(tr("button.export_yolo_all"))
        self.btn_export_yolo.clicked.connect(self.export_yolo_all)
        annotation_side_layout.addWidget(self.btn_export_yolo)

        self.btn_yolo_auto = QtWidgets.QPushButton(tr("button.yolo_auto_annotate"))
        self.btn_yolo_auto.clicked.connect(self.yolo_auto_annotate)
        annotation_side_layout.addWidget(self.btn_yolo_auto)

        annotation_layout.addWidget(annotation_side)

        self.center_tabs.addTab(annotation_panel, tr("tab.annotation"))

        splitter.addWidget(center_panel)

        # Right panel: pipeline constructor
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)

        self.lbl_pipeline_title = QtWidgets.QLabel(tr("label.pipeline_builder"))
        right_layout.addWidget(self.lbl_pipeline_title)
        self.steps_list = QtWidgets.QListWidget()
        self.steps_list.currentItemChanged.connect(self.on_step_selected)
        self.steps_list.itemChanged.connect(self.on_step_item_changed)
        right_layout.addWidget(self.steps_list, 1)

        step_buttons = QtWidgets.QHBoxLayout()
        self.step_combo = QtWidgets.QComboBox()
        self._populate_step_combo()
        self.btn_add_step = QtWidgets.QPushButton(tr("button.add"))
        self.btn_add_step.clicked.connect(self.add_step)
        self.btn_remove_step = QtWidgets.QPushButton(tr("button.remove"))
        self.btn_remove_step.clicked.connect(self.remove_step)
        step_buttons.addWidget(self.step_combo)
        step_buttons.addWidget(self.btn_add_step)
        step_buttons.addWidget(self.btn_remove_step)
        right_layout.addLayout(step_buttons)

        order_buttons = QtWidgets.QHBoxLayout()
        self.btn_up = QtWidgets.QPushButton(tr("button.up"))
        self.btn_up.clicked.connect(self.move_step_up)
        self.btn_down = QtWidgets.QPushButton(tr("button.down"))
        self.btn_down.clicked.connect(self.move_step_down)
        order_buttons.addWidget(self.btn_up)
        order_buttons.addWidget(self.btn_down)
        right_layout.addLayout(order_buttons)

        self.params_group = QtWidgets.QGroupBox(tr("group.step_params"))
        self.params_form = QtWidgets.QFormLayout(self.params_group)
        right_layout.addWidget(self.params_group)

        pipeline_buttons = QtWidgets.QHBoxLayout()
        self.btn_save_pipeline = QtWidgets.QPushButton(tr("button.save_pipeline"))
        self.btn_save_pipeline.clicked.connect(self.save_pipeline)
        self.btn_load_pipeline = QtWidgets.QPushButton(tr("button.load_pipeline"))
        self.btn_load_pipeline.clicked.connect(self.load_pipeline)
        pipeline_buttons.addWidget(self.btn_save_pipeline)
        pipeline_buttons.addWidget(self.btn_load_pipeline)
        right_layout.addLayout(pipeline_buttons)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 2)

    def _build_actions(self) -> None:
        self.view_menu = self.menuBar().addMenu(tr("menu.view"))
        self.action_fullscreen = QtGui.QAction(tr("action.fullscreen"), self)
        self.action_fullscreen.setCheckable(True)
        self.action_fullscreen.setShortcut(QtGui.QKeySequence("F11"))
        self.action_fullscreen.triggered.connect(self.toggle_fullscreen)
        self.view_menu.addAction(self.action_fullscreen)

        self.action_exit_fullscreen = QtGui.QAction(tr("action.exit_fullscreen"), self)
        self.action_exit_fullscreen.setShortcut(QtGui.QKeySequence("Escape"))
        self.action_exit_fullscreen.triggered.connect(self.exit_fullscreen)
        self.addAction(self.action_exit_fullscreen)

        self.language_menu = self.menuBar().addMenu(tr("menu.language"))
        self.action_language_uk = QtGui.QAction(tr("action.lang_uk"), self)
        self.action_language_uk.setCheckable(True)
        self.action_language_sk = QtGui.QAction(tr("action.lang_sk"), self)
        self.action_language_sk.setCheckable(True)
        lang_group = QtGui.QActionGroup(self)
        lang_group.setExclusive(True)
        lang_group.addAction(self.action_language_uk)
        lang_group.addAction(self.action_language_sk)
        self.language_menu.addAction(self.action_language_uk)
        self.language_menu.addAction(self.action_language_sk)
        self.action_language_uk.triggered.connect(lambda checked: checked and self.apply_language("uk"))
        self.action_language_sk.triggered.connect(lambda checked: checked and self.apply_language("sk"))

    def _step_label(self, step_type: str) -> str:
        meta = STEP_DEFS.get(step_type, {})
        label_key = meta.get("label_key")
        if label_key:
            return tr(label_key)
        return meta.get("label", step_type)

    def _populate_step_combo(self) -> None:
        current = self.step_combo.currentData()
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        for key in STEP_DEFS.keys():
            self.step_combo.addItem(self._step_label(key), key)
        if current:
            idx = self.step_combo.findData(current)
            if idx >= 0:
                self.step_combo.setCurrentIndex(idx)
        self.step_combo.blockSignals(False)

    def apply_language(self, lang: str) -> None:
        if lang not in ("uk", "sk"):
            return
        set_language(lang)
        self.language = lang
        self.setWindowTitle(tr("app.title"))

        self.lbl_images_title.setText(tr("label.project_images"))
        self.lbl_preview_title.setText(tr("label.preview"))
        self.lbl_original.setText(tr("label.original"))
        self.lbl_processed.setText(tr("label.processed"))
        self.center_tabs.setTabText(0, tr("tab.preview"))
        self.center_tabs.setTabText(1, tr("tab.annotation"))
        self.level_group.setTitle(tr("group.annotation_level"))
        self.level_l1.setText(tr("radio.l1_sections"))
        self.level_l2.setText(tr("radio.l2_pairs"))
        self.level_l3.setText(tr("radio.l3_elements"))
        self.annotation_hint.setText(tr("hint.draw_select_level"))
        self.chk_load_annotations.setText(tr("checkbox.load_annotations"))
        self.lbl_l1_title.setText(tr("label.l1_sections"))
        self.lbl_l2_title.setText(tr("label.l2_pairs"))
        self.lbl_l3_title.setText(tr("label.l3_elements"))
        self.btn_delete_l1.setText(tr("button.delete_l1"))
        self.btn_delete_l2.setText(tr("button.delete_l2"))
        self.btn_delete_l3.setText(tr("button.delete_l3"))
        self.btn_mark_symbol.setText(tr("button.mark_symbol"))
        self.btn_mark_not_symbol.setText(tr("button.mark_not_symbol"))
        self.btn_clear_symbol.setText(tr("button.clear_l3_label"))
        self.btn_mark_rest_not_symbol.setText(tr("button.mark_rest_not_symbol"))
        self.btn_save_annotations.setText(tr("button.save_annotations"))
        self.btn_auto_annotations.setText(tr("button.auto_annotate"))
        self.btn_auto_annotations_batch.setText(tr("button.auto_annotate_batch"))
        self.btn_export_yolo.setText(tr("button.export_yolo_all"))
        self.btn_yolo_auto.setText(tr("button.yolo_auto_annotate"))
        self.lbl_pipeline_title.setText(tr("label.pipeline_builder"))
        self.btn_add_step.setText(tr("button.add"))
        self.btn_remove_step.setText(tr("button.remove"))
        self.btn_up.setText(tr("button.up"))
        self.btn_down.setText(tr("button.down"))
        self.params_group.setTitle(tr("group.step_params"))
        self.btn_save_pipeline.setText(tr("button.save_pipeline"))
        self.btn_load_pipeline.setText(tr("button.load_pipeline"))
        self.btn_import.setText(tr("button.import"))
        self.btn_refresh.setText(tr("button.refresh"))
        self.btn_apply_current.setText(tr("button.save_processed_current"))
        self.btn_apply_all.setText(tr("button.process_all"))

        self.view_menu.setTitle(tr("menu.view"))
        self.action_fullscreen.setText(tr("action.fullscreen"))
        self.action_exit_fullscreen.setText(tr("action.exit_fullscreen"))
        self.language_menu.setTitle(tr("menu.language"))
        self.action_language_uk.setText(tr("action.lang_uk"))
        self.action_language_sk.setText(tr("action.lang_sk"))
        self.action_language_uk.setChecked(self.language == "uk")
        self.action_language_sk.setChecked(self.language == "sk")

        self._populate_step_combo()
        self.refresh_steps_list()
        self.set_annotation_level(self.annotation_level)
    def toggle_fullscreen(self, enabled: bool) -> None:
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            if hasattr(self, "action_fullscreen"):
                self.action_fullscreen.setChecked(False)

    def refresh_images(self) -> None:
        self.image_list.clear()
        for path in list_raw_images(self.root):
            item = QtWidgets.QListWidgetItem(path.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            self.image_list.addItem(item)

    def on_image_selected(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if self.annotation_dirty:
            self.save_annotations_current(silent=True)
        if not current:
            self.current_image_path = None
            self.current_image = None
            self.current_original_qimage = None
            self.current_processed_qimage = None
            self.preview_dirty = True
            self.annotation_canvas.set_image(None)
            self.clear_annotation_state()
            self.update_preview()
            return
        path = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(path, Path):
            return
        try:
            self.current_image = Image.open(path)
            self.current_image_path = path
            self.lbl_status.setText(path.name)
            self.current_original_qimage = self._pil_to_qimage(self.current_image)
            self.current_processed_qimage = None
            self.annotation_canvas.set_image(self.current_original_qimage)
            self.clear_annotation_state()
            if self.load_saved_annotations:
                self.load_annotations_for_current()
            self.preview_dirty = True
            self.update_preview()
        except Exception as exc:
            self.current_image = None
            self.current_image_path = None
            self.lbl_status.setText("")
            self.current_original_qimage = None
            self.current_processed_qimage = None
            self.annotation_canvas.set_image(None)
            self.clear_annotation_state()
            QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.load_image_failed").format(exc=exc))

    def update_preview(self) -> None:
        self.preview_dirty = True
        if self.preview_timer.isActive():
            self.preview_timer.stop()
        self.preview_timer.start(120)

    def _render_preview(self) -> None:
        if not self.current_image:
            self.lbl_original.setText(tr("label.original"))
            self.lbl_processed.setText(tr("label.processed"))
            self.lbl_original.setPixmap(QtGui.QPixmap())
            self.lbl_processed.setPixmap(QtGui.QPixmap())
            return
        if self.preview_dirty or self.current_original_qimage is None or self.current_processed_qimage is None:
            self.current_original_qimage = self._pil_to_qimage(self.current_image)
            processed = apply_pipeline(self.current_image, self.steps)
            self.current_processed_qimage = self._pil_to_qimage(processed)
            self.preview_dirty = False
        if self.current_original_qimage:
            self._set_qimage_on_label(self.lbl_original, self.current_original_qimage)
        if self.current_processed_qimage:
            self._set_qimage_on_label(self.lbl_processed, self.current_processed_qimage)
        if self.current_original_qimage:
            self.annotation_canvas.set_image(self.current_original_qimage)
        self._redraw_annotations()

    def _set_qimage_on_label(self, label: QtWidgets.QLabel, qimage: QtGui.QImage) -> None:
        pixmap = QtGui.QPixmap.fromImage(qimage)
        if label.width() > 0 and label.height() > 0:
            pixmap = pixmap.scaled(label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pixmap)

    def _pil_to_qimage(self, image: Image.Image) -> QtGui.QImage:
        if image.mode == "RGB":
            data = image.tobytes("raw", "RGB")
            qimage = QtGui.QImage(data, image.width, image.height, image.width*3, QtGui.QImage.Format.Format_RGB888)
            return qimage.copy()
        if image.mode == "RGBA":
            data = image.tobytes("raw", "RGBA")
            qimage = QtGui.QImage(data, image.width, image.height, image.width*4, QtGui.QImage.Format.Format_RGBA8888)
            return qimage.copy()
        gray = image.convert("L")
        data = gray.tobytes("raw", "L")
        qimage = QtGui.QImage(data, gray.width, gray.height, gray.width, QtGui.QImage.Format.Format_Grayscale8)
        return qimage.copy()

    def set_load_saved_annotations(self, enabled: bool) -> None:
        self.load_saved_annotations = enabled

    def set_annotation_level(self, level: str) -> None:
        self.annotation_level = level
        if level == "L1":
            self.annotation_hint.setText(tr("hint.draw_l1"))
        elif level == "L2":
            self.annotation_hint.setText(tr("hint.draw_l2"))
        else:
            self.annotation_hint.setText(tr("hint.draw_l3"))

    def on_rect_created(self, rect: QtCore.QRectF) -> None:
        if not self.current_image_path:
            return
        parent_id = None
        if self.annotation_level == "L2":
            parent_id = self._infer_parent_id(rect, "L1")
            if parent_id is None:
                QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.no_l1_for_l2"))
                return
        if self.annotation_level == "L3":
            parent_id = self._infer_parent_id(rect, "L2")
            if parent_id is None:
                parent_id = self._infer_parent_id(rect, "L1")
                if parent_id is None:
                    QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.no_l2_or_l1_for_l3"))
                    return
        self.add_annotation(self.annotation_level, rect, parent_id)

    def add_annotation(self, level: str, rect: QtCore.QRectF, parent_id: int | None) -> None:
        annotation_id = self.annotation_next_id
        self.annotation_next_id += 1
        bbox = [int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())]
        item = AnnotationItem(id=annotation_id, level=level, parent_id=parent_id, bbox=bbox)
        self.annotation_items.append(item)
        color = self._item_color(item)
        rect_item = self.annotation_canvas.add_rect(rect, color, annotation_id)
        self.annotation_rects[annotation_id] = rect_item
        self.annotation_dirty = True
        self.refresh_annotation_lists()

    def load_annotations_for_current(self) -> None:
        self.clear_annotation_state()
        if not self.current_image_path:
            return
        path = annotation_path(self.root, self.current_image_path)
        if not path.exists():
            return
        data = load_annotations(path)
        self.annotation_items = data.items
        self.annotation_next_id = data.next_id
        for item in self.annotation_items:
            rect = QtCore.QRectF(item.bbox[0], item.bbox[1], item.bbox[2], item.bbox[3])
            rect_item = self.annotation_canvas.add_rect(rect, self._item_color(item), item.id)
            self.annotation_rects[item.id] = rect_item
        self.annotation_dirty = False
        self.refresh_annotation_lists()

    def save_annotations_current(self, silent: bool = False) -> None:
        if not self.annotation_dirty:
            return
        if not self.current_image_path:
            self.annotation_dirty = False
            return
        path = annotation_path(self.root, self.current_image_path)
        if not self.annotation_items:
            if path.exists():
                path.unlink()
            self.annotation_dirty = False
            return
        data = AnnotationFile(image=self.current_image_path.name, items=self.annotation_items, next_id=self.annotation_next_id)
        save_annotations(path, data)
        self.annotation_dirty = False
        if not silent:
            QtWidgets.QMessageBox.information(
                self,
                tr("message.done_title"),
                tr("message.annotations_saved").format(name=path.name),
            )

    def clear_annotation_state(self) -> None:
        self.annotation_items = []
        self.annotation_next_id = 1
        self.annotation_dirty = False
        self.annotation_rects.clear()
        self.annotation_canvas.clear_annotations()
        self.refresh_annotation_lists()

    def refresh_annotation_lists(self) -> None:
        selected_l1 = self._selected_id(self.list_l1)
        selected_l2 = self._selected_id(self.list_l2)
        selected_l3 = self._selected_id(self.list_l3)
        indexed = {item.id:item for item in self.annotation_items}
        pair = indexed.get(selected_l2)
        if pair is None or pair.parent_id != selected_l1:
            selected_l2 = None
        element = indexed.get(selected_l3)
        if element is None or element.parent_id not in {selected_l1,selected_l2}:
            selected_l3 = None

        blocker_l1 = QtCore.QSignalBlocker(self.list_l1)
        blocker_l2 = QtCore.QSignalBlocker(self.list_l2)
        blocker_l3 = QtCore.QSignalBlocker(self.list_l3)

        self.list_l1.clear()
        self.list_l2.clear()
        self.list_l3.clear()

        for item in self.annotation_items:
            if item.level == "L1":
                self._add_list_item(self.list_l1, item)

        for item in self.annotation_items:
            if item.level == "L2" and item.parent_id == selected_l1:
                self._add_list_item(self.list_l2, item)

        for item in self.annotation_items:
            if item.level == "L3" and item.parent_id == selected_l2:
                self._add_list_item(self.list_l3, item)
        if selected_l2 is None and selected_l1 is not None:
            for item in self.annotation_items:
                if item.level == "L3" and item.parent_id == selected_l1:
                    self._add_list_item(self.list_l3, item)

        self._select_item_by_id(self.list_l1, selected_l1)
        self._select_item_by_id(self.list_l2, selected_l2)
        self._select_item_by_id(self.list_l3, selected_l3)

        del blocker_l1
        del blocker_l2
        del blocker_l3

    def _list_label(self, item: AnnotationItem) -> str:
        label = f" ({item.label})" if item.label else ""
        return f"#{item.id} [{item.bbox[0]},{item.bbox[1]},{item.bbox[2]}x{item.bbox[3]}]{label}"

    def _selected_id(self, widget: QtWidgets.QListWidget) -> int | None:
        item = widget.currentItem()
        if not item:
            return None
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, int):
            return data
        return None

    def _add_list_item(self, widget: QtWidgets.QListWidget, item: AnnotationItem) -> None:
        list_item = QtWidgets.QListWidgetItem(self._list_label(item))
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item.id)
        widget.addItem(list_item)

    def _select_item_by_id(self, widget: QtWidgets.QListWidget, annotation_id: int | None) -> None:
        if annotation_id is None:
            return
        for i in range(widget.count()):
            item = widget.item(i)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == annotation_id:
                widget.setCurrentItem(item)
                return

    def on_l1_selected(self, current: QtWidgets.QListWidgetItem | None) -> None:
        self.refresh_annotation_lists()
        self.annotation_canvas.highlight_item(self._selected_id(self.list_l1))

    def on_l2_selected(self, current: QtWidgets.QListWidgetItem | None) -> None:
        self.refresh_annotation_lists()
        self.annotation_canvas.highlight_item(self._selected_id(self.list_l2))

    def on_l3_selected(self, current: QtWidgets.QListWidgetItem | None) -> None:
        self.annotation_canvas.highlight_item(self._selected_id(self.list_l3))

    def delete_selected(self, level: str) -> None:
        widget = self.list_l1 if level == "L1" else self.list_l2 if level == "L2" else self.list_l3
        selected_id = self._selected_id(widget)
        if selected_id is None:
            return
        self.delete_annotation(selected_id)

    def delete_annotation(self, annotation_id: int) -> None:
        item = next((i for i in self.annotation_items if i.id == annotation_id), None)
        if not item:
            return
        to_remove = {annotation_id}
        if item.level == "L1":
            to_remove.update(i.id for i in self.annotation_items if i.parent_id == annotation_id)
            to_remove.update(i.id for i in self.annotation_items if i.parent_id in to_remove)
        if item.level == "L2":
            to_remove.update(i.id for i in self.annotation_items if i.parent_id == annotation_id)
        self.annotation_items = [i for i in self.annotation_items if i.id not in to_remove]
        for rid in to_remove:
            rect_item = self.annotation_rects.pop(rid, None)
            if rect_item:
                self.annotation_canvas.scene().removeItem(rect_item)
        self.annotation_dirty = True
        self.refresh_annotation_lists()

    def _selected_ids(self, widget: QtWidgets.QListWidget) -> List[int]:
        selected = []
        for item in widget.selectedItems():
            data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, int):
                selected.append(data)
        return selected

    def mark_selected_l3_label(self, label: str) -> None:
        selected_ids = set(self._selected_ids(self.list_l3))
        if not selected_ids:
            return
        changed = False
        for item in self.annotation_items:
            if item.level != "L3" or item.id not in selected_ids:
                continue
            new_label = label
            if new_label == "":
                new_label = ""
            if item.label != new_label:
                item.label = new_label
                changed = True
        if changed:
            self.annotation_dirty = True
            self.refresh_annotation_lists()
            self._redraw_annotations()

    def mark_rest_l3_not_symbol(self) -> None:
        selected_ids = set(self._selected_ids(self.list_l3))
        count = 0
        for item in self.annotation_items:
            if item.level != "L3":
                continue
            if item.id in selected_ids:
                continue
            if item.label:
                continue
            item.label = "not_symbol"
            count += 1
        if count:
            self.annotation_dirty = True
            self.refresh_annotation_lists()
            self._redraw_annotations()

    def _level_color(self, level: str) -> QtGui.QColor:
        if level == "L1":
            return QtGui.QColor("#a9684a")
        if level == "L2":
            return QtGui.QColor("#9b7a2c")
        return QtGui.QColor("#2e7d32")

    def _item_color(self, item: AnnotationItem) -> QtGui.QColor:
        if item.level != "L3":
            return self._level_color(item.level)
        if item.label == "symbol":
            return QtGui.QColor("#2e7d32")
        if item.label == "not_symbol":
            return QtGui.QColor("#757575")
        return QtGui.QColor("#2e7d32")

    def _infer_parent_id(self, rect: QtCore.QRectF, parent_level: str) -> int | None:
        rect_box = (rect.x(), rect.y(), rect.width(), rect.height())
        center_x = rect.x() + rect.width() / 2
        center_y = rect.y() + rect.height() / 2
        containing: list[tuple[int, float]] = []
        best_id = None
        best_score = 0.0
        for item in self.annotation_items:
            if item.level != parent_level:
                continue
            px, py, pw, ph = item.bbox
            if px <= center_x <= px + pw and py <= center_y <= py + ph:
                score = self._iou(rect_box, (px, py, pw, ph))
                containing.append((item.id, score))
                continue
            score = self._iou(rect_box, (px, py, pw, ph))
            if score > best_score:
                best_score = score
                best_id = item.id
        if containing:
            containing.sort(key=lambda pair: pair[1], reverse=True)
            best_id = containing[0][0]
        if best_id is None:
            return None
        if parent_level == "L1":
            self._select_item_by_id(self.list_l1, best_id)
        if parent_level == "L2":
            self._select_item_by_id(self.list_l2, best_id)
        return best_id

    def _iou(self, a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        a_right = ax + aw
        a_bottom = ay + ah
        b_right = bx + bw
        b_bottom = by + bh
        inter_left = max(ax, bx)
        inter_top = max(ay, by)
        inter_right = min(a_right, b_right)
        inter_bottom = min(a_bottom, b_bottom)
        if inter_right <= inter_left or inter_bottom <= inter_top:
            return 0.0
        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        a_area = aw * ah
        b_area = bw * bh
        union = a_area + b_area - inter_area
        if union <= 0:
            return 0.0
        return inter_area / union

    def export_yolo_all(self) -> None:
        if self.annotation_dirty:
            self.save_annotations_current(silent=True)
        results = []
        for level in ("L1", "L2", "L3"):
            res = export_yolo_dataset(self.root, level)
            results.append(f"{level}: {res.labels} labels")
        QtWidgets.QMessageBox.information(
            self,
            tr("message.done_title"),
            tr("message.export_done").format(details="\n".join(results)),
        )

    def yolo_auto_annotate(self) -> None:
        if not self.current_image:
            return
        if self.annotation_items:
            reply = QtWidgets.QMessageBox.question(
                self,
                tr("message.confirm_title"),
                tr("message.overwrite_confirm"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        config_path = self.root / "results" / "yolo_config.json"
        if not config_path.exists():
            QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.yolo_config_missing"))
            return
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        weights_l1 = self.root / cfg.get("L1", "")
        weights_l2 = self.root / cfg.get("L2", "")
        weights_l3 = self.root / cfg.get("L3", "")
        conf = cfg.get("conf", {})
        conf_l1 = float(conf.get("L1", 0.25))
        conf_l2 = float(conf.get("L2", 0.25))
        conf_l3 = float(conf.get("L3", 0.25))

        if not weights_l1.exists() or not weights_l2.exists() or not weights_l3.exists():
            QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.yolo_weights_missing"))
            return

        try:
            l1_boxes, l2_boxes, l3_boxes = cascade_detect(
                self.current_image,
                weights_l1,
                weights_l2,
                weights_l3,
                conf_l1=conf_l1,
                conf_l2=conf_l2,
                conf_l3=conf_l3,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("message.error_title"), tr("message.yolo_error").format(exc=exc))
            return
        self._log_yolo_result(l1_boxes, l2_boxes, l3_boxes)
        if not l1_boxes and not l2_boxes and not l3_boxes:
            QtWidgets.QMessageBox.information(self, tr("message.result_title"), tr("message.yolo_no_objects"))
            return

        self.clear_annotation_state()
        self.annotation_next_id = 1
        l1_ids: List[int] = []
        for box in l1_boxes:
            l1_ids.append(self._create_annotation_item("L1", int(box.x1), int(box.y1), int(box.x2), int(box.y2), None))

        for box in l2_boxes:
            rect = QtCore.QRectF(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1)
            parent_id = self._infer_parent_id(rect, "L1")
            self._create_annotation_item("L2", int(box.x1), int(box.y1), int(box.x2), int(box.y2), parent_id)

        for box in l3_boxes:
            rect = QtCore.QRectF(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1)
            parent_id = self._infer_parent_id(rect, "L2")
            self._create_annotation_item("L3", int(box.x1), int(box.y1), int(box.x2), int(box.y2), parent_id)

        self.annotation_dirty = True
        self.refresh_annotation_lists()
        self._ensure_annotation_view()
        QtWidgets.QMessageBox.information(self, tr("message.done_title"), tr("message.yolo_auto_done"))

    def _log_yolo_result(self, l1_boxes: List[Any], l2_boxes: List[Any], l3_boxes: List[Any]) -> None:
        log_path = self.root / "results" / "yolo_auto.log"
        line = f"{datetime.now().isoformat()} L1={len(l1_boxes)} L2={len(l2_boxes)} L3={len(l3_boxes)}\n"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(line)

    def auto_annotate(self) -> None:
        if not self.current_image:
            return
        if self.annotation_items:
            reply = QtWidgets.QMessageBox.question(
                self,
                tr("message.confirm_title"),
                tr("message.overwrite_confirm"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        base_image = apply_pipeline(self.current_image, self.steps) if self.steps else self.current_image
        gray = base_image.convert("L")
        threshold = self._otsu_threshold(gray)
        width, height = gray.size
        data = list(gray.getdata())
        bin_data = [1 if v < threshold else 0 for v in data]

        row_sums = [sum(bin_data[y * width:(y + 1) * width]) for y in range(height)]
        row_thresh = max(1, int(width * 0.01))
        line_segments = self._find_runs(row_sums, row_thresh, min_len=3, gap_tol=2)
        if not line_segments:
            QtWidgets.QMessageBox.information(self, tr("message.result_title"), tr("message.no_rows_l2"))
            return

        line_infos: List[dict[str, object]] = []
        for top, bottom in line_segments:
            col_sums = [0] * width
            for y in range(top, bottom + 1):
                row_start = y * width
                for x in range(width):
                    col_sums[x] += bin_data[row_start + x]
            col_thresh = max(1, int((bottom - top + 1) * 0.1))
            col_segments = self._find_runs(col_sums, col_thresh, min_len=3, gap_tol=2)
            if not col_segments:
                continue
            left = col_segments[0][0]
            right = col_segments[-1][1]
            line_infos.append({
                "top": top,
                "bottom": bottom,
                "left": left,
                "right": right,
                "segments": col_segments,
            })

        if not line_infos:
            QtWidgets.QMessageBox.information(self, tr("message.result_title"), tr("message.no_elements_l3"))
            return

        block_gap = max(20, int(height * 0.03))
        line_infos.sort(key=lambda x: int(x["top"]))  # type: ignore[index]
        blocks: List[List[dict[str, object]]] = []
        current_block: List[dict[str, object]] = []
        last_bottom = None
        for line in line_infos:
            top = int(line["top"])  # type: ignore[index]
            if last_bottom is not None and top - last_bottom > block_gap:
                if current_block:
                    blocks.append(current_block)
                current_block = []
            current_block.append(line)
            last_bottom = int(line["bottom"])  # type: ignore[index]
        if current_block:
            blocks.append(current_block)

        self.clear_annotation_state()
        self.annotation_next_id = 1
        for block in blocks:
            block_top = min(int(line["top"]) for line in block)  # type: ignore[index]
            block_bottom = max(int(line["bottom"]) for line in block)  # type: ignore[index]
            block_left = min(int(line["left"]) for line in block)  # type: ignore[index]
            block_right = max(int(line["right"]) for line in block)  # type: ignore[index]

            l1_id = self._create_annotation_item("L1", block_left, block_top, block_right, block_bottom, None)
            for line in block:
                l2_id = self._create_annotation_item(
                    "L2",
                    int(line["left"]),  # type: ignore[index]
                    int(line["top"]),  # type: ignore[index]
                    int(line["right"]),  # type: ignore[index]
                    int(line["bottom"]),  # type: ignore[index]
                    l1_id,
                )
                segments = line["segments"]  # type: ignore[index]
                for seg_left, seg_right in segments:
                    self._create_annotation_item(
                        "L3",
                        int(seg_left),
                        int(line["top"]),  # type: ignore[index]
                        int(seg_right),
                        int(line["bottom"]),  # type: ignore[index]
                        l2_id,
                    )

        self.annotation_dirty = True
        self.refresh_annotation_lists()
        self._ensure_annotation_view()
        QtWidgets.QMessageBox.information(self, tr("message.done_title"), tr("message.auto_done"))

    def auto_annotate_batch(self) -> None:
        raw_images = list_raw_images(self.root)
        if not raw_images:
            QtWidgets.QMessageBox.information(self, tr("message.result_title"), tr("message.no_images_raw"))
            return
        count, ok = QtWidgets.QInputDialog.getInt(
            self,
            tr("dialog.auto_batch_title"),
            tr("dialog.auto_batch_prompt"),
            min(20, len(raw_images)),
            1,
            len(raw_images),
        )
        if not ok:
            return
        processed = 0
        for path in raw_images[:count]:
            try:
                image = Image.open(path)
                items = self._auto_annotate_image(image)
                if items:
                    ann_path = annotation_path(self.root, path)
                    data = AnnotationFile(image=path.name, items=items, next_id=max(i.id for i in items) + 1)
                    save_annotations(ann_path, data)
                processed += 1
            except Exception:
                continue
        QtWidgets.QMessageBox.information(
            self,
            tr("message.done_title"),
            tr("message.auto_batch_done").format(processed=processed, count=count),
        )

    def _auto_annotate_image(self, image: Image.Image) -> List[AnnotationItem]:
        base_image = apply_pipeline(image, self.steps) if self.steps else image
        gray = base_image.convert("L")
        threshold = self._otsu_threshold(gray)
        width, height = gray.size
        data = list(gray.getdata())
        bin_data = [1 if v < threshold else 0 for v in data]

        row_sums = [sum(bin_data[y * width:(y + 1) * width]) for y in range(height)]
        row_thresh = max(1, int(width * 0.01))
        line_segments = self._find_runs(row_sums, row_thresh, min_len=3, gap_tol=2)
        if not line_segments:
            return []

        line_infos: List[dict[str, object]] = []
        for top, bottom in line_segments:
            col_sums = [0] * width
            for y in range(top, bottom + 1):
                row_start = y * width
                for x in range(width):
                    col_sums[x] += bin_data[row_start + x]
            col_thresh = max(1, int((bottom - top + 1) * 0.1))
            col_segments = self._find_runs(col_sums, col_thresh, min_len=3, gap_tol=2)
            if not col_segments:
                continue
            left = col_segments[0][0]
            right = col_segments[-1][1]
            line_infos.append({
                "top": top,
                "bottom": bottom,
                "left": left,
                "right": right,
                "segments": col_segments,
            })

        if not line_infos:
            return []

        block_gap = max(20, int(height * 0.03))
        line_infos.sort(key=lambda x: int(x["top"]))  # type: ignore[index]
        blocks: List[List[dict[str, object]]] = []
        current_block: List[dict[str, object]] = []
        last_bottom = None
        for line in line_infos:
            top = int(line["top"])  # type: ignore[index]
            if last_bottom is not None and top - last_bottom > block_gap:
                if current_block:
                    blocks.append(current_block)
                current_block = []
            current_block.append(line)
            last_bottom = int(line["bottom"])  # type: ignore[index]
        if current_block:
            blocks.append(current_block)

        items: List[AnnotationItem] = []
        next_id = 1
        for block in blocks:
            block_top = min(int(line["top"]) for line in block)  # type: ignore[index]
            block_bottom = max(int(line["bottom"]) for line in block)  # type: ignore[index]
            block_left = min(int(line["left"]) for line in block)  # type: ignore[index]
            block_right = max(int(line["right"]) for line in block)  # type: ignore[index]

            l1_id = next_id
            next_id += 1
            items.append(AnnotationItem(id=l1_id, level="L1", parent_id=None, bbox=[block_left, block_top, max(1, block_right - block_left), max(1, block_bottom - block_top)]))
            for line in block:
                l2_id = next_id
                next_id += 1
                items.append(AnnotationItem(
                    id=l2_id,
                    level="L2",
                    parent_id=l1_id,
                    bbox=[int(line["left"]), int(line["top"]), max(1, int(line["right"]) - int(line["left"])), max(1, int(line["bottom"]) - int(line["top"]))],
                ))
                segments = line["segments"]  # type: ignore[index]
                for seg_left, seg_right in segments:
                    l3_id = next_id
                    next_id += 1
                    items.append(AnnotationItem(
                        id=l3_id,
                        level="L3",
                        parent_id=l2_id,
                        bbox=[int(seg_left), int(line["top"]), max(1, int(seg_right) - int(seg_left)), max(1, int(line["bottom"]) - int(line["top"]))],
                    ))
        return items

    def _ensure_annotation_view(self) -> None:
        if self.current_original_qimage:
            self.annotation_canvas.set_image(self.current_original_qimage)
        self._redraw_annotations()
        self.center_tabs.setCurrentIndex(1)
        self.annotation_canvas.viewport().update()

    def _redraw_annotations(self) -> None:
        self.annotation_canvas.clear_annotations()
        self.annotation_rects.clear()
        for item in self.annotation_items:
            rect = QtCore.QRectF(item.bbox[0], item.bbox[1], item.bbox[2], item.bbox[3])
            rect_item = self.annotation_canvas.add_rect(rect, self._item_color(item), item.id)
            self.annotation_rects[item.id] = rect_item

    def _create_annotation_item(self, level: str, left: int, top: int, right: int, bottom: int, parent_id: int | None) -> int:
        annotation_id = self.annotation_next_id
        self.annotation_next_id += 1
        bbox = [left, top, max(1, right - left), max(1, bottom - top)]
        item = AnnotationItem(id=annotation_id, level=level, parent_id=parent_id, bbox=bbox)
        self.annotation_items.append(item)
        rect = QtCore.QRectF(left, top, bbox[2], bbox[3])
        rect_item = self.annotation_canvas.add_rect(rect, self._item_color(item), annotation_id)
        self.annotation_rects[annotation_id] = rect_item
        return annotation_id

    def _otsu_threshold(self, gray: Image.Image) -> int:
        hist = gray.histogram()
        total = sum(hist)
        sum_total = sum(i * hist[i] for i in range(256))
        sum_b = 0
        w_b = 0
        max_var = 0.0
        threshold = 128
        for i in range(256):
            w_b += hist[i]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += i * hist[i]
            m_b = sum_b / w_b
            m_f = (sum_total - sum_b) / w_f
            var_between = w_b * w_f * (m_b - m_f) ** 2
            if var_between > max_var:
                max_var = var_between
                threshold = i
        return threshold

    def _find_runs(self, values: List[int], min_value: int, min_len: int, gap_tol: int) -> List[tuple[int, int]]:
        segments: List[tuple[int, int]] = []
        start = None
        last_above = None
        gap = 0
        for idx, value in enumerate(values):
            if value >= min_value:
                if start is None:
                    start = idx
                last_above = idx
                gap = 0
            else:
                if start is not None:
                    gap += 1
                    if gap > gap_tol:
                        end = last_above if last_above is not None else idx
                        if end - start + 1 >= min_len:
                            segments.append((start, end))
                        start = None
                        last_above = None
                        gap = 0
        if start is not None:
            end = last_above if last_above is not None else start
            if end - start + 1 >= min_len:
                segments.append((start, end))
        return segments

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_preview()

    def refresh_steps_list(self) -> None:
        self.steps_list.clear()
        for step in self.steps:
            label = self._step_label(step.step_type)
            item = QtWidgets.QListWidgetItem(label)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if step.enabled else QtCore.Qt.CheckState.Unchecked)
            self.steps_list.addItem(item)
        if self.steps:
            self.steps_list.setCurrentRow(0)

    def add_step(self) -> None:
        step_type = self.step_combo.currentData()
        if not step_type:
            return
        self.steps.append(default_step(step_type))
        self.refresh_steps_list()
        self.preview_dirty = True
        self.update_preview()

    def remove_step(self) -> None:
        row = self.steps_list.currentRow()
        if row < 0:
            return
        self.steps.pop(row)
        self.refresh_steps_list()
        self.preview_dirty = True
        self.update_preview()

    def move_step_up(self) -> None:
        row = self.steps_list.currentRow()
        if row <= 0:
            return
        self.steps[row - 1], self.steps[row] = self.steps[row], self.steps[row - 1]
        self.refresh_steps_list()
        self.steps_list.setCurrentRow(row - 1)
        self.preview_dirty = True
        self.update_preview()

    def move_step_down(self) -> None:
        row = self.steps_list.currentRow()
        if row < 0 or row >= len(self.steps) - 1:
            return
        self.steps[row + 1], self.steps[row] = self.steps[row], self.steps[row + 1]
        self.refresh_steps_list()
        self.steps_list.setCurrentRow(row + 1)
        self.preview_dirty = True
        self.update_preview()

    def on_step_selected(self, current: QtWidgets.QListWidgetItem | None) -> None:
        self._render_params()
        self.preview_dirty = True
        self.update_preview()

    def on_step_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self.steps_list.row(item)
        if 0 <= row < len(self.steps):
            self.steps[row].enabled = item.checkState() == QtCore.Qt.CheckState.Checked
            self.preview_dirty = True
            self.update_preview()

    def _render_params(self) -> None:
        while self.params_form.rowCount():
            self.params_form.removeRow(0)
        row = self.steps_list.currentRow()
        if row < 0 or row >= len(self.steps):
            return
        step = self.steps[row]
        params = step.params
        for key, value in params.items():
            editor = self._create_param_editor(key, value, step)
            label = QtWidgets.QLabel(key)
            self.params_form.addRow(label, editor)

    def _create_param_editor(self, key: str, value: Any, step: Step) -> QtWidgets.QWidget:
        if isinstance(value, bool):
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(value)
            checkbox.stateChanged.connect(lambda state: self._update_param(step, key, bool(state)))
            return checkbox
        if isinstance(value, int):
            spin = QtWidgets.QSpinBox()
            spin.setRange(-10000, 10000)
            spin.setValue(value)
            spin.valueChanged.connect(lambda v: self._update_param(step, key, int(v)))
            return spin
        if isinstance(value, float):
            dspin = QtWidgets.QDoubleSpinBox()
            dspin.setDecimals(2)
            dspin.setRange(-10000.0, 10000.0)
            dspin.setSingleStep(0.1)
            dspin.setValue(value)
            dspin.valueChanged.connect(lambda v: self._update_param(step, key, float(v)))
            return dspin
        line = QtWidgets.QLineEdit(str(value))
        line.textChanged.connect(lambda v: self._update_param(step, key, v))
        return line

    def _update_param(self, step: Step, key: str, value: Any) -> None:
        step.params[key] = value
        self.preview_dirty = True
        self.update_preview()

    def import_images(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            tr("dialog.select_images_title"),
            str(self.root),
            tr("dialog.select_images_filter")
        )
        if not files:
            return
        raw_dir = self.root / "images_raw"
        for file_path in files:
            src = Path(file_path)
            dest = self._unique_path(raw_dir / src.name)
            shutil.copy2(src, dest)
        self.refresh_images()

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while True:
            candidate = path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def save_current_processed(self) -> None:
        if not self.current_image or not self.current_image_path:
            return
        processed = apply_pipeline(self.current_image, self.steps)
        out_path = self.root / "images_processed" / self.current_image_path.name
        processed.save(out_path)
        QtWidgets.QMessageBox.information(
            self,
            tr("message.done_title"),
            tr("message.saved_processed").format(name=out_path.name),
        )

    def save_all_processed(self) -> None:
        raw_images = list_raw_images(self.root)
        if not raw_images:
            return
        for path in raw_images:
            try:
                img = Image.open(path)
                processed = apply_pipeline(img, self.steps)
                out_path = self.root / "images_processed" / path.name
                processed.save(out_path)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("message.error_title"),
                    tr("message.process_error").format(name=path.name, exc=exc),
                )
                return
        QtWidgets.QMessageBox.information(self, tr("message.done_title"), tr("message.all_processed"))

    def save_pipeline(self) -> None:
        save_pipeline(self.root, self.steps)
        QtWidgets.QMessageBox.information(self, tr("message.done_title"), tr("message.pipeline_saved"))

    def load_pipeline(self) -> None:
        self.steps = load_pipeline(self.root)
        self.refresh_steps_list()
        self.preview_dirty = True
        self.update_preview()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Backalor desktop annotation workspace")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument('--server',help='Remote Backalor API origin (HTTPS)')
    parser.add_argument('--local-backend',action='store_true',help='Explicit development-only local API/SQLite mode')
    args = parser.parse_args()
    root = args.project.resolve()
    from .diagnostics import install_diagnostics
    install_diagnostics(root)
    app = QtWidgets.QApplication(sys.argv)
    from .theme import apply_theme
    apply_theme(app)
    app.setOrganizationName('Backalor');app.setApplicationName('Backalor')
    app.setQuitOnLastWindowClosed(False)
    from .portal import PortalWindow
    from .backend_runtime import BackendRuntime
    window = PortalWindow(initial_project=root,runtime=BackendRuntime(base_url=args.server,allow_local=args.local_backend))
    app.aboutToQuit.connect(window.runtime.close)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
