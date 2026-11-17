"""Canonical symbols and their page occurrences, inside the native Symbols tab."""
from __future__ import annotations
from pathlib import Path
from PIL import Image
from PyQt6 import QtCore,QtGui,QtWidgets
from .symbol_catalog import occurrence_index,update_symbol

COPY={
 'import_library':('Імпорт бібліотеки…','Importovať knižnicu…'),
 'export_library':('Експорт бібліотеки…','Exportovať knižnicu…'),
 'transferred':('Бібліотеку перенесено. Однакові коди означають однакові символи.','Knižnica prenesená. Rovnaké kódy označujú rovnaké symboly.'),
 'samples':('Зразків','Vzory'),
 'catalog':('Каталог символів','Katalóg symbolov'),'fragments':('Фрагменти L3','Výrezy L3'),
 'search':('Пошук за кодом або назвою…','Hľadať podľa kódu alebo názvu…'),
 'refresh':('Оновити каталог','Obnoviť katalóg'),'code':('Код','Kód'),'title':('Назва','Názov'),
 'count':('Входжень','Výskyty'),'page':('Сторінка','Strana'),'notes':('Примітки','Poznámky'),
 'add':('Додати / змінити опис…','Pridať / upraviť popis…'),
 'delete':('Видалити опис','Odstrániť popis'),'representative':('Зробити еталонним','Použiť ako vzor'),
 'open':('Відкрити анотацію','Otvoriť anotáciu'),'uncoded':('Без коду','Bez kódu'),
 'intro':('Коди об’єднують однакові шифросимволи на різних сторінках цього проєкту. Вибери входження, щоб побачити фрагмент або зробити його еталонним.','Kódy spájajú rovnaké šifrové symboly na rôznych stranách tohto projektu. Vyber výskyt na zobrazenie výrezu alebo nastavenie vzoru.'),
 'empty':('Шифросимволів ще немає. Задай L3 тип «Шифросимвол» і код у властивостях.','Zatiaľ žiadne šifrové symboly. Nastav pre L3 typ Šifrový symbol a kód vo vlastnostiach.'),
 'select':('Вибери входження для перегляду.','Vyber výskyt na zobrazenie.'),
 'remove_prompt':('Видалити лише опис із каталогу? Коди й анотації на сканах залишаться.','Odstrániť iba popis z katalógu? Kódy a anotácie na skenoch zostanú.'),
 'summary':('Кодів: {codes} · входжень: {count} · імпортованих зразків: {samples}','Kódy: {codes} · výskyty: {count} · importované vzory: {samples}'),
 'missing_rep':('Еталонне входження більше недоступне. Вибери інше.','Vzorový výskyt už nie je dostupný. Vyber iný.'),
 'no_code':('Спочатку задай код символу.','Najprv nastav kód symbolu.'),
}


