"""Desktop workflows corresponding to the reference application's annotation tools."""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from .storage import atomic_write
from PyQt6 import QtCore, QtGui, QtWidgets
from PIL import Image
from .main import MainWindow
from .canvas import EditorCanvas
from .annotations import AnnotationFile, AnnotationItem, annotation_path, load_annotations, save_annotations, UnsupportedAnnotationVersion
from .storage import file_revision, SaveConflict
from .recovery import save_draft, read_draft, clear_draft
from .datasets import export_bundle, import_bundle, export_coco, validate_annotations
from .jobs import Task, recognize_text
from .project import ensure_project_structure, list_raw_images, load_pipeline
from .segmentation import segment_image
from .yolo_export import export_yolo_dataset, export_all_levels, validate_cascade_dataset
from .yolo_infer import cascade_detect
from .i18n import tr
from .preview import ImageView

TEXT = {
 'project': ('Проєкт', 'Projekt'), 'open': ('Відкрити проєкт…', 'Otvoriť projekt…'),
 'new': ('Новий проєкт…', 'Nový projekt…'), 'metadata': ('Відомості про проєкт…', 'Údaje projektu…'),
 'export_bundle': ('Експорт проєкту ZIP…', 'Export projektu ZIP…'),
 'import_bundle': ('Імпорт проєкту ZIP…', 'Import projektu ZIP…'),
 'export_coco': ('Експорт COCO…', 'Export COCO…'), 'edit': ('Редагування', 'Úpravy'),
 'undo': ('Скасувати', 'Späť'), 'redo': ('Повторити', 'Znova'),
 'draw': ('Малювати рамки', 'Kresliť rámčeky'), 'fit': ('Вмістити', 'Prispôsobiť'),
 'symbols': ('Символи', 'Symboly'), 'models': ('Моделі й навчання', 'Modely a tréning'),
 'properties': ('Властивості анотації', 'Vlastnosti anotácie'),
 'search_images': ('Пошук зображень…', 'Hľadať obrázky…'),
 'search_symbols': ('Пошук транскрипції, коду, типу…', 'Hľadať prepis, kód, typ…'),
 'select_annotation': ('Вибери рамку або елемент зі списку.', 'Vyber rámček alebo položku zo zoznamu.'),
 'transcription': ('Транскрипція', 'Prepis'), 'code': ('Код символу', 'Kód symbolu'),
 'kind': ('Тип', 'Typ'), 'notes': ('Примітки', 'Poznámky'), 'parent': ('Батьківська анотація', 'Nadradená anotácia'),
 'apply': ('Застосувати', 'Použiť'), 'refresh_symbols': ('Оновити символи', 'Obnoviť symboly'),
 'image': ('Зображення', 'Obrázok'), 'thumbnail': ('Фрагмент', 'Výrez'),
 'validate': ('Перевірити анотації', 'Skontrolovať anotácie'),
 'title': ('Назва', 'Názov'), 'description': ('Опис', 'Popis'),
 'source': ('Архів / джерело', 'Archív / zdroj'), 'save': ('Зберегти', 'Uložiť'),
 'train': ('Навчати', 'Trénovať'), 'stop': ('Зупинити', 'Zastaviť'),
 'evaluate': ('Оцінити test', 'Vyhodnotiť test'), 'weights': ('Ваги YOLO', 'Váhy YOLO'),
 'confidence': ('Поріг впевненості', 'Prah istoty'), 'epochs': ('Епохи', 'Epochy'),
 'imgsz': ('Розмір входу', 'Veľkosť vstupu'), 'batch': ('Розмір пакета', 'Veľkosť dávky'),
 'choose': ('Обрати…', 'Vybrať…'), 'busy': ('Виконується задача…', 'Prebieha úloha…'),
 'ready': ('Готово', 'Pripravené'), 'no_symbols': ('Символів немає. Створи анотації L3.', 'Žiadne symboly. Vytvor anotácie L3.'),
 'no_results': ('Нічого не знайдено.', 'Žiadne výsledky.'),
 'geometry_error': ('Рамка має бути всередині зображення й батьківської рамки; дочірні рамки мають залишатися всередині.', 'Rámček musí byť v obrázku a rodičovi; podradené rámčeky musia zostať vnútri.'),
 'valid': ('Проблем не знайдено.', 'Nenašli sa problémy.'),
 'legacy': ('Знайдені проблеми збережених анотацій. Дані не змінено.', 'Nájdené problémy uložených anotácií. Údaje neboli zmenené.'),
 'instructions': ('Колесо: масштаб. Вимкни «Малювати рамки», щоб пересувати рамки або змінювати розмір за нижній правий кут.', 'Koliesko: zoom. Vypni „Kresliť rámčeky“ pre posun rámčekov alebo zmenu veľkosti pravým dolným rohom.'),
 'delete_image': ('Видалити зображення…', 'Odstrániť obrázok…'),
 'delete_confirm': ('Зображення й анотації буде перенесено в кошик проєкту. Продовжити?', 'Obrázok a anotácie sa presunú do koša projektu. Pokračovať?'),
 'ocr': ('Розпізнати текст фрагмента', 'Rozpoznať text výrezu'),
 'ocr_model': ('Локальна модель TrOCR', 'Lokálny model TrOCR'),
 'model_help': ('Для навчання потрібен Ultralytics. Обери локальні ваги. Експорт YOLO створює окремі train/val/test; зображення одного документа варто тримати в одному наборі.', 'Tréning vyžaduje Ultralytics. Vyber lokálne váhy. Export YOLO vytvára oddelené train/val/test; strany jedného dokumentu majú zostať v jednej množine.'),
 'close_task': ('Дочекайся завершення задачі або зупини навчання перед закриттям.', 'Počkaj na dokončenie úlohy alebo zastav tréning pred zatvorením.'),
 'plain': ('Відкритий текст', 'Otvorený text'), 'cipher': ('Шифротекст', 'Šifrový text'),
 'symbol': ('Символ', 'Symbol'), 'unknown': ('Не визначено', 'Neurčené'),
 'empty_project': ('Імпортуй скани, щоб почати роботу.', 'Začni importovaním skenov.'),
 'read_error': ('Не вдалося прочитати файл', 'Nepodarilo sa načítať súbor'),
 'document_group': ('Група документа…', 'Skupina dokumentu…'),
 'hierarchy': ('Ієрархія', 'Hierarchia'), 'details': ('Властивості', 'Vlastnosti'),
 'comparison': ('Порівняння', 'Porovnanie'), 'result': ('Результат', 'Výsledok'),
 'linked': ('Синхронний перегляд', 'Prepojený náhľad'),
 'previous': ('Попередній скан', 'Predchádzajúci sken'), 'next': ('Наступний скан', 'Nasledujúci sken'),
 'edit_mode': ('Вибір і редагування', 'Výber a úpravy'), 'draw_mode': ('Малювання', 'Kreslenie'),
 'pan_hint': ('Колесо — масштаб · перетягування — переміщення', 'Koliesko — zoom · ťahanie — posun'),
 'draw_hint': ('Обери L1, L2 чи L3 і намалюй рамку.', 'Vyber L1, L2 alebo L3 a nakresli rámček.'),
 'edit_hint': ('Вибери рамку. Перетягни її або будь-який кут.', 'Vyber rámček. Potiahni ho alebo ľubovoľný roh.'),
 'dimensions': ('Розміри', 'Rozmery'), 'saved': ('Збережено', 'Uložené'),
 'pending': ('Зміни у властивостях', 'Zmenené vlastnosti'),
 'no_params': ('Цей крок не має параметрів.', 'Tento krok nemá parametre.'),
 'discard_properties': ('Відкинути зміни', 'Zahodiť zmeny'),
 'automation': ('Автоанотація', 'Auto-anotácia'), 'exports': ('Експорт', 'Export'),
 'autosaved': ('Автозбережено', 'Automaticky uložené'), 'draft_saved': ('Чернетку збережено', 'Koncept uložený'),
 'save_failed': ('Не вдалося зберегти. Чернетка залишається у вікні.', 'Uloženie zlyhalo. Koncept zostáva v okne.'),
 'recovery_title': ('Відновлення анотацій', 'Obnovenie anotácií'),
 'recovery_prompt': ('Знайдено чернетку незбережених змін для {image}. Відновити її? Вибір «Ні» залишить поточний збережений файл.', 'Našiel sa koncept neuložených zmien pre {image}. Obnoviť ho? Voľba „Nie“ ponechá aktuálny uložený súbor.'),
 'backup_prompt': ('Основний файл {image} пошкоджено. Відновити попередню резервну копію?', 'Hlavný súbor {image} je poškodený. Obnoviť predchádzajúcu zálohu?'),
 'conflict': ('Файл змінено в іншому вікні. Збереження зупинено; чернетку збережено для відновлення.', 'Súbor bol zmenený v inom okne. Ukladanie sa zastavilo; koncept je uložený na obnovenie.'),
 'draft_unreadable': ('Чернетка пошкоджена. Збережені анотації завантажено; файл чернетки залишено для перевірки.', 'Koncept je poškodený. Uložené anotácie boli načítané; súbor konceptu zostal na kontrolu.'),
 'reload': ('Перезавантажити анотації з диска', 'Znova načítať anotácie z disku'),
 'reload_prompt': ('Завантажити збережену версію? Поточні незбережені зміни залишаться в чернетці відновлення.', 'Načítať uloženú verziu? Aktuálne neuložené zmeny zostanú v koncepte na obnovenie.'),
}


