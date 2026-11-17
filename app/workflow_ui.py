"""Task-focused desktop shell. Existing stage indices and editor commands stay stable.
Operate surface: page navigation and hierarchy left, scan centre, properties right.
Advanced model/geometry controls use disclosures; review follows unresolved items.
"""
from __future__ import annotations
from pathlib import Path
from PyQt6 import QtCore,QtWidgets

COPY={
 'scans':('Скани','Skeny'),'annotate':('Розмітка','Anotovanie'),'symbols':('Символи','Symboly'),
 'review':('Перевірка','Kontrola'),'models':('Моделі та навчання','Modely a tréning'),
 'more':('Інструменти','Nástroje'),'account':('Увійти','Prihlásiť sa'),
 'add':('Додати скани…','Pridať skeny…'),'pages':('Сторінки · {count}','Strany · {count}'),
 'structure':('Структура сторінки','Štruktúra strany'),
 'select':('Вибирати','Vyberať'),'draw':('Малювати','Kresliť'),
 'section':('Секція · L1','Sekcia · L1'),'pair':('Пара · L2','Pár · L2'),'element':('Елемент · L3','Prvok · L3'),
 'advanced':('Додаткові властивості','Ďalšie vlastnosti'),
 'processing':('Зберегти обробку','Uložiť spracovanie'),
 'current':('Поточну сторінку','Aktuálnu stranu'),'all':('Усі сторінки','Všetky strany'),
 'to_annotation':('Почати розмітку','Začať anotovať'),'to_review':('До перевірки','Na kontrolu'),
 'export':('Експорт','Export'),'export_key':('Ключ JSON / CSV…','Kľúč JSON / CSV…'),
 'export_project':('Увесь проєкт ZIP…','Celý projekt ZIP…'),
 'training_data':('Навчальні фрагменти…','Trénovacie výrezy…'),
 'help':('Як працювати','Ako pracovať'),
 'help_text':('Додай скани → створи секції L1, пари L2 та елементи L3 → заповни роль і тип → перевір результати → експортуй ключ.\nКолесо миші — масштаб; Alt + перетягування — рух полотна. У режимі малювання: 1 / 2 / 3 обирають рівень. F вміщує сторінку. Зміни зберігаються автоматично.','Pridaj skeny → vytvor sekcie L1, páry L2 a prvky L3 → nastav rolu a typ → skontroluj výsledky → exportuj kľúč.\nKoliesko — zoom; Alt + ťahanie — posun plátna. Pri kreslení: 1 / 2 / 3 vyberú úroveň. F prispôsobí stranu. Zmeny sa ukladajú automaticky.'),
 'hint_empty':('Додай зображення або PDF, щоб почати.','Začni pridaním obrázkov alebo PDF.'),
 'hint_scan':('Вибери сторінку. Обробка зображення — праворуч.','Vyber stranu. Spracovanie obrázka je vpravo.'),
 'hint_annotate':('Вибери рамку або ввімкни малювання.','Vyber rámček alebo zapni kreslenie.'),
 'hint_symbols':('Один код символу — усі його входження.','Jeden kód symbolu — všetky jeho výskyty.'),
 'hint_review':('Перевір пропуски й підтвердь елементи перед експортом.','Skontroluj chýbajúce údaje a potvrď prvky pred exportom.'),
 'hint_models':('Налаштування автоматичної обробки та навчання.','Nastavenia automatického spracovania a tréningu.'),
 'collapse':('Показати / сховати додаткові налаштування','Zobraziť / skryť ďalšie nastavenia'),
 'empty_title':('Додай першу сторінку','Pridaj prvú stranu'),
 'empty_detail':('Імпортуй зображення або PDF. Потім можна обробити скан і почати розмітку.','Importuj obrázky alebo PDF. Potom môžeš spracovať sken a začať anotovať.'),
 'save_key':('Зберегти ключ','Uložiť kľúč'),'duplicate':('Дублювати','Duplikovať'),'delete':('Видалити','Odstrániť'),
 'save_steps':('Зберегти','Uložiť'),'load_steps':('Завантажити','Načítať'),'preprocess':('Обробка скану','Spracovanie skenu'),
}


class Disclosure(QtWidgets.QGroupBox):
    def __init__(self,parent=None):
        super().__init__(parent);self.setCheckable(True);self.setChecked(False);self.setFlat(True)
        layout=QtWidgets.QVBoxLayout(self);layout.setContentsMargins(0,6,0,0)
        self.body=QtWidgets.QWidget();layout.addWidget(self.body);self.body.hide()
        self.toggled.connect(self.body.setVisible)