class CatalogPanel(QtWidgets.QWidget):
    def __init__(self,workspace):
        super().__init__();self.workspace=workspace;self.data={'catalog':{},'occurrences':{},'failures':[]};self._code=None
        layout=QtWidgets.QVBoxLayout(self);self.intro=QtWidgets.QLabel();self.intro.setWordWrap(True);layout.addWidget(self.intro)
        row=QtWidgets.QHBoxLayout();self.search=QtWidgets.QLineEdit();self.search.textChanged.connect(self.filter)
        self.refresh_button=QtWidgets.QPushButton();self.refresh_button.clicked.connect(lambda:workspace._guard(self.refresh))
        row.addWidget(self.search,1);row.addWidget(self.refresh_button);layout.addLayout(row)
        transfers=QtWidgets.QHBoxLayout()
        self.transfer_buttons={}
        for key,callback in [('import_library',self.import_library),('export_library',self.export_library)]:
            button=QtWidgets.QPushButton();button.clicked.connect(lambda checked=False,fn=callback:workspace._guard(fn))
            self.transfer_buttons[key]=button;transfers.addWidget(button)
        transfers.addStretch();layout.addLayout(transfers)
        split=QtWidgets.QSplitter();layout.addWidget(split,1)
        self.codes=QtWidgets.QTableWidget(0,4);self.codes.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.codes.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection);self.codes.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.codes.verticalHeader().hide()
        self.codes.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.codes.horizontalHeader().setMinimumSectionSize(55)
        self.codes.horizontalHeader().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.codes.itemSelectionChanged.connect(self.select_code);split.addWidget(self.codes)
        details=QtWidgets.QWidget();right=QtWidgets.QVBoxLayout(details);right.setContentsMargins(8,0,0,0)
        self.preview=QtWidgets.QLabel();self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumSize(160,100);self.preview.setMaximumHeight(200)
        right.addWidget(self.preview)
        self.occurrences=QtWidgets.QTableWidget(0,2);self.occurrences.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.occurrences.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection);self.occurrences.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.occurrences.verticalHeader().hide();self.occurrences.horizontalHeader().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.occurrences.itemSelectionChanged.connect(lambda:workspace._guard(self.show_preview));self.occurrences.cellDoubleClicked.connect(lambda *_:workspace._guard(self.open_occurrence))
        right.addWidget(self.occurrences,1);split.addWidget(details);split.setSizes([380,330])
        self.buttons={}
        for keys in [('add','delete'),('representative','open')]:
            row=QtWidgets.QHBoxLayout()
            for key in keys:
                button=QtWidgets.QPushButton();button.clicked.connect(lambda checked=False,name=key:workspace._guard(getattr(self,name)))
                self.buttons[key]=button;row.addWidget(button)
            layout.addLayout(row)
        self.status=QtWidgets.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);self.translate()
    def t(self,key):return COPY[key][0 if self.workspace.language=='uk' else 1]
    def translate(self):
        self.intro.setText(self.t('intro'));self.search.setPlaceholderText(self.t('search'));self.refresh_button.setText(self.t('refresh'))
        self.codes.setHorizontalHeaderLabels([self.t('code'),self.t('title'),self.t('count'),self.t('samples')]);self.occurrences.setHorizontalHeaderLabels([self.t('page'),'L3'])
        for key,button in {**self.buttons,**self.transfer_buttons}.items():button.setText(self.t(key))
        if self.preview.pixmap() is None or self.preview.pixmap().isNull():self.preview.setText(self.t('select'))
    def refresh(self):
        window=self.workspace
        if window._task is not None or window._process is not None:return
        if window.save_annotations_current(silent=True) is False:return
        root=window.root
        window.run_task(lambda:occurrence_index(root),self.loaded)
    def loaded(self,data):
        old=self._code;self.data=data;self.codes.blockSignals(True);self.codes.setRowCount(0)
        for code in sorted(data['occurrences'],key=lambda value:value.casefold()):
            row=self.codes.rowCount();self.codes.insertRow(row)
            meta=data['catalog'].get(code,{})
            for column,value in enumerate((code or self.t('uncoded'),meta.get('title',''),str(len(data['occurrences'][code])),str(len(meta.get('samples',[]))))):
                self.codes.setItem(row,column,QtWidgets.QTableWidgetItem(value))
            self.codes.item(row,0).setData(QtCore.Qt.ItemDataRole.UserRole,code)
        self.codes.blockSignals(False);self.filter(self.search.text());self._code=None
        self.status.setText('\n'.join(data['failures']) if data['failures'] else self.t('summary').format(codes=sum(bool(code) for code in data['occurrences']),count=sum(len(entries) for entries in data['occurrences'].values()),samples=sum(len(entry.get('samples',[])) for entry in data['catalog'].values())))
        if not data['occurrences']:self.status.setText(self.t('empty'))
        for row in range(self.codes.rowCount()):
            if self.codes.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)==old:self.codes.selectRow(row);break
        else:
            if self.codes.rowCount():self.codes.selectRow(0)
            else:self.occurrences.setRowCount(0);self.preview.clear();self.preview.setText(self.t('select'))
    def filter(self,query):
        for row in range(self.codes.rowCount()):
            self.codes.setRowHidden(row,query.casefold() not in ' '.join(self.codes.item(row,col).text() for col in (0,1)).casefold())
    def select_code(self):
        row=self.codes.currentRow()
        if row<0:return
        self._code=self.codes.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        self.occurrences.blockSignals(True);self.occurrences.setRowCount(0);entries=self.data['occurrences'].get(self._code,[])
        for row,entry in enumerate(entries):
            self.occurrences.insertRow(row);cell=QtWidgets.QTableWidgetItem(entry['image']);cell.setData(QtCore.Qt.ItemDataRole.UserRole,entry);self.occurrences.setItem(row,0,cell)
            self.occurrences.setItem(row,1,QtWidgets.QTableWidgetItem('#'+str(entry['annotation_id'])))
        self.occurrences.blockSignals(False)
        rep=self.data['catalog'].get(self._code,{}).get('representative');index=0
        if rep:
            matches=[index for index,entry in enumerate(entries) if entry['image']==rep['image'] and entry['annotation_id']==rep['annotation_id']]
            if matches:index=matches[0]
            else:self.status.setText(self.t('missing_rep'))
        if entries:self.occurrences.selectRow(index)
        else:
            self.preview.clear()
            samples=self.data['catalog'].get(self._code,{}).get('samples',[])
            if samples:
                from .portable import decode_sample
                crop=decode_sample(samples[0]);crop.thumbnail((320,180))
                self.preview.setPixmap(QtGui.QPixmap.fromImage(self.workspace._pil_to_qimage(crop)))
            else:self.preview.setText(self.t('select'))
    def occurrence(self):
        row=self.occurrences.currentRow()
        return self.occurrences.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole) if row>=0 else None
    def show_preview(self):
        entry=self.occurrence()
        if entry is None:return
        root=self.workspace.root;entry=dict(entry)
        def operation():
            from .annotations import annotation_path,load_annotations
            from .digitization import crop_element
            path=root/'images_raw'/entry['image'];data=load_annotations(annotation_path(root,path))
            item=next(item for item in data.items if item.id==entry['annotation_id'])
            with Image.open(path) as image:crop=crop_element(image,item);crop.thumbnail((320,180));return crop
        def completed(crop):
            self.preview.setPixmap(QtGui.QPixmap.fromImage(self.workspace._pil_to_qimage(crop)))
        self.workspace.run_task(operation,completed)
    def add(self):
        code=self._code or '';meta=self.data['catalog'].get(code,{})
        dialog=QtWidgets.QDialog(self);dialog.setWindowTitle(self.t('add'));layout=QtWidgets.QFormLayout(dialog)
        code_field=QtWidgets.QLineEdit(code);code_field.setReadOnly(bool(code));title=QtWidgets.QLineEdit(meta.get('title',''));notes=QtWidgets.QLineEdit(meta.get('notes',''))
        layout.addRow(self.t('code'),code_field);layout.addRow(self.t('title'),title);layout.addRow(self.t('notes'),notes)
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save|QtWidgets.QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()==QtWidgets.QDialog.DialogCode.Accepted:
            update_symbol(self.workspace.root,code_field.text(),title.text(),notes.text(),meta.get('representative'));self._code=code_field.text().strip();self.refresh()
    def delete(self):
        if not self._code:return
        if QtWidgets.QMessageBox.question(self,self.t('delete'),self.t('remove_prompt'))!=QtWidgets.QMessageBox.StandardButton.Yes:return
        update_symbol(self.workspace.root,self._code,delete=True);self.refresh()
    def representative(self):
        entry=self.occurrence()
        if not entry or not self._code:self.status.setText(self.t('no_code'));return
        meta=self.data['catalog'].get(self._code,{})
        update_symbol(self.workspace.root,self._code,meta.get('title',''),meta.get('notes',''),{'image':entry['image'],'annotation_id':entry['annotation_id']});self.refresh()
    def open(self):self.open_occurrence()
    def open_occurrence(self):
        entry=self.occurrence()
        if entry:self.workspace.open_annotation_location(self.workspace.root/'images_raw'/entry['image'],entry['annotation_id'])

    def import_library(self):
        import json
        from .portable import import_symbol_library
        if self.workspace.save_annotations_current(silent=True) is False:return
        source,_=QtWidgets.QFileDialog.getOpenFileName(self,self.t('import_library'),str(self.workspace.root),'JSON (*.json)')
        if not source:return
        path=Path(source)
        if path.stat().st_size>32*1024*1024:raise ValueError('Library JSON exceeds 32 MiB')
        payload=json.loads(path.read_text(encoding='utf-8-sig'));root=self.workspace.root
        self.workspace.run_task(lambda:import_symbol_library(root,payload),lambda count:self.refresh())

    def export_library(self):
        from .portable import export_symbol_library
        if self.workspace.save_annotations_current(silent=True) is False:return
        target,_=QtWidgets.QFileDialog.getSaveFileName(self,self.t('export_library'),str(self.workspace.root/'results/symbol-library.json'),'JSON (*.json)')
        if not target:return
        root=self.workspace.root
        self.workspace.run_task(lambda:export_symbol_library(root,Path(target)),lambda payload:self.status.setText(self.t('transferred')))
