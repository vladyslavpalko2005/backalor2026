"""Native desktop extension: review semantics and route L3 crops to local models."""
from __future__ import annotations
import copy
from pathlib import Path
from PyQt6 import QtCore, QtWidgets
from .digitization import (LocalClassifier, classify_elements, recognize_elements,
    effective_role, effective_type, element_issues, export_key, export_classification_dataset)

COPY = {
 'tab':('Оцифрування','Digitalizácia'),
 'library_recognize':('Розпізнати за бібліотекою','Rozpoznať podľa knižnice'),
 'library_threshold':('Мінімальна схожість зі зразком','Minimálna podobnosť so vzorom'),
 'library_margin':('Відрив від другого варіанта','Odstup od druhého variantu'),
 'library_help':('Бібліотека використовує перевірені L3 та імпортовані PNG-зразки: визначає читабельні елементи й шифросимволи та заповнює порожні поля. Непевні збіги залишаються без змін. Для нового рукописного тексту вкажи локальну TrOCR. Схожість зі зразком не є ймовірністю правильності.','Knižnica používa overené L3 a importované PNG vzory: rozlišuje čitateľné prvky a šifrové symboly a vypĺňa prázdne polia. Neisté zhody ponechá bez zmeny. Pre nový rukopis nastav lokálny TrOCR. Podobnosť so vzorom nie je pravdepodobnosť správnosti.'),
 'library':('Бібліотека та відповідності…','Knižnica a zhody…'),
 'export_ciphertext':('Експорт шифротексту…','Exportovať šifrový text…'),
 'ciphertext_exported':('Шифротекст збережено. Статус: {status}.','Šifrový text uložený. Stav: {status}.'),
 'intro':('Перевір роль, тип і результат кожного L3. Подвійне натискання відкриває рамку на скані.','Skontroluj rolu, typ a výsledok každého L3. Dvojklik otvorí rámček na skene.'),
 'help':('Моделі необов’язкові для ручної роботи. Класи типів: readable / cipher_symbol; класи символів — їхні коди. Автоматика заповнює тільки порожні поля; результат потребує перевірки.','Pri ručnej práci modely nepotrebuješ. Triedy typov: readable / cipher_symbol; triedy symbolov sú ich kódy. Automatika vyplní iba prázdne polia; výsledok treba skontrolovať.'),
 'type_model':('Модель типів (.pt)','Model typov (.pt)'), 'symbol_model':('Модель символів (.pt)','Model symbolov (.pt)'),
 'threshold':('Поріг впевненості','Prah istoty'), 'classify':('Визначити типи L3','Určiť typy L3'),
 'recognize':('Розпізнати L3 за типом','Rozpoznať L3 podľa typu'), 'refresh':('Оновити','Obnoviť'),
 'export':('Експорт ключа…','Exportovať kľúč…'), 'dataset':('Навчальні фрагменти…','Trénovacie výrezy…'),
 'review':('Підтвердити вибраний L3','Potvrdiť vybraný L3'),
 'role':('Роль','Rola'), 'type':('Тип елемента','Typ prvku'), 'text':('Транскрипція / код','Prepis / kód'),
 'state':('Перевірка','Kontrola'), 'plain':('Відкритий текст','Otvorený text'), 'cipher':('Шифротекст','Šifrový text'),
 'readable':('Читабельний','Čitateľný'), 'cipher_symbol':('Шифросимвол','Šifrový symbol'), 'unknown':('Не визначено','Neurčené'),
 'needs_review':('Потрібна перевірка','Vyžaduje kontrolu'), 'missing_role':('Немає ролі','Chýba rola'),
 'missing_type':('Немає типу','Chýba typ'), 'missing_transcription':('Немає транскрипції','Chýba prepis'),
 'missing_symbol_code':('Немає коду символу','Chýba kód symbolu'), 'checked':('Перевірено','Skontrolované'),
 'summary':('Елементів: {l3} · Перевірено: {reviewed}/{l3}','Prvky: {l3} · Skontrolované: {reviewed}/{l3}'),
 'done':('Змінено: {changed} · нижче порогу / порожній результат: {uncertain} · пропущено: {skipped}','Zmenené: {changed} · pod prahom / prázdny výsledok: {uncertain} · preskočené: {skipped}'),
 'models_missing':('Вкажи модель TrOCR на вкладці «Моделі та навчання» або модель символів тут.','Nastav model TrOCR na karte Modely a tréning alebo model symbolov tu.'),
 'model_missing':('Вибери навчену локальну модель типів.','Vyber natrénovaný lokálny model typov.'),
 'review_missing':('Спочатку задай роль, тип і транскрипцію або код символу.','Najprv nastav rolu, typ a prepis alebo kód symbolu.'),
 'exported':('Ключ збережено. Статус: {status}.','Kľúč uložený. Stav: {status}.'),
 'types':('Типи елементів','Typy prvkov'), 'symbols':('Коди шифросимволів','Kódy šifrových symbolov'),
 'dataset_done':('Експортовано фрагментів: {count}','Exportované výrezy: {count}'),
 'invalid_transcription_reference':('Некоректний зв’язок із текстом','Neplatný odkaz na text'),
 'automatic':('Автоматичне розпізнавання','Automatické rozpoznávanie'),
 'filter_all':('Усі елементи','Všetky prvky'), 'filter_unreviewed':('Потрібна перевірка','Vyžaduje kontrolu'),
 'filter_incomplete':('Є пропуски','Chýbajúce údaje'), 'filter_reviewed':('Перевірені','Skontrolované'),
 'next_issue':('Наступний неперевірений','Ďalší neskontrolovaný'),
 'no_issues':('У вибраному фільтрі немає неперевірених елементів.','Vo vybranom filtri nie sú neskontrolované prvky.'),
 'no_elements':('На сторінці ще немає елементів L3. Створи їх на вкладці «Розмітка».','Na strane ešte nie sú prvky L3. Vytvor ich na karte Anotovanie.'),
}