class WorkflowShell(QtCore.QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window
        self._build_header();self._simplify_files();self._simplify_annotation();self._simplify_properties()
        self.window.center_tabs.currentChanged.connect(self.on_stage)
        self.window.account_action.changed.connect(self.refresh)
        self.window.type_combo.currentIndexChanged.connect(self.sync_selection)
        self.window.draw_action.setChecked(False);self.window.mode_combo.setCurrentIndex(1)
        self.window.preview_mode.setCurrentIndex(1)
        self._build_navigation()
        self.translate();self.on_stage(window.center_tabs.currentIndex())

    def _build_navigation(self):
        from .rail_icons import icon
        w=self.window;root=w.centralWidget().layout();items=[]
        while root.count():items.append(root.takeAt(0))
        root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        shell=QtWidgets.QWidget();outer=QtWidgets.QHBoxLayout(shell);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.rail=QtWidgets.QFrame();self.rail.setObjectName('navigationRail');self.rail.setFixedWidth(184)
        navigation=QtWidgets.QVBoxLayout(self.rail);navigation.setContentsMargins(16,26,16,22);navigation.setSpacing(8)
        wordmark=QtWidgets.QLabel('BACKALOR');wordmark.setObjectName('brandWordmark');navigation.addWidget(wordmark);navigation.addSpacing(26)
        self.projects_button=QtWidgets.QToolButton();self.projects_button.setObjectName('railButton');self.projects_button.setIcon(icon('projects'));self.projects_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.projects_button.clicked.connect(lambda:w._guard(w.session_controller.show_projects) if getattr(w,'session_controller',None) else w._guard(w.open_project));navigation.addWidget(self.projects_button);navigation.addSpacing(18)
        self.nav_buttons={};self.nav_group=QtWidgets.QButtonGroup(self);self.nav_group.setExclusive(True)
        for index,key in [(0,'scans'),(1,'annotate'),(2,'symbols'),(4,'review'),(3,'models')]:
            button=QtWidgets.QToolButton();button.setObjectName('railButton');button.setIcon(icon(key));button.setIconSize(QtCore.QSize(20,20));button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon);button.setCheckable(True)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,QtWidgets.QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False,target=index:self.navigate(target));self.nav_group.addButton(button);self.nav_buttons[index]=button;navigation.addWidget(button)
        navigation.addStretch();self.account.setObjectName('railProfile');navigation.addWidget(self.account)
        outer.addWidget(self.rail)
        content=QtWidgets.QWidget();content_layout=QtWidgets.QVBoxLayout(content);content_layout.setContentsMargins(18,16,18,12);content_layout.setSpacing(10)
        for item in items:
            widget=item.widget()
            if widget:content_layout.addWidget(widget,1 if isinstance(widget,QtWidgets.QSplitter) else 0)
        outer.addWidget(content,1);root.addWidget(shell)
        w.center_tabs.tabBar().hide();w.setMinimumSize(1100,720)
        self.brand_label=w.findChild(QtWidgets.QLabel,'appBrand')
    def navigate(self,index):
        if index==3:self.open_models()
        elif self.window.center_tabs.isTabEnabled(index):self.window.center_tabs.setCurrentIndex(index)
    def t(self,key):return COPY[key][0 if self.window.language=='uk' else 1]
    def _build_header(self):
        w=self.window;root=w.centralWidget().layout()
        root.setStretchFactor(root.itemAt(0).widget(),1)
        self.header=QtWidgets.QWidget();self.header.setObjectName('appHeader');row=QtWidgets.QHBoxLayout(self.header);row.setContentsMargins(14,10,14,10)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,QtWidgets.QSizePolicy.Policy.Fixed)
        identity=QtWidgets.QVBoxLayout();title_row=QtWidgets.QHBoxLayout();brand=QtWidgets.QLabel('Backalor');brand.setObjectName('appBrand')
        title_row.addWidget(brand);self.project=QtWidgets.QLabel();self.project.setObjectName('mutedLabel');title_row.addWidget(self.project);title_row.addStretch()
        identity.addLayout(title_row);self.hint=QtWidgets.QLabel();self.hint.setObjectName('mutedLabel');self.hint.setWordWrap(True);identity.addWidget(self.hint);row.addLayout(identity,1)
        self.next_button=QtWidgets.QPushButton();self.next_button.setProperty('primary',True);self.next_button.clicked.connect(lambda:w._guard(self.advance));row.addWidget(self.next_button)
        parent_layout=w.export_menu_button.parentWidget().layout()
        if parent_layout:parent_layout.removeWidget(w.export_menu_button)
        row.addWidget(w.export_menu_button)
        self.key_action=w.export_menu_button.menu().addAction('',lambda:w._guard(w.digitization.export))
        self.project_action=w.export_menu_button.menu().addAction('',lambda:w._guard(w.export_project_bundle))
        self.dataset_action=w.export_menu_button.menu().addAction('',lambda:w._guard(w.digitization.dataset))
        self.tools=QtWidgets.QToolButton();self.tools.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QtWidgets.QMenu(self.tools);self.model_action=menu.addAction('',lambda:self.open_models())
        from .portable_ui import transfer_settings
        self.settings_actions={}
        for key,importing in [('import_settings',True),('export_settings',False)]:
            self.settings_actions[key]=menu.addAction('',lambda checked=False,value=importing:w._guard(lambda:transfer_settings(w,value)))
        menu.addSeparator()
        menu.addAction(w.extension_actions['validate']);menu.addAction(w.extension_actions['metadata'])
        self.refresh_action=menu.addAction('',w.btn_refresh.click)
        menu.addSeparator();self.help_action=menu.addAction('');self.help_action.setCheckable(True)
        self.tools.setMenu(menu);row.addWidget(self.tools)
        w.statusBar().removeWidget(w.account_button);w.account_button.hide()
        self.account=QtWidgets.QPushButton();self.account.clicked.connect(w.account_action.trigger);row.addWidget(self.account)
        root.insertWidget(0,self.header)
        self.help_text=QtWidgets.QLabel();self.help_text.setWordWrap(True);self.help_text.setObjectName('workflowHelp');self.help_text.setContentsMargins(16,8,16,8);self.help_text.hide()
        root.insertWidget(1,self.help_text);self.help_action.toggled.connect(self.help_text.setVisible)
        self.empty=QtWidgets.QWidget();empty_layout=QtWidgets.QVBoxLayout(self.empty);empty_layout.addStretch()
        self.empty_title=QtWidgets.QLabel();self.empty_title.setObjectName('emptyTitle');self.empty_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);empty_layout.addWidget(self.empty_title)
        self.empty_detail=QtWidgets.QLabel();self.empty_detail.setWordWrap(True);self.empty_detail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);empty_layout.addWidget(self.empty_detail)
        self.empty_import=QtWidgets.QPushButton();self.empty_import.setProperty('primary',True);self.empty_import.clicked.connect(w.btn_import.click)
        button_row=QtWidgets.QHBoxLayout();button_row.addStretch();button_row.addWidget(self.empty_import);button_row.addStretch();empty_layout.addLayout(button_row);empty_layout.addStretch()
        w.center_tabs.widget(0).layout().addWidget(self.empty,1)
    def _simplify_files(self):
        w=self.window;self.files=w.image_list.parentWidget();layout=self.files.layout()
        self.files.setMinimumWidth(225);self.files.setMaximumWidth(250)
        w.btn_refresh.hide();w.btn_apply_current.hide();w.btn_apply_all.hide()
        w.btn_import.setProperty('primary',False)
        w.btn_import.style().unpolish(w.btn_import);w.btn_import.style().polish(w.btn_import)
        self.structure_label=QtWidgets.QLabel();self.structure_label.setObjectName('panelTitle');layout.addWidget(self.structure_label)
        w.hierarchy_panel.setParent(self.files);layout.addWidget(w.hierarchy_panel,1);w.hierarchy_panel.tree.setMinimumHeight(110)
        self.processing=QtWidgets.QToolButton();self.processing.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QtWidgets.QMenu(self.processing);self.process_current=menu.addAction('',w.btn_apply_current.click);self.process_all=menu.addAction('',w.btn_apply_all.click)
        self.processing.setMenu(menu);w.pipeline_panel.layout().addWidget(self.processing)
        pipeline_layout=w.pipeline_panel.layout()
        for index in range(pipeline_layout.count()):
            item=pipeline_layout.itemAt(index)
            if item.layout() and item.layout().indexOf(w.step_combo)>=0:
                item.layout().removeWidget(w.step_combo);pipeline_layout.insertWidget(index,w.step_combo);break
    def _simplify_annotation(self):
        w=self.window
        w.level_group.hide();w.annotation_hint.hide();w.chk_load_annotations.hide()
        for widget in (w.btn_mark_symbol,w.btn_mark_not_symbol,w.btn_clear_symbol,w.btn_mark_rest_not_symbol):widget.hide()
        # Advanced legacy actions remain reachable through Edit.
        legacy=w.edit_menu.addMenu('L3')
        self.legacy_actions=[]
        for button in (w.btn_mark_symbol,w.btn_mark_not_symbol,w.btn_clear_symbol,w.btn_mark_rest_not_symbol):
            action=legacy.addAction(button.text());action.triggered.connect(button.click)
            self.legacy_actions.append((action,button))
        w.inspector_tabs.tabBar().hide();w.inspector_tabs.setCurrentIndex(1);w.inspector_tabs.setObjectName('inspectorTabs')
        w.instructions.hide()
        for action in w.annotation_toolbar.actions():
            if isinstance(action,QtWidgets.QWidgetAction) and action.defaultWidget()==w.instructions:action.setVisible(False)
        self.level=QtWidgets.QComboBox();self.level.setMinimumContentsLength(12)
        for key in ('section','pair','element'):self.level.addItem(self.t(key))
        self.level.currentIndexChanged.connect(lambda index:getattr(w,'level_l'+str(index+1)).setChecked(True))
        for index,radio in enumerate((w.level_l1,w.level_l2,w.level_l3)):
            radio.toggled.connect(lambda checked,index=index:checked and self.level.setCurrentIndex(index))
        w.annotation_toolbar.insertWidget(w.fit_action,self.level)
        parent_layout=w.automation_menu_button.parentWidget().layout()
        if parent_layout:parent_layout.removeWidget(w.automation_menu_button)
        w.annotation_toolbar.addWidget(w.automation_menu_button)
        w.automation_menu_button.menu().setTitle(w.text('automation'))
        self.tools.menu().addMenu(w.automation_menu_button.menu())
        w.removeToolBar(w.annotation_toolbar)
        w.annotation_toolbar.setParent(w.centralWidget());w.centralWidget().layout().insertWidget(2,w.annotation_toolbar)
        w.annotation_toolbar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,QtWidgets.QSizePolicy.Policy.Fixed)
    def _simplify_properties(self):
        w=self.window;form=w.properties.layout();self.form=form
        self.advanced=Disclosure(w.properties);self.advanced_form=QtWidgets.QFormLayout(self.advanced.body)
        self.advanced_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        for field in [w.fields['notes'],w.fields['caption'],w.parent_combo,*w.coords]:
            row=form.takeRow(field);label=row.labelItem.widget() if row.labelItem else None
            if label:self.advanced_form.addRow(label,field)
            else:self.advanced_form.addRow(field)
        primary=[w.role_combo,w.type_combo,w.fields['transcription'],w.fields['code'],w.reference_combo]
        rows=[]
        for field in primary:
            row=form.takeRow(field);rows.append((row.labelItem.widget(),field))
        for index,(label,field) in enumerate(rows,1):form.insertRow(index,label,field)
        form.insertRow(6,self.advanced)
        w.ocr_button.setProperty('primary',False)
    def translate(self):
        from .portable_ui import COPY as PORTABLE_COPY
        for key,action in self.settings_actions.items():action.setText(PORTABLE_COPY[key][0 if self.window.language=='uk' else 1])
        w=self.window
        for index,key in [(0,'scans'),(1,'annotate'),(2,'symbols'),(3,'models'),(4,'review')]:w.center_tabs.setTabText(index,self.t(key))
        self.projects_button.setText('Проєкти' if w.language=='uk' else 'Projekty')
        for index,key in [(0,'scans'),(1,'annotate'),(2,'symbols'),(3,'models'),(4,'review')]:self.nav_buttons[index].setText(self.t(key) if index!=3 else ('Моделі' if w.language=='uk' else 'Modely'))
        self.tools.setText(self.t('more'));self.model_action.setText(self.t('models'));self.help_action.setText(self.t('help'));self.help_text.setText(self.t('help_text'))
        w.automation_menu_button.menu().setTitle(w.text('automation'))
        self.refresh_action.setText(w.btn_refresh.text());self.key_action.setText(self.t('export_key'));self.project_action.setText(self.t('export_project'));self.dataset_action.setText(self.t('training_data'))
        self.structure_label.setText(self.t('structure'));w.btn_import.setText(self.t('add'))
        for action,button in self.legacy_actions:action.setText(button.text())
        for key in ('duplicate','delete'):
            button=w.hierarchy_panel.buttons[key];button.setToolTip(button.text());button.setText(self.t(key))
        w.btn_save_pipeline.setText(self.t('save_steps'));w.btn_load_pipeline.setText(self.t('load_steps'));w.lbl_pipeline_title.setText(self.t('preprocess'))
        self.processing.setText(self.t('processing'));self.process_current.setText(self.t('current'));self.process_all.setText(self.t('all'))
        self.advanced.setTitle(self.t('advanced'));self.advanced.setToolTip(self.t('collapse'))
        self.empty_title.setText(self.t('empty_title'));self.empty_detail.setText(self.t('empty_detail'));self.empty_import.setText(self.t('add'))
        if not w.annotation_dirty and not w._property_dirty and w._last_autosave_error is None:w.autosave_status.setText(w.text('saved'))
        w.mode_combo.setItemText(0,self.t('draw'));w.mode_combo.setItemText(1,self.t('select'))
        for index,key in enumerate(('section','pair','element')):self.level.setItemText(index,self.t(key))
        self.refresh();self.sync_selection()
    def refresh(self):
        w=self.window;index=w.center_tabs.currentIndex();count=w.image_list.count()
        self.project.setText(w.root.name[:28]);self.project.setToolTip(str(w.root))
        if self.brand_label is not None:self.brand_label.setText(w.center_tabs.tabText(index))
        self.hint.setText(self.t('hint_empty' if not count else {0:'hint_scan',1:'hint_annotate',2:'hint_symbols',3:'hint_models',4:'hint_review'}[index]))
        self.next_button.setText(self.t('add' if not count else 'to_annotation' if index in (0,3) else 'save_key' if index==4 else 'to_review'))
        profile=w.api_client.profile
        self.account.setText(profile['name'].split()[0] if profile and profile.get('name') else self.t('account'))
        self.account.setToolTip(w.account_action.text());w.lbl_images_title.setText(self.t('pages').format(count=count))
        self.empty.setVisible(not count);w.preview_splitter.setVisible(bool(count));self.next_button.setVisible(bool(count))
        for widget in (w.preview_mode,w.preview_zoom_in,w.preview_zoom_out,w.preview_fit,w.preview_actual,w.lbl_preview_title,w.lbl_status,w.preview_caption):widget.setVisible(bool(count))
        w.preview_link.setVisible(bool(count) and w.preview_mode.currentIndex()==0)
        w.pipeline_panel.setVisible(index==0 and bool(count));w.export_menu_button.setEnabled(bool(count))
        for stage in (1,2,4):w.center_tabs.setTabEnabled(stage,bool(count))
        for stage,button in self.nav_buttons.items():button.setEnabled(stage not in (1,2,4) or bool(count));button.setChecked(stage==index)
        busy=w._task is not None or w._process is not None;self.header.setEnabled(not busy)
        self.rail.setEnabled(not busy)
    def on_stage(self,index):
        w=self.window;w.center_tabs.setTabVisible(3,index==3)
        self.structure_label.setVisible(index==1);w.hierarchy_panel.setVisible(index==1)
        w.image_list.setMaximumHeight(125 if index==1 else 16777215)
        if index==1:w.inspector_tabs.setCurrentIndex(1)
        self.refresh()
    def advance(self):
        w=self.window;index=w.center_tabs.currentIndex()
        if not w.image_list.count():w.btn_import.click()
        elif index in (0,3):w.center_tabs.setCurrentIndex(1)
        elif index==4:w.digitization.export()
        else:w.center_tabs.setCurrentIndex(4)
    def open_models(self):
        self.window.center_tabs.setTabVisible(3,True);self.window.center_tabs.setCurrentIndex(3)
    def sync_selection(self,*_):
        w=self.window;item=next((item for item in w.annotation_items if item.id==w._active_annotation),None)
        if item is None:return
        kind=w.type_combo.currentData();is_element=item.level=='L3'
        for widget,visible in [(w.type_combo,is_element),(w.fields['transcription'],is_element and kind!='cipher_symbol'),(w.fields['code'],is_element and kind!='readable'),(w.reference_combo,is_element and kind=='cipher_symbol')]:
            self.form.setRowVisible(widget,visible)
        w.reference_combo.setEnabled(is_element and kind=='cipher_symbol')
        w.ocr_button.setVisible(is_element and kind=='readable')