class WorkspaceWindow(MainWindow):
    closed=QtCore.pyqtSignal()

    def __init__(self, root, api_client=None):
        self._undo = []
        self._redo = []
        self._history_current = None
        self._active_annotation = None
        self._task = None
        self._task_result = None
        self._task_error = None
        self._process = None
        self._loading_symbols = False
        self._selecting_annotation = False
        self._pending_selection = None
        self._disk_revision = None
        self._recovered_pending = None
        self._last_autosave_error = None
        super().__init__(root)
        self._extend_ui()
        self.selection_timer = QtCore.QTimer(self)
        self.selection_timer.setSingleShot(True)
        self.selection_timer.timeout.connect(self._apply_queued_selection)
        self._reset_history()
        self._translate_extensions()
        self._load_model_settings()
        from .api_client import ApiClient
        settings=QtCore.QSettings('Backalor','Desktop')
        try:self.api_client=api_client or ApiClient(settings.value('backend_url','http://127.0.0.1:8000'))
        except ValueError:self.api_client=ApiClient()
        self.account_action=QtGui.QAction('Обліковий запис і сервер' if self.language=='uk' else 'Účet a server',self)
        self.account_action.triggered.connect(lambda:self._guard(self.open_account))
        self.project_menu.addSeparator()
        self.project_menu.addAction(self.account_action)
        self.account_button=QtWidgets.QToolButton(self)
        self.account_button.setDefaultAction(self.account_action)
        self.account_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.statusBar().addPermanentWidget(self.account_button)
        self._render_params()
        for widget in (self.btn_import,self.apply_properties_button,self.train_button):
            widget.setProperty('primary',True)
            widget.style().unpolish(widget);widget.style().polish(widget)
        self.setMinimumSize(960, 680)
        self.statusBar().showMessage(str(self.root))
        self.resize(1440, 920)
        self.autosave_status = QtWidgets.QLabel(self.text('saved'))
        self.autosave_status.setObjectName('mutedLabel')
        self.autosave_status.setWordWrap(True)
        self.autosave_status.setMaximumWidth(360)
        self.statusBar().addPermanentWidget(self.autosave_status)
        self.journal_timer = QtCore.QTimer(self)
        self.journal_timer.setSingleShot(True)
        self.journal_timer.setInterval(1000)
        self.journal_timer.timeout.connect(self._checkpoint_safely)
        self.autosave_timer = QtCore.QTimer(self)
        self.autosave_timer.setInterval(10000)
        self.autosave_timer.timeout.connect(self._autosave_tick)
        self.autosave_timer.start()
        if self.image_list.count():
            self.image_list.setCurrentRow(0)
        from .workflow_ui import WorkflowShell
        self.workflow=WorkflowShell(self)

    def text(self, key):
        return TEXT[key][0 if self.language == 'uk' else 1]

    def open_account(self):
        if self._task is not None or self._process is not None:return
        from .account import AccountDialog
        dialog=AccountDialog(self)
        dialog.exec()

    def _extend_ui(self):
        old = self.annotation_canvas
        layout = old.parentWidget().layout()
        canvas = EditorCanvas()
        canvas.on_rect_created = self.on_rect_created
        canvas.enable_drawing(True)
        canvas.selected.connect(self._select_from_canvas)
        canvas.boxEdited.connect(self.edit_box)
        layout.replaceWidget(old, canvas)
        old.deleteLater()
        self.annotation_canvas = canvas
        if self.current_original_qimage:
            canvas.set_image(self.current_original_qimage)
            self._redraw_annotations()
        # The inspector remains scrollable on small laptop displays.
        side = self.level_group.parentWidget()
        side_layout = side.layout()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        layout.removeWidget(side)
        scroll.setWidget(side)
        scroll.setMinimumWidth(255)
        scroll.setMaximumWidth(345)
        layout.addWidget(scroll)
        for widget in (self.list_l1, self.list_l2, self.list_l3):
            widget.setMinimumHeight(70)
            widget.setMaximumHeight(150)
        self.properties = QtWidgets.QGroupBox()
        form = QtWidgets.QFormLayout(self.properties)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.property_status = QtWidgets.QLabel()
        self.property_status.setWordWrap(True)
        form.addRow(self.property_status)
        self.fields = {}
        self.field_labels = {}
        for key in ('transcription', 'code', 'notes', 'caption'):
            editor = QtWidgets.QLineEdit()
            label = QtWidgets.QLabel()
            label.setBuddy(editor)
            self.fields[key] = editor
            self.field_labels[key] = label
            form.addRow(label, editor)
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_label = QtWidgets.QLabel()
        form.addRow(self.kind_label, self.kind_combo)
        # Legacy kind mixed the semantic role with the visual element type.
        self.kind_label.hide(); self.kind_combo.hide()
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.setMinimumContentsLength(15)
        self.role_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.role_label = QtWidgets.QLabel()
        form.addRow(self.role_label, self.role_combo)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setMinimumContentsLength(15)
        self.type_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.type_label = QtWidgets.QLabel()
        form.addRow(self.type_label, self.type_combo)
        self.reference_combo=QtWidgets.QComboBox()
        self.reference_combo.setMinimumContentsLength(15)
        self.reference_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.reference_label=QtWidgets.QLabel()
        form.addRow(self.reference_label,self.reference_combo)
        self.parent_combo = QtWidgets.QComboBox()
        self.parent_label = QtWidgets.QLabel()
        form.addRow(self.parent_label, self.parent_combo)
        self.coords = []
        for key in ('x', 'y', 'w', 'h'):
            spin = QtWidgets.QSpinBox()
            spin.setRange(0 if key in ('x', 'y') else 1, 1000000)
            self.coords.append(spin)
            form.addRow(key, spin)
        self.apply_properties_button = QtWidgets.QPushButton()
        self.apply_properties_button.clicked.connect(self.apply_properties)
        form.addRow(self.apply_properties_button)
        self.discard_properties_button = QtWidgets.QPushButton(self.text('discard_properties'))
        self.discard_properties_button.clicked.connect(self.discard_properties)
        self.discard_properties_button.setEnabled(False)
        form.addRow(self.discard_properties_button)
        self.ocr_button = QtWidgets.QPushButton()
        self.ocr_button.clicked.connect(self.run_ocr)
        form.addRow(self.ocr_button)
        # Keep hierarchy and details independently reachable without a long scroll.
        scroll.takeWidget()
        hierarchy_scroll = QtWidgets.QScrollArea()
        hierarchy_scroll.setWidgetResizable(True)
        hierarchy_scroll.setWidget(side)
        properties_scroll = QtWidgets.QScrollArea()
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setWidget(self.properties)
        self.inspector_tabs = QtWidgets.QTabWidget()
        self.inspector_tabs.addTab(hierarchy_scroll, self.text('hierarchy'))
        self.inspector_tabs.addTab(properties_scroll, self.text('details'))
        scroll.setWidget(self.inspector_tabs)
        scroll.setMinimumWidth(280)
        scroll.setMaximumWidth(330)
        self.properties.setFlat(True)
        self.properties.setTitle('')
        # Keep infrequent batch/export actions available outside the scrolling lists.
        sidebar_panel=QtWidgets.QWidget()
        sidebar_layout=QtWidgets.QVBoxLayout(sidebar_panel);sidebar_layout.setContentsMargins(0,0,0,0)
        layout.removeWidget(scroll);sidebar_layout.addWidget(scroll,1);layout.addWidget(sidebar_panel)
        action_row=QtWidgets.QHBoxLayout()
        self.automation_menu_button=QtWidgets.QToolButton()
        self.export_menu_button=QtWidgets.QToolButton()
        for button,keys in [(self.automation_menu_button,('btn_auto_annotations','btn_auto_annotations_batch','btn_yolo_auto')),
                            (self.export_menu_button,('btn_export_yolo',))]:
            menu=QtWidgets.QMenu(button)
            for key in keys:
                original=getattr(self,key)
                action=menu.addAction(original.text());action.triggered.connect(original.click)
                original.hide()
            button.setMenu(menu);button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
            action_row.addWidget(button)
        self.export_menu_button.menu().addAction(self.text('export_coco'),lambda:self._guard(self.export_coco_dialog))
        sidebar_layout.addLayout(action_row)
        self.properties.setEnabled(False)
        self.image_search = QtWidgets.QLineEdit()
        self.image_search.textChanged.connect(self.filter_images)
        self.image_list.parentWidget().layout().insertWidget(1, self.image_search)
        self.image_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.image_list.customContextMenuRequested.connect(self._image_menu)
        self._build_extension_actions()
        toolbar = self.addToolBar('Annotation')
        self.annotation_toolbar = toolbar
        toolbar.setObjectName('annotationToolbar')
        toolbar.setMovable(False)
        for action in (self.undo_action, self.redo_action, self.save_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem(self.text('draw_mode'), True)
        self.mode_combo.addItem(self.text('edit_mode'), False)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.draw_action.toggled.connect(lambda checked:self.mode_combo.setCurrentIndex(0 if checked else 1))
        toolbar.addWidget(self.mode_combo)
        toolbar.addAction(self.fit_action)
        self.instructions = QtWidgets.QLabel()
        self.instructions.setWordWrap(True)
        self.instructions.setContentsMargins(8, 4, 8, 4)
        toolbar.addWidget(self.instructions)
        self.layer_checks = {}
        for level in ('L1', 'L2', 'L3'):
            checkbox = QtWidgets.QCheckBox(level)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._update_layer_visibility)
            toolbar.addWidget(checkbox)
            self.layer_checks[level] = checkbox
        self.pipeline_panel = self.steps_list.parentWidget()
        self.pipeline_panel.setMinimumWidth(250)
        self.pipeline_panel.setMaximumWidth(310)
        self.image_list.parentWidget().setMinimumWidth(170)
        self.image_list.parentWidget().setMaximumWidth(220)
        for label in (self.lbl_original, self.lbl_processed):
            label.setMinimumSize(160, 220)
        self._build_preview()
        self.navigation = QtWidgets.QLabel()
        self.navigation.setObjectName('mutedLabel')
        navigation_row = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QPushButton()
        self.next_button = QtWidgets.QPushButton()
        self.previous_button.clicked.connect(lambda: self.navigate_image(-1))
        self.next_button.clicked.connect(lambda: self.navigate_image(1))
        navigation_row.addWidget(self.previous_button)
        navigation_row.addWidget(self.navigation,1)
        navigation_row.addWidget(self.next_button)
        self.image_list.parentWidget().layout().insertLayout(3,navigation_row)
        self.navigation.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        for widget in (self.lbl_images_title,self.lbl_pipeline_title): widget.setObjectName('panelTitle')
        for widget in (self.btn_import,self.apply_properties_button,self.train_button if hasattr(self,'train_button') else self.btn_save_annotations): widget.setProperty('primary',True)
        for field in self.fields.values(): field.textEdited.connect(self._property_modified)
        for spin in self.coords: spin.valueChanged.connect(self._property_modified)
        self.kind_combo.currentIndexChanged.connect(self._property_modified)
        self.role_combo.currentIndexChanged.connect(self._property_modified)
        self.type_combo.currentIndexChanged.connect(self._property_modified)
        self.reference_combo.currentIndexChanged.connect(self._property_modified)
        self.parent_combo.currentIndexChanged.connect(self._property_modified)
        self._property_dirty = False
        self._build_symbols_tab()
        self._build_models_tab()
        from .digitization_ui import DigitizationPanel
        self.digitization = DigitizationPanel(self)
        self.center_tabs.addTab(self.digitization,self.digitization.t('tab'))
        self.center_tabs.currentChanged.connect(self._tab_changed)
        self._tab_changed(0)
        from .hierarchy_ui import HierarchyPanel
        self.hierarchy_panel=HierarchyPanel(self)
        for widget in (self.list_l1,self.list_l2,self.list_l3,self.lbl_l1_title,self.lbl_l2_title,self.lbl_l3_title,self.btn_delete_l1,self.btn_delete_l2,self.btn_delete_l3):widget.hide()
        side.layout().insertWidget(3,self.hierarchy_panel,1)
        self.hierarchy_panel.rebuild()

    def _build_preview(self):
        panel = self.center_tabs.widget(0)
        old_layout = panel.layout()
        for label in (self.lbl_original,self.lbl_processed):
            label.hide()
        # Remove the old fixed QLabel row and replace it with pan/zoom canvases.
        item = old_layout.takeAt(1)
        if item and item.layout():
            while item.layout().count(): item.layout().takeAt(0)
        controls = QtWidgets.QHBoxLayout()
        self.preview_mode = QtWidgets.QComboBox()
        for key in ('comparison','image','result'): self.preview_mode.addItem(self.text(key))
        self.preview_mode.currentIndexChanged.connect(self._preview_mode_changed)
        controls.addWidget(self.preview_mode)
        self.preview_link = QtWidgets.QCheckBox(self.text('linked')); self.preview_link.setChecked(True)
        controls.addWidget(self.preview_link)
        controls.addStretch()
        self.preview_zoom_out = QtWidgets.QPushButton('−'); self.preview_zoom_out.setFixedWidth(34)
        self.preview_zoom_in = QtWidgets.QPushButton('+'); self.preview_zoom_in.setFixedWidth(34)
        self.preview_fit = QtWidgets.QPushButton(self.text('fit'))
        self.preview_actual = QtWidgets.QPushButton('100%')
        for widget in (self.preview_zoom_out,self.preview_zoom_in,self.preview_fit,self.preview_actual): controls.addWidget(widget)
        old_layout.addLayout(controls)
        self.preview_splitter = QtWidgets.QSplitter()
        self.preview_frames = []
        self.preview_titles = []
        self.original_view = ImageView(); self.processed_view = ImageView()
        for view,key in ((self.original_view,'label.original'),(self.processed_view,'label.processed')):
            frame = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(frame);layout.setContentsMargins(0,5,0,0)
            title = QtWidgets.QLabel(tr(key));title.setObjectName('previewTitle')
            layout.addWidget(title);layout.addWidget(view,1)
            self.preview_splitter.addWidget(frame);self.preview_frames.append(frame);self.preview_titles.append(title)
        old_layout.addWidget(self.preview_splitter,1)
        self.preview_caption = QtWidgets.QLabel();self.preview_caption.setObjectName('mutedLabel')
        old_layout.addWidget(self.preview_caption)
        self.original_view.viewChanged.connect(lambda:self._synchronize_preview(self.original_view,self.processed_view))
        self.processed_view.viewChanged.connect(lambda:self._synchronize_preview(self.processed_view,self.original_view))
        self.preview_zoom_out.clicked.connect(lambda:self._preview_zoom(1/1.25))
        self.preview_zoom_in.clicked.connect(lambda:self._preview_zoom(1.25))
        self.preview_fit.clicked.connect(self._fit_preview)
        self.preview_actual.clicked.connect(lambda:self._active_preview().actual_size())
        self.preview_link.toggled.connect(lambda enabled: enabled and self._synchronize_preview(self._active_preview(),self.processed_view if self._active_preview() is self.original_view else self.original_view))

    def _active_preview(self):
        return self.processed_view if self.preview_mode.currentIndex()==2 else self.original_view

    def _synchronize_preview(self,source,target):
        if self.preview_link.isChecked() and not source._syncing:
            target.synchronize_from(source)

    def _preview_zoom(self,factor):
        self._active_preview().zoom(factor)

    def _fit_preview(self):
        self.original_view.fit_image();self.processed_view.fit_image()

    def _preview_mode_changed(self,index):
        self.preview_frames[0].setVisible(index!=2)
        self.preview_frames[1].setVisible(index!=1)
        self.preview_link.setVisible(index==0)
        QtCore.QTimer.singleShot(0,self._fit_preview)

    def _mode_changed(self):
        drawing = bool(self.mode_combo.currentData())
        self.draw_action.setChecked(drawing)
        self.annotation_canvas.enable_drawing(drawing)
        self.instructions.setText(self.text('draw_hint' if drawing else 'edit_hint'))

    def _property_modified(self,*args):
        if self._selecting_annotation or self._active_annotation is None: return
        self._property_dirty = True
        self.apply_properties_button.setEnabled(True)
        self.discard_properties_button.setEnabled(True)
        self.property_status.setText(self.text('pending'))
        self._schedule_checkpoint()

    def discard_properties(self):
        annotation_id=self._active_annotation
        self._property_dirty=False
        self.select_annotation(annotation_id)

    def _action(self, key, callback, shortcut=None, menu=None):
        action = QtGui.QAction(self.text(key), self)
        action.triggered.connect(lambda checked=False: self._guard(callback))
        if shortcut:
            action.setShortcut(shortcut)
        if menu:
            menu.addAction(action)
        return action

    def _build_extension_actions(self):
        self.project_menu = self.menuBar().addMenu(self.text('project'))
        self.extension_actions = {}
        for key, callback in [('open', self.open_project), ('new', self.new_project),
                              ('metadata', self.edit_project_metadata), ('export_bundle', self.export_project_bundle),
                              ('import_bundle', self.import_project_bundle), ('export_coco', self.export_coco_dialog),
                              ('reload', self.reload_saved_annotations),
                              ('validate', self.validate_project)]:
            self.extension_actions[key] = self._action(key, callback, menu=self.project_menu)
        self.edit_menu = self.menuBar().addMenu(self.text('edit'))
        self.undo_action = self._action('undo', self.undo, QtGui.QKeySequence.StandardKey.Undo, self.edit_menu)
        self.redo_action = self._action('redo', self.redo, QtGui.QKeySequence.StandardKey.Redo, self.edit_menu)
        self.draw_action = QtGui.QAction(self.text('draw'), self)
        self.draw_action.setCheckable(True)
        self.draw_action.setChecked(True)
        self.draw_action.triggered.connect(self.annotation_canvas.enable_drawing)
        self.fit_action = self._action('fit', self.annotation_canvas.fit_image, 'F', self.view_menu)
        self.fit_action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        self.annotation_canvas.addAction(self.fit_action)
        self.save_action = self._action('save', self.save_annotations_current, QtGui.QKeySequence.StandardKey.Save, self.edit_menu)
        self.delete_action = QtGui.QAction(self.text('delete_image'), self)
        self.delete_action.triggered.connect(lambda: self._guard(self.delete_image))
        self.group_action = self._action('document_group', self.set_document_group)
        self.edit_menu.addAction(self.draw_action)
        for key in ('1', '2', '3'):
            action = QtGui.QAction(self.annotation_canvas)
            action.setShortcut(key)
            action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
            action.triggered.connect(lambda checked=False, level=key: getattr(self, 'level_l'+level).setChecked(True))
            self.annotation_canvas.addAction(action)
        delete_annotation_action = QtGui.QAction(self.annotation_canvas)
        delete_annotation_action.setShortcut(QtGui.QKeySequence('Delete'))
        delete_annotation_action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        delete_annotation_action.triggered.connect(lambda: self.delete_annotation(self._active_annotation) if self._active_annotation else None)
        self.annotation_canvas.addAction(delete_annotation_action)
        self._sync_history_actions()

    def _build_symbols_tab(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        row = QtWidgets.QHBoxLayout()
        self.symbol_search = QtWidgets.QLineEdit()
        self.symbol_search.textChanged.connect(self.filter_symbols)
        self.refresh_symbols_button = QtWidgets.QPushButton()
        self.refresh_symbols_button.clicked.connect(self.refresh_symbols)
        row.addWidget(self.symbol_search, 1)
        row.addWidget(self.refresh_symbols_button)
        layout.addLayout(row)
        self.symbol_status = QtWidgets.QLabel()
        layout.addWidget(self.symbol_status)
        self.symbol_table = QtWidgets.QTableWidget(0, 7)
        self.symbol_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.symbol_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.symbol_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.symbol_table.setIconSize(QtCore.QSize(64, 48))
        self.symbol_table.verticalHeader().setDefaultSectionSize(55)
        self.symbol_table.verticalHeader().hide()
        self.symbol_table.horizontalHeader().setStretchLastSection(True)
        self.symbol_table.cellDoubleClicked.connect(self.open_symbol)
        self.symbol_table.itemActivated.connect(lambda item: self.open_symbol(item.row(), item.column()))
        layout.addWidget(self.symbol_table, 1)
        from .catalog_ui import CatalogPanel
        self.catalog_panel=CatalogPanel(self)
        self.symbol_tabs=QtWidgets.QTabWidget()
        self.symbol_tabs.addTab(panel,self.catalog_panel.t('fragments'))
        self.symbol_tabs.addTab(self.catalog_panel,self.catalog_panel.t('catalog'))
        self.symbol_tabs.setCurrentIndex(1)
        self.symbol_tabs.currentChanged.connect(lambda index:self._guard(self.catalog_panel.refresh if index==1 else self.refresh_symbols) if self.center_tabs.currentIndex()==2 else None)
        self.center_tabs.addTab(self.symbol_tabs, self.text('symbols'))

    def _build_models_tab(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        form = QtWidgets.QFormLayout()
        self.weight_fields = {}
        self.confidence_fields = {}
        self.weight_labels = {}
        for level in ('L1','L2','L3'):
            row = QtWidgets.QHBoxLayout()
            field = QtWidgets.QLineEdit()
            choose = QtWidgets.QPushButton('…')
            choose.setMaximumWidth(38)
            choose.clicked.connect(lambda checked=False, target=field: self._choose_weights(target))
            confidence = QtWidgets.QDoubleSpinBox()
            confidence.setRange(0.01, 1.0)
            confidence.setSingleStep(0.05)
            confidence.setValue(0.25)
            row.addWidget(field, 1); row.addWidget(choose); row.addWidget(confidence)
            label = QtWidgets.QLabel()
            form.addRow(label, row)
            self.weight_fields[level] = field
            self.confidence_fields[level] = confidence
            self.weight_labels[level] = label
        self.save_models_button = QtWidgets.QPushButton()
        self.save_models_button.clicked.connect(lambda: self._guard(self.save_model_settings))
        form.addRow(self.save_models_button)
        self.ocr_path = QtWidgets.QLineEdit()
        self.ocr_label = QtWidgets.QLabel()
        form.addRow(self.ocr_label, self.ocr_path)
        self.train_level = QtWidgets.QComboBox(); self.train_level.addItems(['L1','L2','L3'])
        form.addRow('L1 / L2 / L3', self.train_level)
        self.epochs = QtWidgets.QSpinBox(); self.epochs.setRange(1, 10000); self.epochs.setValue(50)
        self.imgsz = QtWidgets.QSpinBox(); self.imgsz.setRange(64, 4096); self.imgsz.setSingleStep(32); self.imgsz.setValue(640)
        self.batch = QtWidgets.QSpinBox(); self.batch.setRange(1, 128); self.batch.setValue(4)
        self.training_labels = {}
        for key, widget in [('epochs', self.epochs), ('imgsz', self.imgsz), ('batch', self.batch)]:
            label = QtWidgets.QLabel(); self.training_labels[key] = label; form.addRow(label, widget)
        layout.addLayout(form)
        row = QtWidgets.QHBoxLayout()
        self.train_button = QtWidgets.QPushButton()
        self.train_button.clicked.connect(lambda: self._guard(lambda: self.start_training('train')))
        self.evaluate_button = QtWidgets.QPushButton()
        self.evaluate_button.clicked.connect(lambda: self._guard(lambda: self.start_training('test')))
        self.stop_button = QtWidgets.QPushButton()
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_training)
        for widget in (self.train_button,self.evaluate_button,self.stop_button): row.addWidget(widget)
        layout.addLayout(row)
        self.model_help = QtWidgets.QLabel(); self.model_help.setWordWrap(True)
        layout.addWidget(self.model_help)
        self.job_log = QtWidgets.QPlainTextEdit(); self.job_log.setReadOnly(True)
        self.job_log.setMaximumBlockCount(2000)
        layout.addWidget(self.job_log, 1)
        self.center_tabs.addTab(panel, self.text('models'))

    def _translate_extensions(self):
        if not hasattr(self, 'project_menu'): return
        self.project_menu.setTitle(self.text('project')); self.edit_menu.setTitle(self.text('edit'))
        for key, action in self.extension_actions.items(): action.setText(self.text(key))
        for key, widget in [('undo',self.undo_action),('redo',self.redo_action),('draw',self.draw_action),
                            ('fit',self.fit_action),('save',self.save_action),('delete_image',self.delete_action),('document_group',self.group_action),
                            ('properties',self.properties),('apply',self.apply_properties_button),
                            ('refresh_symbols',self.refresh_symbols_button),('save',self.save_models_button),
                            ('train',self.train_button),('evaluate',self.evaluate_button),('stop',self.stop_button),('ocr',self.ocr_button)]:
            (widget.setTitle if isinstance(widget, QtWidgets.QGroupBox) else widget.setText)(self.text(key))
        from .hierarchy_ui import translate as hierarchy_text
        for key,label in self.field_labels.items(): label.setText(hierarchy_text(self,key) if key=='caption' else self.text(key))
        self.reference_label.setText(hierarchy_text(self,'reference'))
        if hasattr(self,'hierarchy_panel'):self.hierarchy_panel.translate()
        self.catalog_panel.translate()
        self.symbol_tabs.setTabText(0,self.catalog_panel.t('fragments'));self.symbol_tabs.setTabText(1,self.catalog_panel.t('catalog'))
        self.kind_label.setText(self.text('kind')); self.parent_label.setText(self.text('parent'))
        kind = self.kind_combo.currentData()
        self.kind_combo.clear()
        for key,value in [('unknown',''),('plain','plaintext'),('cipher','ciphertext'),('symbol','symbol')]: self.kind_combo.addItem(self.text(key), value)
        self.kind_combo.setCurrentIndex(max(0,self.kind_combo.findData(kind)))
        role=self.role_combo.currentData();element_type=self.type_combo.currentData()
        from .digitization_ui import COPY as DIGITIZATION_COPY
        translate=lambda key:DIGITIZATION_COPY[key][0 if self.language=='uk' else 1]
        self.role_label.setText(translate('role'));self.type_label.setText(translate('type'))
        self.role_combo.clear();self.type_combo.clear()
        for key,value in [('unknown',''),('plain','plaintext'),('cipher','ciphertext')]:self.role_combo.addItem(translate(key),value)
        for key,value in [('unknown',''),('readable','readable'),('cipher_symbol','cipher_symbol')]:self.type_combo.addItem(translate(key),value)
        self.role_combo.setCurrentIndex(max(0,self.role_combo.findData(role)))
        self.type_combo.setCurrentIndex(max(0,self.type_combo.findData(element_type)))
        if hasattr(self,'digitization'):
            self.digitization.translate()
            self.center_tabs.setTabText(4,self.digitization.t('tab'))
        for level,label in self.weight_labels.items(): label.setText(level+' · '+self.text('weights'))
        for field in self.confidence_fields.values(): field.setToolTip(self.text('confidence'))
        for key,label in self.training_labels.items(): label.setText(self.text(key))
        self.ocr_label.setText(self.text('ocr_model')); self.model_help.setText(self.text('model_help'))
        self.instructions.setText(self.text('instructions'))
        self.image_search.setPlaceholderText(self.text('search_images'))
        self.symbol_search.setPlaceholderText(self.text('search_symbols'))
        self.center_tabs.setTabText(2,self.text('symbols')); self.center_tabs.setTabText(3,self.text('models'))
        self.symbol_table.setHorizontalHeaderLabels([self.text('thumbnail'),self.text('image'),'ID',self.text('transcription'),self.text('code'),self.text('kind'),self.text('notes')])
        self.properties.setTitle('')
        self.discard_properties_button.setText(self.text('discard_properties'))
        self.automation_menu_button.setText(self.text('automation'));self.export_menu_button.setText(self.text('exports'))
        for action,key in zip(self.automation_menu_button.menu().actions(),('btn_auto_annotations','btn_auto_annotations_batch','btn_yolo_auto')):
            action.setText(getattr(self,key).text())
        self.export_menu_button.menu().actions()[0].setText(self.btn_export_yolo.text())
        self.export_menu_button.menu().actions()[1].setText(self.text('export_coco'))
        self.inspector_tabs.setTabText(0,self.text('hierarchy'));self.inspector_tabs.setTabText(1,self.text('details'))
        self.mode_combo.setItemText(0,self.text('draw_mode'));self.mode_combo.setItemText(1,self.text('edit_mode'))
        self.instructions.setText(self.text('draw_hint' if self.mode_combo.currentData() else 'edit_hint'))
        self.preview_mode.setItemText(0,self.text('comparison'));self.preview_mode.setItemText(1,tr('label.original'));self.preview_mode.setItemText(2,self.text('result'))
        self.preview_titles[0].setText(tr('label.original'));self.preview_titles[1].setText(tr('label.processed'))
        self.preview_link.setText(self.text('linked'));self.preview_fit.setText(self.text('fit'))
        self.previous_button.setText('‹');self.next_button.setText('›')
        self.previous_button.setToolTip(self.text('previous'));self.next_button.setToolTip(self.text('next'))
        self.property_status.setText(self.text('select_annotation') if self._active_annotation is None else f'#{self._active_annotation}')

    def apply_language(self, lang):
        if not self._flush_properties(): return
        super().apply_language(lang)
        self._translate_extensions()
        if hasattr(self,'navigation'): self._update_navigation()
        if hasattr(self,'account_action'):
            from .account import COPY
            profile=self.api_client.profile
            self.account_action.setText(COPY['account'][0 if lang=='uk' else 1]+(' · '+profile['name'] if profile else ''))
        if hasattr(self,'workflow'):self.workflow.translate()

    def _guard(self, callback):
        try: return callback()
        except Exception as exc: self._error(str(exc))

    def _error(self, message):
        QtWidgets.QMessageBox.warning(self, tr('message.error_title'), message)

    def _snapshot(self):
        return (copy.deepcopy(self.annotation_items), self.annotation_next_id)

    def _reset_history(self):
        self._pending_selection = None
        if hasattr(self,'selection_timer'):self.selection_timer.stop()
        self._undo = []; self._redo = []; self._history_current = self._snapshot()
        self._active_annotation = None
        self._property_dirty = False
        if hasattr(self, 'properties'): self.properties.setEnabled(False)
        self._sync_history_actions()

    def _record(self):
        snapshot = self._snapshot()
        if self._history_current is not None and snapshot != self._history_current:
            self._undo.append(self._history_current)
            self._undo = self._undo[-100:]
            self._redo.clear()
        self._history_current = snapshot
        self._sync_history_actions()
        self._schedule_checkpoint()
        if hasattr(self,'workflow'):self.workflow.refresh()

    def _sync_history_actions(self):
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(bool(self._undo)); self.redo_action.setEnabled(bool(self._redo))

    def _restore(self, snapshot):
        self.annotation_items, self.annotation_next_id = copy.deepcopy(snapshot)
        self.annotation_dirty = True
        self._history_current = self._snapshot()
        self._redraw_annotations(); self.refresh_annotation_lists(); self._sync_history_actions()
        self.select_annotation(self._active_annotation) if self._active_annotation else None
        self._schedule_checkpoint()
        if hasattr(self,'digitization'):self.digitization.refresh()

    def undo(self):
        if not self._flush_properties(): return
        if self._undo:
            self._redo.append(self._snapshot()); self._restore(self._undo.pop())

    def redo(self):
        if not self._flush_properties(): return
        if self._redo:
            self._undo.append(self._snapshot()); self._restore(self._redo.pop())

    def add_annotation(self, level, rect, parent_id):
        super().add_annotation(level, rect, parent_id)
        self._record(); self.select_annotation(self.annotation_items[-1].id)

    def on_rect_created(self, rect):
        if not self.current_image: return
        if not self._flush_properties(): return
        # Never replace unseen existing annotations when drawing on a saved scan.
        path = annotation_path(self.root,self.current_image_path)
        if not self.annotation_items and not self.annotation_dirty and path.exists():
            self.load_annotations_for_current();self._reset_history()
        bounds = QtCore.QRectF(0,0,*self.current_image.size)
        rect = rect.intersected(bounds)
        if min(rect.width(),rect.height()) < 5: return
        parent_level = {'L2':'L1','L3':'L2'}.get(self.annotation_level)
        parent_id = None
        if parent_level:
            candidates = [i for i in self.annotation_items if i.level == parent_level and QtCore.QRectF(*i.bbox).contains(rect)]
            if not candidates:
                self._error(self.text('geometry_error')); return
            parent_id = min(candidates,key=lambda i:i.bbox[2]*i.bbox[3]).id
        self.add_annotation(self.annotation_level,rect,parent_id)

    def delete_annotation(self, annotation_id):
        if not self._flush_properties(): return
        super().delete_annotation(annotation_id); self._record()
        if self._active_annotation == annotation_id:
            self._active_annotation = None; self.properties.setEnabled(False)

    def mark_selected_l3_label(self, label):
        super().mark_selected_l3_label(label); self._record()

    def mark_rest_l3_not_symbol(self):
        super().mark_rest_l3_not_symbol(); self._record()

    def on_image_selected(self, current):
        try:
            if not self._flush_properties():
                blocker = QtCore.QSignalBlocker(self.image_list)
                for index in range(self.image_list.count()):
                    previous = self.image_list.item(index)
                    if previous.data(QtCore.Qt.ItemDataRole.UserRole)==self.current_image_path:
                        self.image_list.setCurrentItem(previous);break
                del blocker
                return
            super().on_image_selected(current)
            if self.current_image_path:
                self._disk_revision = file_revision(annotation_path(self.root,self.current_image_path))
            self._reset_history()
            if self._recovered_pending:
                pending = self._recovered_pending
                self._recovered_pending = None
                self.select_annotation(pending['id'])
                for key in self.fields:
                    if key in pending:self.fields[key].setText(pending[key])
                for spin,value in zip(self.coords,pending.get('bbox',[])): spin.setValue(value)
                self.kind_combo.setCurrentIndex(max(0,self.kind_combo.findData(pending.get('kind',''))))
                if 'text_role' in pending:self.role_combo.setCurrentIndex(max(0,self.role_combo.findData(pending['text_role'])))
                if 'element_type' in pending:self.type_combo.setCurrentIndex(max(0,self.type_combo.findData(pending['element_type'])))
                if 'transcription_ref_id' in pending:self.reference_combo.setCurrentIndex(max(0,self.reference_combo.findData(pending['transcription_ref_id'])))
                self.parent_combo.setCurrentIndex(max(0,self.parent_combo.findData(pending.get('parent_id'))))
                self._property_modified()
                self.inspector_tabs.setCurrentIndex(1)
            if hasattr(self.annotation_canvas,'fit_image'): self.annotation_canvas.fit_image()
            if hasattr(self,'original_view'):
                self.original_view.set_image(self.current_original_qimage,reset=True)
                self.processed_view.set_image(None)
                self._update_navigation()
            if hasattr(self,'digitization'):self.digitization.refresh()
            if hasattr(self,'workflow'):self.workflow.refresh()
        except Exception as exc:
            self._error(str(exc))
            blocker = QtCore.QSignalBlocker(self.image_list)
            for index in range(self.image_list.count()):
                item=self.image_list.item(index)
                if item.data(QtCore.Qt.ItemDataRole.UserRole)==self.current_image_path:
                    self.image_list.setCurrentItem(item);break
            del blocker

    def _ask_recovery(self, message):
        return QtWidgets.QMessageBox.question(self,self.text('recovery_title'),message,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes) == QtWidgets.QMessageBox.StandardButton.Yes

    def load_annotations_for_current(self, allow_recovery=True):
        self.clear_annotation_state()
        if not self.current_image_path: return
        image=self.current_image_path
        path=annotation_path(self.root,image)
        self._disk_revision=file_revision(path)
        data=None
        unreadable=None
        if path.exists():
            try: data=load_annotations(path)
            except UnsupportedAnnotationVersion:raise
            except Exception as exc: unreadable=exc
        try:draft=read_draft(self.root,image)
        except (ValueError,TypeError,KeyError):
            draft=None
            self.statusBar().showMessage(self.text('draft_unreadable'))
        recovered=False
        if draft and allow_recovery:
            if draft['data']==data and not draft.get('pending'):
                clear_draft(self.root,image)
            elif self._ask_recovery(self.text('recovery_prompt').format(image=image.name)):
                data=draft['data'];self._recovered_pending=draft.get('pending');recovered=True
            else: clear_draft(self.root,image)
        if unreadable and not recovered:
            backup=path.with_suffix('.json.bak')
            if backup.exists() and self._ask_recovery(self.text('backup_prompt').format(image=image.name)):
                data=load_annotations(backup);recovered=True
            else: raise unreadable
        if data is None: return
        self.annotation_items=data.items;self.annotation_next_id=data.next_id
        self.annotation_dirty=recovered
        self._redraw_annotations();self.refresh_annotation_lists()
        if recovered:self._schedule_checkpoint()

    def reload_saved_annotations(self):
        if not self.current_image_path:return
        self._checkpoint()
        if not self._ask_recovery(self.text('reload_prompt')):return
        self._recovered_pending=None
        self.load_annotations_for_current(allow_recovery=False)
        self._reset_history()
        self._last_autosave_error=None
        self.autosave_status.setText(self.text('saved'))

    def _selection_from_list(self, current):
        if current is None or self._selecting_annotation:return
        # Only copy a primitive ID while the signal's item is alive. Rebuilding
        # lists inside currentItemChanged destroys the item Qt is still using.
        annotation_id = current.data(QtCore.Qt.ItemDataRole.UserRole)
        self._pending_selection = (annotation_id, self.current_image_path)
        if hasattr(self,'selection_timer'):self.selection_timer.start(0)

    def on_l1_selected(self,current):
        self._selection_from_list(current)

    def on_l2_selected(self,current):
        self._selection_from_list(current)

    def on_l3_selected(self,current):
        self._selection_from_list(current)

    def _apply_queued_selection(self):
        pending,self._pending_selection=self._pending_selection,None
        if pending and pending[1]==self.current_image_path:
            self._guard(lambda:self.select_annotation(pending[0]))

    def _select_from_canvas(self, annotation_id):
        self.select_annotation(annotation_id)
        self.inspector_tabs.setCurrentIndex(1)

    def _flush_properties(self):
        if getattr(self,'_property_dirty',False) and not self._selecting_annotation:
            return self.apply_properties() is not False
        return True

    def select_annotation(self, annotation_id):
        if self._selecting_annotation: return
        if not self._flush_properties(): return
        item = next((i for i in self.annotation_items if i.id == annotation_id), None)
        if not item or not hasattr(self,'properties'):
            if hasattr(self,'properties'): self.properties.setEnabled(False)
            return
        self._selecting_annotation = True
        self._active_annotation = item.id
        self.properties.setEnabled(True)
        self.property_status.setText(f'{item.level} · #{item.id}')
        self.fields['transcription'].setText(item.transcription)
        self.fields['code'].setText(item.symbol_code); self.fields['notes'].setText(item.notes)
        self.fields['caption'].setText(item.label if item.label not in ('symbol','not_symbol') else '')
        self.kind_combo.setCurrentIndex(max(0,self.kind_combo.findData(item.kind)))
        from .digitization import effective_type, ROLES
        role=item.text_role or (item.kind if item.kind in ROLES else '')
        self.role_combo.setCurrentIndex(max(0,self.role_combo.findData(role)))
        self.type_combo.setCurrentIndex(max(0,self.type_combo.findData(effective_type(item))))
        self.type_combo.setEnabled(item.level=='L3')
        from .digitization import effective_role
        self.reference_combo.clear();self.reference_combo.addItem('—',None)
        for target in self.annotation_items:
            if target.id!=item.id and target.level=='L3' and target.parent_id==item.parent_id and effective_type(target)=='readable' and effective_role(target,self.annotation_items)=='plaintext':
                self.reference_combo.addItem(f'#{target.id} · {target.transcription}',target.id)
        if item.transcription_ref_id is not None and self.reference_combo.findData(item.transcription_ref_id)<0:
            self.reference_combo.addItem(f'#{item.transcription_ref_id} (?)',item.transcription_ref_id)
        self.reference_combo.setCurrentIndex(max(0,self.reference_combo.findData(item.transcription_ref_id)))
        self.reference_combo.setEnabled(item.level=='L3' and effective_type(item)=='cipher_symbol')
        self.parent_combo.clear(); self.parent_combo.addItem('—', None)
        expected = {'L2':'L1','L3':'L2'}.get(item.level)
        for candidate in self.annotation_items:
            if candidate.level == expected: self.parent_combo.addItem(f'{candidate.level} #{candidate.id}',candidate.id)
        if item.parent_id is not None and self.parent_combo.findData(item.parent_id) < 0:
            self.parent_combo.addItem(f'#{item.parent_id} (legacy)', item.parent_id)
        self.parent_combo.setCurrentIndex(max(0,self.parent_combo.findData(item.parent_id)))
        self.parent_combo.setEnabled(item.level != 'L1')
        for spin,value in zip(self.coords,item.bbox): spin.setValue(int(value))
        self.annotation_canvas.highlight_item(item.id)
        self._property_dirty = False
        self.apply_properties_button.setEnabled(False)
        self.discard_properties_button.setEnabled(False)
        # Selecting on the canvas reveals the same object in the hierarchy.
        indexed = {i.id:i for i in self.annotation_items}
        ancestors = []
        node = item
        while node and node.id not in {i.id for i in ancestors}:
            ancestors.append(node);node=indexed.get(node.parent_id)
        for node in reversed(ancestors):
            widget = {'L1':self.list_l1,'L2':self.list_l2,'L3':self.list_l3}.get(node.level)
            if widget:
                blocker = QtCore.QSignalBlocker(widget)
                self._select_item_by_id(widget,node.id)
                del blocker
                self.refresh_annotation_lists()
        self._selecting_annotation = False
        if hasattr(self,'hierarchy_panel'):self.hierarchy_panel.highlight(item.id)
        if hasattr(self,'workflow'):self.workflow.sync_selection()

    def refresh_annotation_lists(self):
        super().refresh_annotation_lists()
        if hasattr(self,'hierarchy_panel'):self.hierarchy_panel.rebuild()

    def duplicate_current_annotation(self):
        if not self._flush_properties() or self._active_annotation is None or not self.current_image:return
        from .annotation_ops import duplicate_subtree
        items,selected=duplicate_subtree(self.annotation_items,self._active_annotation,self.current_image.size)
        self.annotation_items=items;self.annotation_next_id=max(item.id for item in items)+1
        self.annotation_dirty=True;self._record();self._redraw_annotations();self.refresh_annotation_lists();self.select_annotation(selected)

    def _descendant_ids(self, annotation_id):
        descendants={annotation_id}
        while True:
            expanded=descendants | {item.id for item in self.annotation_items if item.parent_id in descendants}
            if expanded==descendants:return descendants
            descendants=expanded

    def _box_changes(self, item, bbox, parent_id):
        if not self.current_image: return None
        rect = QtCore.QRectF(*bbox)
        if min(bbox[2:]) <= 0 or not QtCore.QRectF(0,0,*self.current_image.size).contains(rect): return None
        parent = next((i for i in self.annotation_items if i.id == parent_id), None)
        if item.level != 'L1':
            if parent is None or parent.level != {'L2':'L1','L3':'L2'}[item.level] or not QtCore.QRectF(*parent.bbox).contains(rect): return None
        pending = {item.id:bbox}
        dx,dy = bbox[0]-item.bbox[0],bbox[1]-item.bbox[1]
        descendants = {item.id}
        for _ in range(3):
            descendants.update(i.id for i in self.annotation_items if i.parent_id in descendants)
        for child in self.annotation_items:
            if child.id in descendants and child.id != item.id:
                x,y,w,h = child.bbox; pending[child.id] = [x+dx,y+dy,w,h]
        for child in self.annotation_items:
            if child.id in pending and child.id != item.id:
                parent_box = pending.get(child.parent_id)
                if parent_box is None or not QtCore.QRectF(*parent_box).contains(QtCore.QRectF(*pending[child.id])): return None
        return pending

    def edit_box(self, annotation_id, rect):
        item = next((i for i in self.annotation_items if i.id == annotation_id), None)
        if not item: return
        bbox = [round(rect.x()),round(rect.y()),round(rect.width()),round(rect.height())]
        changes = self._box_changes(item,bbox,item.parent_id)
        if changes is None:
            self._redraw_annotations(); self._error(self.text('geometry_error')); return
        for annotation in self.annotation_items:
            if annotation.id in changes:
                annotation.bbox = changes[annotation.id]
                annotation.reviewed = False
        self.annotation_dirty = True; self._record(); self._redraw_annotations(); self.refresh_annotation_lists(); self.select_annotation(item.id)

    def apply_properties(self):
        item = next((i for i in self.annotation_items if i.id == self._active_annotation),None)
        if item is None: return True
        before=(item.transcription,item.symbol_code,item.text_role,item.element_type,item.parent_id,list(item.bbox),item.transcription_ref_id)
        bbox = [spin.value() for spin in self.coords]
        parent_id = self.parent_combo.currentData()
        if bbox != item.bbox or parent_id != item.parent_id:
            changes = self._box_changes(item,bbox,parent_id)
            if changes is None: self._error(self.text('geometry_error')); return False
            for annotation in self.annotation_items:
                if annotation.id in changes:
                    annotation.bbox = changes[annotation.id]
                    annotation.reviewed = False
            item.parent_id = parent_id
        item.transcription = self.fields['transcription'].text().strip()
        item.symbol_code = self.fields['code'].text().strip(); item.notes = self.fields['notes'].text().strip()
        item.kind = self.kind_combo.currentData()
        caption=self.fields['caption'].text().strip()
        if caption or item.label not in ('symbol','not_symbol'):item.label=caption
        item.text_role = self.role_combo.currentData() or ''
        item.element_type = (self.type_combo.currentData() or '') if item.level=='L3' else ''
        if item.kind in ('plaintext','ciphertext','symbol'):item.kind=''
        item.transcription_ref_id=self.reference_combo.currentData() if item.element_type=='cipher_symbol' else None
        if item.element_type != before[3]:
            item.type_source='manual';item.type_confidence=None
        if (item.transcription,item.symbol_code) != before[:2]:
            item.recognition_source='manual';item.recognition_confidence=None
        if before != (item.transcription,item.symbol_code,item.text_role,item.element_type,item.parent_id,list(item.bbox),item.transcription_ref_id):
            affected=self._descendant_ids(item.id)
            for entry in self.annotation_items:
                if entry.id in affected or entry.transcription_ref_id in affected:entry.reviewed=False
        self._property_dirty = False
        self.annotation_dirty = True; self._record(); self._redraw_annotations(); self.refresh_annotation_lists(); self.select_annotation(item.id)
        return True

    def save_annotations_current(self, silent=False):
        if not self._flush_properties(): return False
        changed = self.annotation_dirty
        if changed and self.current_image_path:
            self._checkpoint()
            data=AnnotationFile(self.current_image_path.name,self.annotation_items,self.annotation_next_id)
            path=annotation_path(self.root,self.current_image_path)
            self._disk_revision=save_annotations(path,data,expected_revision=self._disk_revision)
            self.annotation_dirty=False
            clear_draft(self.root,self.current_image_path)
            self._last_autosave_error=None
            if hasattr(self,'autosave_status'):self.autosave_status.setText(self.text('saved'))
        if changed and hasattr(self,'statusBar'):
            self.statusBar().showMessage(self.text('saved')+' · '+self.current_image_path.name,4000)
        return True

    def _schedule_checkpoint(self):
        if hasattr(self,'journal_timer'):self.journal_timer.start()

    def _checkpoint(self):
        if not self.current_image_path or not (self.annotation_dirty or getattr(self,'_property_dirty',False)):return
        pending=None
        if getattr(self,'_property_dirty',False):
            pending={'id':self._active_annotation,**{key:field.text() for key,field in self.fields.items()},
                     'bbox':[spin.value() for spin in self.coords], 'kind':self.kind_combo.currentData(),
                     'parent_id':self.parent_combo.currentData(),
                     'text_role':self.role_combo.currentData(), 'element_type':self.type_combo.currentData(),
                     'transcription_ref_id':self.reference_combo.currentData()}
        save_draft(self.root,self.current_image_path,
                   AnnotationFile(self.current_image_path.name,self.annotation_items,self.annotation_next_id),
                   self._disk_revision,pending)
        if hasattr(self,'autosave_status'):self.autosave_status.setText(self.text('draft_saved'))

    def _checkpoint_safely(self):
        try:self._checkpoint()
        except Exception as exc:self._report_autosave_error(exc)

    def _report_autosave_error(self,exc):
        message=self.text('conflict') if isinstance(exc,SaveConflict) else self.text('save_failed')
        self.autosave_status.setText(message)
        # A periodic timer never opens repeated modal dialogs or discards edits.
        if self._last_autosave_error!=str(exc):
            self.statusBar().showMessage(message)
            self._last_autosave_error=str(exc)

    def _autosave_tick(self):
        if self._task is not None or self._process is not None:return
        try:
            self._checkpoint()
            # Pending fields (including temporarily invalid coordinates) stay in the recovery draft.
            if self.annotation_dirty and not getattr(self,'_property_dirty',False):
                self.save_annotations_current(silent=True)
                self.autosave_status.setText(self.text('autosaved'))
        except Exception as exc:self._report_autosave_error(exc)

    def _list_label(self,item):
        name = ' · '.join(value for value in (item.label if item.label not in ('symbol','not_symbol') else '',item.transcription or item.symbol_code) if value) or item.label
        return f'#{item.id} · {name}' if name else super()._list_label(item)

    def filter_images(self, query):
        for index in range(self.image_list.count()):
            item = self.image_list.item(index); item.setHidden(query.casefold() not in item.text().casefold())
        self._update_navigation()

    def _update_navigation(self):
        if not hasattr(self,'navigation'): return
        visible = [self.image_list.item(i) for i in range(self.image_list.count()) if not self.image_list.item(i).isHidden()]
        current = self.image_list.currentItem()
        position = visible.index(current) if current in visible else -1
        self.navigation.setText(f'{position+1} / {len(visible)}' if position>=0 else f'0 / {len(visible)}')
        self.previous_button.setEnabled(position>0);self.next_button.setEnabled(position<len(visible)-1)
        self.lbl_images_title.setText(tr('label.project_images')+f' · {self.image_list.count()}')

    def navigate_image(self,direction):
        visible = [self.image_list.item(i) for i in range(self.image_list.count()) if not self.image_list.item(i).isHidden()]
        current = self.image_list.currentItem()
        index = visible.index(current) if current in visible else -1
        target = index+direction
        if 0<=target<len(visible):self.image_list.setCurrentItem(visible[target])

    def refresh_images(self):
        current_path = self.current_image_path
        blocker = QtCore.QSignalBlocker(self.image_list)
        self.image_list.clear()
        for path in list_raw_images(self.root):
            item = QtWidgets.QListWidgetItem(path.name); item.setData(QtCore.Qt.ItemDataRole.UserRole,path)
            self.image_list.addItem(item)
            if path == current_path: self.image_list.setCurrentItem(item)
        del blocker
        if hasattr(self,'image_search'): self.filter_images(self.image_search.text())
        if hasattr(self,'statusBar') and not self.image_list.count(): self.statusBar().showMessage(self.text('empty_project'))

    def _image_menu(self, position):
        menu = QtWidgets.QMenu(self); menu.addAction(self.group_action); menu.addAction(self.delete_action); menu.exec(self.image_list.mapToGlobal(position))

    def set_document_group(self):
        if not self.current_image_path: return
        path = self.root/'project.json'
        metadata = json.loads(path.read_text()) if path.exists() else {}
        groups = metadata.setdefault('image_groups', {})
        name = self.current_image_path.name
        value, ok = QtWidgets.QInputDialog.getText(self,self.text('document_group'),self.text('document_group'),text=groups.get(name,name))
        if ok and value.strip():
            groups[name] = value.strip()
            path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')

    def delete_image(self):
        if not self.current_image_path: return
        if QtWidgets.QMessageBox.question(self,self.text('delete_image'),self.text('delete_confirm')) != QtWidgets.QMessageBox.StandardButton.Yes: return
        if self.save_annotations_current(silent=True) is False:return
        from datetime import datetime
        trash = self.root/'.trash'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        path = self.current_image_path
        if self.current_image: self.current_image.close()
        for source in (path,self.root/'images_processed'/path.name,annotation_path(self.root,path)):
            if source.exists():
                relative = source.relative_to(self.root); destination = trash/relative
                destination.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(source),str(destination))
        self.annotation_dirty = False; self.current_image_path = None; self.current_image = None
        self.on_image_selected(None); self.refresh_images()

    def _tab_changed(self, index):
        self.pipeline_panel.setVisible(index == 0)
        self.annotation_toolbar.setVisible(index == 1)
        if index == 2:self._guard(self.catalog_panel.refresh if self.symbol_tabs.currentIndex()==1 else self.refresh_symbols)
        if index == 4 and hasattr(self,'digitization'):
            self._flush_properties();self.digitization.refresh()

    def _update_layer_visibility(self):
        if not hasattr(self, 'layer_checks'): return
        for item in self.annotation_items:
            rectangle = self.annotation_rects.get(item.id)
            if rectangle:
                rectangle.setVisible(self.layer_checks.get(item.level, self.layer_checks['L1']).isChecked())

    def _redraw_annotations(self):
        super()._redraw_annotations()
        self._update_layer_visibility()

    def refresh_symbols(self):
        if self.save_annotations_current(silent=True) is False:return
        self.symbol_table.setRowCount(0)
        failures = []
        for path in list_raw_images(self.root):
            source = annotation_path(self.root,path)
            if not source.exists(): continue
            try:
                annotations = load_annotations(source)
                with Image.open(path) as image:
                    for item in annotations.items:
                        if item.level != 'L3' or item.label == 'not_symbol': continue
                        row = self.symbol_table.rowCount(); self.symbol_table.insertRow(row)
                        x,y,w,h = item.bbox
                        crop = image.crop((x,y,x+w,y+h)); crop.thumbnail((64,48))
                        cell = QtWidgets.QTableWidgetItem()
                        cell.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(self._pil_to_qimage(crop))))
                        cell.setData(QtCore.Qt.ItemDataRole.UserRole,(str(path),item.id))
                        cell.setToolTip(item.label)
                        self.symbol_table.setItem(row,0,cell)
                        from .digitization import effective_type,effective_role
                        kind=effective_type(item)
                        type_text=self.digitization.t(kind) if kind in ('readable','cipher_symbol') else self.text('unknown')
                        role=effective_role(item,annotations.items)
                        role_text=self.text('plain' if role=='plaintext' else 'cipher') if role else ''
                        for column,value in enumerate((path.name,str(item.id),item.transcription,item.symbol_code,' · '.join(filter(None,(type_text,role_text))),item.notes),1):
                            self.symbol_table.setItem(row,column,QtWidgets.QTableWidgetItem(value))
            except Exception as exc: failures.append(f'{path.name}: {exc}')
        self.symbol_table.resizeColumnsToContents()
        self.filter_symbols(self.symbol_search.text())
        if failures: self.symbol_status.setText(self.text('read_error')+': '+ '; '.join(failures))

    def filter_symbols(self, query):
        visible = 0
        for row in range(self.symbol_table.rowCount()):
            text = ' '.join(self.symbol_table.item(row,column).text() for column in range(1,7))+' '+self.symbol_table.item(row,0).toolTip()
            match = query.casefold() in text.casefold(); self.symbol_table.setRowHidden(row,not match); visible += match
        self.symbol_status.setText(f'{visible} / {self.symbol_table.rowCount()}' if visible else self.text('no_results' if query else 'no_symbols'))

    def open_symbol(self, row, column):
        path, annotation_id = self.symbol_table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        self.open_annotation_location(Path(path),annotation_id)

    def open_annotation_location(self,path,annotation_id):
        if not self._flush_properties():return
        for index in range(self.image_list.count()):
            image_item = self.image_list.item(index)
            if Path(image_item.data(QtCore.Qt.ItemDataRole.UserRole)) == path:
                if image_item.isHidden():self.image_search.clear()
                self.image_list.setCurrentItem(image_item)
                if self.current_image_path!=path:return
                self.center_tabs.setCurrentIndex(1)
                self.select_annotation(annotation_id)
                self.draw_action.setChecked(False); self.annotation_canvas.enable_drawing(False)
                self.inspector_tabs.setCurrentIndex(1)
                item = next((i for i in self.annotation_items if i.id == annotation_id),None)
                if item: self.annotation_canvas.centerOn(QtCore.QRectF(*item.bbox).center())
                break

    def switch_project(self, root):
        if self.save_annotations_current(silent=True) is False: return
        if getattr(self.digitization,'library_window',None) is not None:
            self.digitization.library_window.close()
            self.digitization.library_window=None
        ensure_project_structure(root)
        self.current_image_path = None; self.current_image = None
        self._disk_revision=None
        self.clear_annotation_state(); self._reset_history()
        self.root = root; self.steps = load_pipeline(root)
        self.current_original_qimage = None; self.current_processed_qimage = None
        self.annotation_canvas.set_image(None)
        self.refresh_images(); self.refresh_steps_list(); self.update_preview(); self._load_model_settings()
        self.statusBar().showMessage(str(root))
        if self.image_list.count(): self.image_list.setCurrentRow(0)

    def open_project(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self,self.text('open'),str(self.root))
        if directory: self.switch_project(Path(directory))

    def new_project(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self,self.text('new'),str(self.root.parent))
        if directory:
            root = Path(directory)
            if any(root.iterdir()): raise ValueError('Choose an empty directory')
            self.switch_project(root); self.edit_project_metadata()

    def edit_project_metadata(self):
        target = self.root/'project.json'; payload = json.loads(target.read_text()) if target.exists() else {}
        dialog = QtWidgets.QDialog(self); dialog.setWindowTitle(self.text('metadata')); dialog.resize(480,300)
        layout = QtWidgets.QFormLayout(dialog); fields = {}
        for key in ('title','description','source'):
            field = QtWidgets.QLineEdit(str(payload.get(key,''))); fields[key] = field; layout.addRow(self.text(key),field)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        if dialog.exec():
            payload.update({key:field.text() for key,field in fields.items()}); payload['schema_version'] = 1
            target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

    def export_project_bundle(self):
        if self.save_annotations_current(silent=True) is False: return
        target,_ = QtWidgets.QFileDialog.getSaveFileName(self,self.text('export_bundle'),str(self.root.parent/(self.root.name+'.zip')),'ZIP (*.zip)')
        if target: export_bundle(self.root,Path(target)); self.statusBar().showMessage(target)

    def import_project_bundle(self):
        source,_ = QtWidgets.QFileDialog.getOpenFileName(self,self.text('import_bundle'),str(self.root),'ZIP (*.zip)')
        if not source: return
        target = QtWidgets.QFileDialog.getExistingDirectory(self,self.text('new'),str(self.root.parent))
        if target: import_bundle(Path(source),Path(target)); self.switch_project(Path(target))

    def export_coco_dialog(self):
        if self.save_annotations_current(silent=True) is False: return
        target,_ = QtWidgets.QFileDialog.getSaveFileName(self,self.text('export_coco'),str(self.root/'results'/'annotations.coco.json'),'JSON (*.json)')
        if target: export_coco(self.root,Path(target)); self.statusBar().showMessage(target)

    def validate_project(self):
        if self.save_annotations_current(silent=True) is False: return
        issues = []
        for path in list_raw_images(self.root):
            source = annotation_path(self.root,path)
            if not source.exists(): continue
            try:
                with Image.open(path) as image: problems = validate_annotations(load_annotations(source),image.size)
                issues.extend(f'{path.name}: {problem}' for problem in problems)
            except Exception as exc: issues.append(f'{path.name}: {exc}')
        dialog = QtWidgets.QDialog(self); dialog.setWindowTitle(self.text('validate')); dialog.resize(680,440)
        layout = QtWidgets.QVBoxLayout(dialog); summary = QtWidgets.QLabel(self.text('legacy' if issues else 'valid')); summary.setWordWrap(True)
        layout.addWidget(summary); report = QtWidgets.QPlainTextEdit('\n'.join(issues)); report.setReadOnly(True); layout.addWidget(report)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.exec()

    def _load_model_settings(self):
        if not hasattr(self,'weight_fields'): return
        path = self.root/'results'/'yolo_config.json'
        try: config = json.loads(path.read_text()) if path.exists() else {}
        except Exception: config = {}
        for level,field in self.weight_fields.items():
            value = config.get(level,'')
            resolved = self.root/value if value else self.root/'yolov8n.pt'
            field.setText(str(resolved) if value or resolved.is_file() else '')
            self.confidence_fields[level].setValue(float(config.get('conf',{}).get(level,0.25)))
        self.ocr_path.setText(config.get('ocr_model',''))
        if hasattr(self,'digitization'):
            for key,field in self.digitization.model_fields.items():field.setText(config.get(key,''))
            self.digitization.threshold.setValue(float(config.get('recognition_threshold',.8)))
            self.digitization.library_threshold.setValue(float(config.get('library_threshold',.85)))
            self.digitization.library_margin.setValue(float(config.get('library_margin',.10)))
            self.digitization.message.clear();self.digitization.refresh()

    def save_model_settings(self):
        config = {level:field.text().strip() for level,field in self.weight_fields.items()}
        config['conf'] = {level:field.value() for level,field in self.confidence_fields.items()}
        config['ocr_model'] = self.ocr_path.text().strip()
        if hasattr(self,'digitization'):
            config.update({key:field.text().strip() for key,field in self.digitization.model_fields.items()})
            config['recognition_threshold']=self.digitization.threshold.value()
            config['library_threshold']=self.digitization.library_threshold.value()
            config['library_margin']=self.digitization.library_margin.value()
        atomic_write(self.root/'results'/'yolo_config.json',json.dumps(config,indent=2,ensure_ascii=False).encode('utf-8'))
        self.statusBar().showMessage(self.text('ready'))

    def _choose_weights(self, target):
        path,_ = QtWidgets.QFileDialog.getOpenFileName(self,self.text('choose'),str(self.root),'YOLO (*.pt)')
        if path: target.setText(path)

    def _set_busy(self, busy):
        # Keep the log readable and prevent edits to the snapshot being processed.
        for widget in (self.image_list.parentWidget(),self.center_tabs.widget(0),self.center_tabs.widget(1),self.center_tabs.widget(2),self.steps_list.parentWidget(),self.project_menu,self.edit_menu,self.draw_action,self.fit_action):
            widget.setEnabled(not busy)
        self.train_button.setEnabled(not busy); self.evaluate_button.setEnabled(not busy)
        self.save_models_button.setEnabled(not busy)
        if hasattr(self,'digitization'):self.digitization.setEnabled(not busy)
        self.undo_action.setEnabled(not busy and bool(self._undo))
        self.redo_action.setEnabled(not busy and bool(self._redo))
        self.save_action.setEnabled(not busy)
        self.stop_button.setEnabled(busy and self._process is not None)
        self.statusBar().showMessage(self.text('busy' if busy else 'ready'))
        if hasattr(self,'workflow'):self.workflow.refresh()

    def run_task(self, operation, completed):
        if self._task is not None or self._process is not None: return
        self._task_result = None; self._task_error = None
        self._task = Task(operation,self)
        self._task.succeeded.connect(lambda result: setattr(self,'_task_result',result))
        self._task.failed.connect(lambda error: setattr(self,'_task_error',error))
        self._task.finished.connect(lambda: self._finish_task(completed))
        self._set_busy(True); self._task.start()

    def _finish_task(self, completed):
        task = self._task; self._task = None
        self._set_busy(False)
        task.deleteLater()
        if self._task_error: self._error(self._task_error)
        else: self._guard(lambda: completed(self._task_result))

    def _replace_annotations(self, items):
        if not items:
            self.statusBar().showMessage(tr('message.yolo_no_objects')); return
        self.annotation_items = items
        self._active_annotation=None
        self._property_dirty=False
        self.properties.setEnabled(False)
        self.annotation_next_id = max(i.id for i in items)+1
        self.annotation_dirty = True; self._record()
        self._redraw_annotations(); self.refresh_annotation_lists(); self.center_tabs.setCurrentIndex(1)

    def _allow_replace(self):
        if not self._flush_properties():return False
        if not self.annotation_items: return True
        return QtWidgets.QMessageBox.question(self,tr('message.confirm_title'),tr('message.overwrite_confirm')) == QtWidgets.QMessageBox.StandardButton.Yes

    def auto_annotate(self):
        if self.current_image and self._allow_replace():
            image = self.current_image.copy(); steps = copy.deepcopy(self.steps)
            self.run_task(lambda: segment_image(image,steps),self._replace_annotations)

    def auto_annotate_batch(self):
        images = list_raw_images(self.root)
        if not images: return
        count,ok = QtWidgets.QInputDialog.getInt(self,tr('dialog.auto_batch_title'),tr('dialog.auto_batch_prompt'),len(images),1,len(images))
        if not ok: return
        if QtWidgets.QMessageBox.question(self,tr('message.confirm_title'),tr('message.overwrite_confirm')) != QtWidgets.QMessageBox.StandardButton.Yes: return
        if self.save_annotations_current(silent=True) is False:return
        steps = copy.deepcopy(self.steps); root = self.root
        def operation():
            from .annotations import save_annotations
            processed = 0
            for path in images[:count]:
                with Image.open(path) as image: items = segment_image(image,steps)
                if items:
                    save_annotations(annotation_path(root,path),AnnotationFile(path.name,items,max(i.id for i in items)+1)); processed += 1
            return processed
        def completed(processed):
            if self.current_image_path: self.load_annotations_for_current(); self._reset_history()
            self.statusBar().showMessage(tr('message.auto_batch_done').format(processed=processed,count=count))
        self.run_task(operation,completed)

    def yolo_auto_annotate(self):
        if not self.current_image or not self._allow_replace(): return
        self.save_model_settings(); image = self.current_image.copy()
        weights = [Path(self.weight_fields[level].text()) for level in ('L1','L2','L3')]
        if not all(path.is_file() for path in weights): self._error(tr('message.yolo_weights_missing')); return
        confidence = [self.confidence_fields[level].value() for level in ('L1','L2','L3')]
        def operation(): return cascade_detect(image,*weights,*confidence)
        def completed(result):
            self._log_yolo_result(*result)
            items = []
            for level,boxes in zip(('L1','L2','L3'),result):
                for box in boxes:
                    x = max(0,int(box.x1)); y = max(0,int(box.y1)); right = min(image.width,int(box.x2)); bottom = min(image.height,int(box.y2))
                    if right <= x or bottom <= y: continue
                    parent_id = None
                    if level != 'L1':
                        parent_level = {'L2':'L1','L3':'L2'}[level]
                        rect = QtCore.QRectF(x,y,right-x,bottom-y)
                        parents = [i for i in items if i.level == parent_level and QtCore.QRectF(*i.bbox).contains(rect)]
                        if not parents: continue
                        parent_id = min(parents,key=lambda i:i.bbox[2]*i.bbox[3]).id
                    items.append(AnnotationItem(len(items)+1,level,parent_id,[x,y,right-x,bottom-y],confidence=box.confidence))
            self._replace_annotations(items)
        self.run_task(operation,completed)

    def export_yolo_all(self):
        if self.save_annotations_current(silent=True) is False: return
        root = self.root
        self.run_task(lambda: export_all_levels(root),
                      lambda results: self.statusBar().showMessage(' · '.join(f'{level}: {result.images}' for level,result in results)))

    def run_ocr(self):
        if not self._flush_properties():return
        item = next((i for i in self.annotation_items if i.id == self._active_annotation),None)
        if item is None or not self.current_image: return
        from .digitization import effective_type
        if item.level!='L3' or effective_type(item)!='readable':
            self._error(self.digitization.t('review_missing'));return
        path = Path(self.ocr_path.text().strip())
        if not self.ocr_path.text().strip() or not path.is_dir():
            self.center_tabs.setCurrentIndex(3); self.ocr_path.setFocus(); return
        x,y,w,h = item.bbox; crop = self.current_image.crop((x,y,x+w,y+h)); annotation_id = item.id
        def completed(text):
            target = next((i for i in self.annotation_items if i.id == annotation_id),None)
            if target:
                target.transcription = text;target.recognition_source='trocr';target.recognition_confidence=None;target.reviewed=False
                self.annotation_dirty = True; self._record(); self.refresh_annotation_lists(); self.select_annotation(target.id); self.center_tabs.setCurrentIndex(1)
        self.run_task(lambda: recognize_text(crop,path),completed)

    def start_training(self, mode):
        if self._process is not None or self._task is not None: return
        level = self.train_level.currentText()
        weights = Path(self.weight_fields[level].text())
        if not weights.is_file(): raise ValueError(tr('message.yolo_weights_missing'))
        data = self.root/'results'/'yolo'/level/'data.yaml'
        if not data.is_file(): raise ValueError('Export YOLO before training')
        validate_cascade_dataset(self.root,level)
        if self.save_annotations_current(silent=True) is False:return
        self.save_model_settings()
        process = QtCore.QProcess(self); self._process = process
        process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        process.setProgram(sys.executable)
        process.setArguments(['-u','-m','app.train_worker','--root',str(self.root.resolve()),'--level',level,
                              '--model',str(weights.resolve()),'--epochs',str(self.epochs.value()),'--imgsz',str(self.imgsz.value()),'--batch',str(self.batch.value()),'--mode',mode])
        self._training_output = ''
        self._training_mode = mode
        self._training_level = level
        self.job_log.clear()
        process.readyReadStandardOutput.connect(self._read_training_output)
        process.finished.connect(self._training_finished)
        process.errorOccurred.connect(self._training_error)
        self._set_busy(True); process.start()

    def _read_training_output(self):
        if not self._process: return
        output = bytes(self._process.readAllStandardOutput()).decode('utf-8',errors='replace')
        output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output).replace('\r', '\n')
        self._training_output += output
        cursor = self.job_log.textCursor(); cursor.movePosition(QtGui.QTextCursor.MoveOperation.End); cursor.insertText(output); self.job_log.setTextCursor(cursor)

    def _training_error(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self._training_finished(-1,QtCore.QProcess.ExitStatus.CrashExit)

    def _training_finished(self, code, status):
        process = self._process
        if process is None: return
        self._read_training_output()
        (self.root/'results'/'training.log').write_text(self._training_output,encoding='utf-8')
        self._process = None; process.deleteLater(); self._set_busy(False)
        if code == 0 and self._training_mode == 'train':
            directory = self.root/'runs'/'detect'
            candidates = list(directory.glob(self._training_level+'*/weights/best.pt'))
            if candidates:
                weights = max(candidates, key=lambda path: path.stat().st_mtime)
                self.weight_fields[self._training_level].setText(str(weights.resolve()))
                self.save_model_settings()
        self.job_log.appendPlainText(f'Exit: {code}')
        self.statusBar().showMessage(self.text('ready') if code == 0 else tr('message.error_title'))

    def stop_training(self):
        if self._process:
            process = self._process; process.terminate()
            QtCore.QTimer.singleShot(3000,lambda: process.kill() if self._process is process else None)

    def save_current_processed(self):
        self._guard(super().save_current_processed)

    def save_all_processed(self):
        root = self.root; steps = copy.deepcopy(self.steps)
        def operation():
            from .pipeline import apply_pipeline
            paths = list_raw_images(root)
            for path in paths:
                with Image.open(path) as image:
                    output = apply_pipeline(image,steps)
                    if path.suffix.lower() in ('.jpg','.jpeg') and output.mode not in ('RGB','L'): output = output.convert('RGB')
                    output.save(root/'images_processed'/path.name)
            return len(paths)
        self.run_task(operation,lambda count:self.statusBar().showMessage(f'{self.text("ready")}: {count}'))

    def import_images(self):
        files,_ = QtWidgets.QFileDialog.getOpenFileNames(self,tr('dialog.select_images_title'),str(self.root),'Images / PDF (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.PNG *.JPG *.JPEG)')
        if not files: return
        from .importing import import_sources
        root = self.root
        self.run_task(lambda: import_sources(root,[Path(name) for name in files]),lambda count:self.refresh_images())

    def _render_preview(self):
        if not hasattr(self,'original_view'): return
        try:
            if not self.current_image:
                self.original_view.set_image(None);self.processed_view.set_image(None)
                self.preview_caption.setText(self.text('empty_project'))
                return
            from .pipeline import apply_pipeline
            if self.preview_dirty or self.current_processed_qimage is None:
                processed = apply_pipeline(self.current_image,self.steps)
                self.current_processed_qimage = self._pil_to_qimage(processed)
                self.preview_dirty = False
            if self.original_view._pixmap is None:
                self.original_view.set_image(self.current_original_qimage,reset=True)
            self.processed_view.set_image(self.current_processed_qimage)
            self.preview_caption.setText(f'{self.current_image.width} × {self.current_image.height} px  ·  {self.text("pan_hint")}')
        except Exception as exc:
            self.preview_timer.stop(); self._error(str(exc))

    def resizeEvent(self,event):
        QtWidgets.QMainWindow.resizeEvent(self,event)
        if hasattr(self,'preview_splitter'):
            orientation = QtCore.Qt.Orientation.Vertical if self.center_tabs.width()<650 else QtCore.Qt.Orientation.Horizontal
            self.preview_splitter.setOrientation(orientation)

    def _render_params(self):
        super()._render_params()
        if self.params_form.rowCount()==0:
            label=QtWidgets.QLabel(self.text('no_params'));label.setWordWrap(True);label.setObjectName('mutedLabel')
            self.params_form.addRow(label)
        translations = {
            'factor':('Інтенсивність','Intenzita'), 'radius':('Радіус','Polomer'), 'size':('Розмір фільтра','Veľkosť filtra'),
            'threshold':('Поріг','Prah'), 'gamma':('Гамма','Gama'), 'degrees':('Кут повороту','Uhol otočenia'),
            'width':('Ширина','Šírka'), 'height':('Висота','Výška'), 'keep_aspect':('Зберегти пропорції','Zachovať pomer'),
            'left':('Зліва','Zľava'), 'top':('Зверху','Zhora'), 'right':('Справа','Sprava'), 'bottom':('Знизу','Zdola'),
        }
        for row in range(self.params_form.rowCount()):
            item=self.params_form.itemAt(row,QtWidgets.QFormLayout.ItemRole.LabelRole)
            if item and item.widget().text() in translations:
                label=item.widget();label.setText(translations[label.text()][0 if self.language=='uk' else 1])

    def refresh_steps_list(self):
        previous = self.steps_list.currentItem()
        selected = previous.data(QtCore.Qt.ItemDataRole.UserRole) if previous else None
        row = self.steps_list.currentRow()
        blocker = QtCore.QSignalBlocker(self.steps_list)
        self.steps_list.clear()
        for step in self.steps:
            item=QtWidgets.QListWidgetItem(self._step_label(step.step_type))
            item.setData(QtCore.Qt.ItemDataRole.UserRole,step)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if step.enabled else QtCore.Qt.CheckState.Unchecked)
            self.steps_list.addItem(item)
        if self.steps:
            index = next((i for i,step in enumerate(self.steps) if step is selected),min(max(row,0),len(self.steps)-1))
            self.steps_list.setCurrentRow(index)
        del blocker
        self._render_params()
        self.btn_remove_step.setEnabled(bool(self.steps))
        self.btn_up.setEnabled(self.steps_list.currentRow()>0)
        self.btn_down.setEnabled(0<=self.steps_list.currentRow()<len(self.steps)-1)

    def add_step(self):
        super().add_step()
        if self.steps:self.steps_list.setCurrentRow(len(self.steps)-1)

    def on_step_selected(self,current):
        self._render_params()
        self.btn_up.setEnabled(self.steps_list.currentRow()>0)
        self.btn_down.setEnabled(0<=self.steps_list.currentRow()<len(self.steps)-1)

    def _create_param_editor(self,key,value,step):
        editor=super()._create_param_editor(key,value,step)
        if isinstance(editor,(QtWidgets.QSpinBox,QtWidgets.QDoubleSpinBox)):
            blocker=QtCore.QSignalBlocker(editor)
            limits={'factor':(0,5),'radius':(0,50),'size':(1,51),'threshold':(0,255),'gamma':(0.05,10),'degrees':(-180,180)}
            low,high=limits.get(key,(0,100000))
            editor.setRange(low,high)
            if key=='size':editor.setSingleStep(2)
            del blocker
        return editor

    def closeEvent(self,event):
        if self._task is not None or self._process is not None or any(getattr(dialog,'worker',None) is not None for dialog in self.findChildren(QtWidgets.QDialog)):
            self._error(self.text('close_task')); event.ignore(); return
        try:
            if getattr(self,'_close_to_recovery',False):self._checkpoint()
            elif self.save_annotations_current(silent=True) is False:
                event.ignore();return
        except Exception as exc:
            self._error(str(exc)); event.ignore(); return
        self.autosave_timer.stop()
        self.journal_timer.stop()
        self.selection_timer.stop()
        event.accept()
        self.closed.emit()