class DigitizationPanel(QtWidgets.QWidget):
    def __init__(self, workspace):
        super().__init__();self.workspace=workspace
        layout=QtWidgets.QVBoxLayout(self);layout.setSpacing(12)
        self.intro=QtWidgets.QLabel();self.intro.setWordWrap(True);layout.addWidget(self.intro)
        library_actions=QtWidgets.QHBoxLayout()
        self.library_button=QtWidgets.QPushButton()
        self.library_button.clicked.connect(lambda:workspace._guard(self.open_library))
        self.ciphertext_button=QtWidgets.QPushButton()
        self.ciphertext_button.clicked.connect(lambda:workspace._guard(self.export_ciphertext))
        library_actions.addWidget(self.library_button);library_actions.addWidget(self.ciphertext_button);library_actions.addStretch()
        layout.addLayout(library_actions)
        from .workflow_ui import Disclosure
        self.automation=Disclosure()
        automation_shell=QtWidgets.QVBoxLayout(self.automation.body);automation_shell.setContentsMargins(0,0,0,0)
        self.automation_scroll=QtWidgets.QScrollArea();self.automation_scroll.setWidgetResizable(True)
        self.automation_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.automation_scroll.setMinimumHeight(220);self.automation_scroll.setMaximumHeight(260)
        automation_content=QtWidgets.QWidget();automation_layout=QtWidgets.QVBoxLayout(automation_content)
        automation_layout.setContentsMargins(0,0,8,0);automation_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        self.automation_scroll.setWidget(automation_content);automation_shell.addWidget(self.automation_scroll)
        form=QtWidgets.QFormLayout();form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows);self.model_fields={};self.model_labels={}
        for key in ('type_model','symbol_model'):
            field=QtWidgets.QLineEdit();field.setPlaceholderText('/path/to/best.pt')
            choose=QtWidgets.QPushButton('…');choose.setAccessibleName(key);choose.setMaximumWidth(38)
            choose.clicked.connect(lambda checked=False,target=field:workspace._choose_weights(target))
            row=QtWidgets.QHBoxLayout();row.addWidget(field,1);row.addWidget(choose)
            label=QtWidgets.QLabel();label.setBuddy(field);form.addRow(label,row)
            self.model_fields[key]=field;self.model_labels[key]=label
        self.threshold=QtWidgets.QDoubleSpinBox();self.threshold.setRange(.01,1);self.threshold.setSingleStep(.05);self.threshold.setValue(.8)
        self.library_threshold=QtWidgets.QDoubleSpinBox();self.library_threshold.setRange(.01,1);self.library_threshold.setValue(.85);self.library_threshold.setSingleStep(.05)
        self.library_margin=QtWidgets.QDoubleSpinBox();self.library_margin.setRange(.01,1);self.library_margin.setValue(.10);self.library_margin.setSingleStep(.05)
        self.library_labels={}
        for key in ('library_threshold','library_margin'):
            label=QtWidgets.QLabel();label.setBuddy(getattr(self,key));form.addRow(label,getattr(self,key));self.library_labels[key]=label
        self.threshold_label=QtWidgets.QLabel();self.threshold_label.setBuddy(self.threshold);form.addRow(self.threshold_label,self.threshold)
        automation_layout.addLayout(form)
        self.help=QtWidgets.QLabel();self.help.setWordWrap(True);self.help.setObjectName('mutedLabel');automation_layout.addWidget(self.help)
        row=QtWidgets.QHBoxLayout();self.buttons={}
        for key,callback in [('classify',self.classify),('recognize',self.recognize)]:
            button=QtWidgets.QPushButton();button.clicked.connect(lambda checked=False,fn=callback:workspace._guard(fn));self.buttons[key]=button;row.addWidget(button)
        automation_layout.addLayout(row)
        self.buttons['library_recognize']=QtWidgets.QPushButton()
        self.buttons['library_recognize'].clicked.connect(lambda:workspace._guard(self.recognize_library))
        automation_layout.addWidget(self.buttons['library_recognize'])
        self.library_help=QtWidgets.QLabel();self.library_help.setWordWrap(True);self.library_help.setObjectName('mutedLabel');automation_layout.addWidget(self.library_help)
        layout.addWidget(self.automation)
        filters=QtWidgets.QHBoxLayout();self.filter_combo=QtWidgets.QComboBox()
        for value in ('all','unreviewed','incomplete','reviewed'):self.filter_combo.addItem('',value)
        self.filter_combo.currentIndexChanged.connect(self.apply_filter);filters.addWidget(self.filter_combo)
        self.next_issue_button=QtWidgets.QPushButton();self.next_issue_button.clicked.connect(lambda:workspace._guard(self.next_issue));filters.addWidget(self.next_issue_button);filters.addStretch()
        self.buttons['refresh']=QtWidgets.QPushButton();self.buttons['refresh'].clicked.connect(self.refresh);filters.addWidget(self.buttons['refresh']);layout.addLayout(filters)
        self.summary=QtWidgets.QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QtWidgets.QTableWidget(0,5);self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.horizontalHeader().setSectionResizeMode(3,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4,QtWidgets.QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(4,210)
        self.table.cellDoubleClicked.connect(lambda row,column:workspace._guard(lambda:self.open_element(row,column)));layout.addWidget(self.table,1)
        self.empty=QtWidgets.QLabel();self.empty.setWordWrap(True);self.empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.empty,1)
        row=QtWidgets.QHBoxLayout()
        for key,callback in [('review',self.review),('dataset',self.dataset),('export',self.export)]:
            button=QtWidgets.QPushButton();button.clicked.connect(lambda checked=False,fn=callback:workspace._guard(fn));self.buttons[key]=button;row.addWidget(button)
        layout.addLayout(row)
        self.buttons['review'].setProperty('primary',True);self.buttons['dataset'].hide();self.buttons['export'].hide()
        self.bulk_button=QtWidgets.QPushButton();self.bulk_button.clicked.connect(lambda:workspace._guard(self.bulk_edit));row.addWidget(self.bulk_button)
        self.message=QtWidgets.QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.translate()

    def t(self,key):return COPY[key][0 if self.workspace.language=='uk' else 1]
    def translate(self):
        from .hierarchy_ui import translate as hierarchy_text
        self.library_button.setText(self.t('library'));self.ciphertext_button.setText(self.t('export_ciphertext'))
        self.bulk_button.setText(hierarchy_text(self.workspace,'bulk'))
        self.automation.setTitle(self.t('automatic'));self.next_issue_button.setText(self.t('next_issue'));self.empty.setText(self.t('no_elements'))
        for index,value in enumerate(('all','unreviewed','incomplete','reviewed')):self.filter_combo.setItemText(index,self.t('filter_'+value))
        self.library_help.setText(self.t('library_help'))
        for key,label in self.library_labels.items():label.setText(self.t(key))
        for key,label in self.model_labels.items():label.setText(self.t(key))
        for key,button in self.buttons.items():button.setText(self.t(key))
        self.intro.setText(self.t('intro'));self.help.setText(self.t('help'));self.threshold_label.setText(self.t('threshold'))
        self.table.setHorizontalHeaderLabels(['L3 / L2',self.t('role'),self.t('type'),self.t('text'),self.t('state')])
        self.refresh()
    def refresh(self):
        items=self.workspace.annotation_items
        elements=[item for item in items if item.level=='L3']
        self.table.setRowCount(len(elements))
        for row,item in enumerate(elements):
            role=effective_role(item,items);kind=effective_type(item);issues=element_issues(item,items)
            values=[f'#{item.id} / #{item.parent_id}',self.t('plain' if role=='plaintext' else 'cipher' if role=='ciphertext' else 'unknown'),
                    self.t(kind if kind in ('readable','cipher_symbol') else 'unknown'),
                    item.transcription if kind=='readable' else item.symbol_code if kind=='cipher_symbol' else '',
                    ', '.join(self.t(key) for key in issues) if issues else self.t('checked')]
            for column,value in enumerate(values):self.table.setItem(row,column,QtWidgets.QTableWidgetItem(value))
            self.table.item(row,0).setData(QtCore.Qt.ItemDataRole.UserRole,item.id)
            if item.type_confidence is not None:self.table.item(row,2).setToolTip(f'{item.type_source}: {item.type_confidence:.1%}')
            if item.recognition_confidence is not None:self.table.item(row,3).setToolTip(f'{item.recognition_source}: {item.recognition_confidence:.1%}')
        self.summary.setText(self.t('summary').format(l1=sum(item.level=='L1' for item in items),l2=sum(item.level=='L2' for item in items),l3=len(elements),reviewed=sum(not element_issues(item,items) for item in elements)))
        self.table.setVisible(bool(elements));self.empty.setVisible(not elements);self.apply_filter()
    def selected(self):
        row=self.table.currentRow()
        return self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole) if row>=0 else None
    def bulk_edit(self):
        from .hierarchy_ui import translate as ht
        from .annotation_ops import bulk_update
        if not self.workspace._flush_properties():return
        ids={self.table.item(index.row(),0).data(QtCore.Qt.ItemDataRole.UserRole) for index in self.table.selectionModel().selectedRows()}
        if not ids:self.message.setText(ht(self.workspace,'choose'));return
        dialog=QtWidgets.QDialog(self);dialog.setWindowTitle(ht(self.workspace,'bulk'));dialog.resize(460,300)
        form=QtWidgets.QFormLayout(dialog);description=QtWidgets.QLabel(ht(self.workspace,'selection').format(count=len(ids)));description.setWordWrap(True);form.addRow(description)
        fields={};checks={}
        for key,label in [('text_role',self.t('role')),('element_type',self.t('type')),('label',ht(self.workspace,'caption')),('symbol_code',self.workspace.text('code'))]:
            check=QtWidgets.QCheckBox(label);checks[key]=check
            if key in ('text_role','element_type'):
                field=QtWidgets.QComboBox();field.addItem(self.t('unknown'),'')
                values=[('plain','plaintext'),('cipher','ciphertext')] if key=='text_role' else [('readable','readable'),('cipher_symbol','cipher_symbol')]
                for text,value in values:field.addItem(self.t(text),value)
            else:field=QtWidgets.QLineEdit()
            field.setEnabled(False);check.toggled.connect(field.setEnabled);fields[key]=field;form.addRow(check,field)
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Apply|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QtWidgets.QDialog.DialogCode.Accepted:return
        changes={key:field.currentData() if isinstance(field,QtWidgets.QComboBox) else field.text() for key,field in fields.items() if checks[key].isChecked()}
        if not changes:return
        items,count=bulk_update(self.workspace.annotation_items,ids,changes)
        self.complete((items,{'changed':count,'uncertain':0,'skipped':0}))
    def open_element(self,row,column):
        if not self.workspace._flush_properties():return
        annotation_id=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        self.workspace.select_annotation(annotation_id);self.workspace.center_tabs.setCurrentIndex(1);self.workspace.inspector_tabs.setCurrentIndex(1)
        item=next((item for item in self.workspace.annotation_items if item.id==annotation_id),None)
        if item:
            self.workspace.draw_action.setChecked(False)
            x,y,width,height=item.bbox;padding=max(width,height)*.5+20
            rectangle=QtCore.QRectF(x-padding,y-padding,width+2*padding,height+2*padding)
            self.workspace.annotation_canvas._fitted=False
            self.workspace.annotation_canvas.fitInView(rectangle,QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    def apply_filter(self,*_):
        if not hasattr(self,'table'):return
        indexed={item.id:item for item in self.workspace.annotation_items};mode=self.filter_combo.currentData()
        for row in range(self.table.rowCount()):
            cell=self.table.item(row,0)
            if cell is None:continue
            item=indexed.get(cell.data(QtCore.Qt.ItemDataRole.UserRole))
            issues=element_issues(item,self.workspace.annotation_items) if item else []
            match=mode=='all' or (mode=='unreviewed' and item is not None and not item.reviewed) or (mode=='reviewed' and not issues) or (mode=='incomplete' and any(issue!='needs_review' for issue in issues))
            self.table.setRowHidden(row,not match)
    def next_issue(self):
        if not self.workspace._flush_properties():return
        count=self.table.rowCount();start=self.table.currentRow()+1;indexed={item.id:item for item in self.workspace.annotation_items}
        for offset in range(count):
            row=(start+offset)%count
            if self.table.isRowHidden(row):continue
            item=indexed.get(self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole))
            if item and element_issues(item,self.workspace.annotation_items):
                self.table.selectRow(row);self.open_element(row,0);return
        self.message.setText(self.t('no_issues'))
    def review(self):
        if not self.workspace._flush_properties():return
        item=next((item for item in self.workspace.annotation_items if item.id==self.selected()),None)
        if item is None:return
        if any(issue!='needs_review' for issue in element_issues(item,self.workspace.annotation_items)):
            self.message.setText(self.t('review_missing'));return
        item.reviewed=True;self.workspace.annotation_dirty=True;self.workspace._record();self.workspace._checkpoint_safely();self.refresh()
    def ready(self):
        return self.workspace._flush_properties() and self.workspace.current_image is not None and self.workspace._task is None and self.workspace._process is None
    def complete(self,result):
        items,counts=result;window=self.workspace
        window.annotation_items=items;window.annotation_dirty=True;window._record();window._redraw_annotations();window.refresh_annotation_lists()
        if window._active_annotation:window.select_annotation(window._active_annotation)
        window._checkpoint_safely();self.refresh();self.message.setText(self.t('done').format(**counts))
    def classify(self):
        if not self.ready():return
        path=self.model_fields['type_model'].text().strip()
        if not path:self.message.setText(self.t('model_missing'));return
        self.workspace.save_model_settings();image=self.workspace.current_image.copy();items=copy.deepcopy(self.workspace.annotation_items);threshold=self.threshold.value()
        self.workspace.run_task(lambda:classify_elements(image,items,LocalClassifier(path,expected_types=True),threshold),self.complete)
    def recognize(self):
        if not self.ready():return
        ocr=self.workspace.ocr_path.text().strip();symbols=self.model_fields['symbol_model'].text().strip();threshold=self.threshold.value()
        if not ocr and not symbols:self.message.setText(self.t('models_missing'));return
        self.workspace.save_model_settings();image=self.workspace.current_image.copy();items=copy.deepcopy(self.workspace.annotation_items)
        root=self.workspace.root
        def operation():
            allowed_codes=None
            text=None
            needs_text=any(item.level=='L3' and effective_type(item)=='readable' and not item.transcription.strip() for item in items)
            needs_symbols=any(item.level=='L3' and effective_type(item)=='cipher_symbol' and not item.symbol_code.strip() for item in items)
            if symbols and needs_symbols:
                from .symbol_catalog import occurrence_index
                library=occurrence_index(root)
                if library['failures']:raise ValueError('\n'.join(library['failures']))
                allowed_codes={code for code in library['occurrences'] if code}
            if ocr and needs_text:
                from .jobs import LocalTextRecognizer
                text=LocalTextRecognizer(Path(ocr))
            symbol=LocalClassifier(symbols) if symbols and needs_symbols else None
            return recognize_elements(image,items,text,symbol,threshold,allowed_codes=allowed_codes)
        self.workspace.run_task(operation,self.complete)
    def export(self):
        if self.workspace.save_annotations_current(silent=True) is False:return
        target,_=QtWidgets.QFileDialog.getSaveFileName(self,self.t('export'),str(self.workspace.root/'results/key.json'),'JSON (*.json);;CSV (*.csv)')
        if target:
            payload=export_key(self.workspace.root,Path(target));self.message.setText(self.t('exported').format(status=payload['status']))
    def dataset(self):
        if self.workspace.save_annotations_current(silent=True) is False:return
        choices=[self.t('types'),self.t('symbols')]
        choice,ok=QtWidgets.QInputDialog.getItem(self,self.t('dataset'),self.t('type'),choices,0,False)
        if not ok:return
        target=QtWidgets.QFileDialog.getExistingDirectory(self,self.t('dataset'),str(self.workspace.root))
        if not target:return
        root=self.workspace.root;task='types' if choice==choices[0] else 'symbols'
        self.workspace.run_task(lambda:export_classification_dataset(root,Path(target),task),lambda count:self.message.setText(self.t('dataset_done').format(count=count)))

    def open_library(self):
        from .cipher_library_ui import CipherLibraryWindow
        if self.workspace.save_annotations_current(silent=True) is False:return
        if getattr(self,'library_window',None) is not None:self.library_window.close()
        self.library_window=CipherLibraryWindow(self.workspace)
        self.library_window.show()

    def export_ciphertext(self):
        from .cipher_library import export_ciphertext
        if self.workspace.save_annotations_current(silent=True) is False:return
        target,_=QtWidgets.QFileDialog.getSaveFileName(self,self.t('export_ciphertext'),str(self.workspace.root/'results/ciphertext.json'),'JSON (*.json);;CSV (*.csv)')
        if target:
            payload=export_ciphertext(self.workspace.root,Path(target))
            self.message.setText(self.t('ciphertext_exported').format(status=payload['status']))

    def recognize_library(self):
        from .portable import build_symbol_library
        from .library_recognition import recognize_from_library
        if not self.ready():return
        if self.workspace.save_annotations_current(silent=True) is False:return
        self.workspace.save_model_settings()
        root=self.workspace.root;image=self.workspace.current_image.copy();items=copy.deepcopy(self.workspace.annotation_items)
        threshold=self.library_threshold.value();margin=self.library_margin.value()
        self.workspace.run_task(lambda:recognize_from_library(image,items,build_symbol_library(root),threshold,margin),self.complete)
