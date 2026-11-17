"""Owner-managed document visibility and invitations, backed by server permissions."""
from PyQt6 import QtCore, QtWidgets
from .jobs import Task

COPY={
 'title':('Доступ до документа','Prístup k dokumentu'),
 'name':('Назва','Názov'),'description':('Опис','Popis'),'visibility':('Видимість','Viditeľnosť'),
 'private':('Приватний','Súkromný'),'public':('Публічний','Verejný'),
 'help':('Приватний документ доступний власнику й запрошеним учасникам. Публічний документ, включно зі сканами та анотаціями, можуть завантажити всі користувачі Backalor, які увійшли. Завантажені копії залишаються у користувачів після відкликання доступу.','Súkromný dokument je prístupný vlastníkovi a pozvaným účastníkom. Verejný dokument vrátane skenov a anotácií môžu stiahnuť všetci prihlásení používatelia Backalor. Stiahnuté kópie zostanú používateľom aj po odobratí prístupu.'),
 'save':('Зберегти назву й видимість','Uložiť názov a viditeľnosť'),
 'email':('Email користувача Google','Email používateľa Google'),
 'reader':('Читання','Čítanie'),'editor':('Редагування серверної копії','Úprava serverovej kópie'),
 'invite':('Надати / змінити доступ','Udeliť / zmeniť prístup'),
 'revoke':('Відкликати доступ','Odobrať prístup'),
 'refresh':('Оновити','Obnoviť'),'role':('Права','Oprávnenia'),
 'busy':('Виконується запит…','Spracúva sa požiadavka…'),
 'saved':('Доступ оновлено.','Prístup aktualizovaný.'),
 'invite_help':('Учасник має спочатку увійти в Backalor зі своїм Google-акаунтом. Редактор може оновлювати серверний ZIP; керувати доступом і видаляти документ може лише власник.','Účastník sa musí najprv prihlásiť do Backalor účtom Google. Editor môže aktualizovať serverový ZIP; spravovať prístup a odstrániť dokument môže iba vlastník.'),
 'wait':('Дочекайся завершення запиту.','Počkaj na dokončenie požiadavky.'),
 'owner':('Керувати доступом може лише власник.','Prístup môže spravovať iba vlastník.'),
}


class SharingDialog(QtWidgets.QDialog):
    def __init__(self, client, project, language='uk', parent=None):
        super().__init__(parent)
        self.client=client;self.project=dict(project);self.language=language;self.worker=None;self.result=None;self.failure=None
        self.setWindowTitle(self.t('title'));self.resize(740,680);self.setMinimumSize(660,620)
        layout=QtWidgets.QVBoxLayout(self);layout.setSpacing(12)
        form=QtWidgets.QFormLayout();self.name=QtWidgets.QLineEdit(project['title']);self.name.setMaxLength(200)
        self.description=QtWidgets.QPlainTextEdit(project.get('description',''));self.description.setMaximumHeight(80)
        self.visibility=QtWidgets.QComboBox()
        for value in ('private','public'):self.visibility.addItem(self.t(value),value)
        self.visibility.setCurrentIndex(self.visibility.findData(project.get('visibility','private')))
        form.addRow(self.t('name'),self.name);form.addRow(self.t('description'),self.description);form.addRow(self.t('visibility'),self.visibility);layout.addLayout(form)
        help_label=QtWidgets.QLabel(self.t('help'));help_label.setWordWrap(True);help_label.setObjectName('mutedLabel');layout.addWidget(help_label)
        self.save=QtWidgets.QPushButton(self.t('save'));self.save.clicked.connect(self.save_metadata);layout.addWidget(self.save)
        invite_help=QtWidgets.QLabel(self.t('invite_help'));invite_help.setWordWrap(True);layout.addWidget(invite_help)
        invite_row=QtWidgets.QHBoxLayout();self.email=QtWidgets.QLineEdit();self.email.setPlaceholderText(self.t('email'));self.email.setAccessibleName(self.t('email'));self.email.setMaxLength(320)
        self.role=QtWidgets.QComboBox()
        for value in ('reader','editor'):self.role.addItem(self.t(value),value)
        self.role.setAccessibleName(self.t('role'))
        self.invite=QtWidgets.QPushButton(self.t('invite'));self.invite.clicked.connect(self.grant)
        invite_row.addWidget(self.email,1);invite_row.addWidget(self.role);invite_row.addWidget(self.invite);layout.addLayout(invite_row)
        self.table=QtWidgets.QTableWidget(0,2);self.table.setHorizontalHeaderLabels([self.t('email'),self.t('role')]);self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.controls);layout.addWidget(self.table,1)
        row=QtWidgets.QHBoxLayout();self.revoke=QtWidgets.QPushButton(self.t('revoke'));self.revoke.clicked.connect(self.remove)
        self.refresh=QtWidgets.QPushButton(self.t('refresh'));self.refresh.clicked.connect(self.load)
        row.addWidget(self.revoke);row.addStretch();row.addWidget(self.refresh);layout.addLayout(row)
        self.status=QtWidgets.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.controls()
        if project.get('access_role','owner')=='owner':self.load()
        else:self.status.setText(self.t('owner'))

    def t(self,key):return COPY[key][0 if self.language=='uk' else 1]
    def controls(self):
        enabled=self.worker is None and self.project.get('access_role','owner')=='owner'
        for widget in (self.name,self.description,self.visibility,self.save,self.email,self.role,self.invite,self.refresh,self.table):widget.setEnabled(enabled)
        self.revoke.setEnabled(enabled and self.table.currentRow()>=0)
    def perform(self,operation,completed):
        if self.worker is not None:return
        self.result=None;self.failure=None;self.worker=Task(operation,self)
        self.worker.succeeded.connect(lambda result:setattr(self,'result',result));self.worker.failed.connect(lambda error:setattr(self,'failure',error))
        self.worker.finished.connect(lambda:self.finished(completed));self.status.setText(self.t('busy'));self.controls();self.worker.start()
    def finished(self,completed):
        worker=self.worker;self.worker=None;worker.deleteLater()
        if self.failure:self.status.setText(self.failure)
        else:
            try:completed(self.result)
            except Exception as exc:self.status.setText(str(exc))
        self.controls()
    def load(self):self.perform(lambda:self.client.shares(self.project),self.populate)
    def populate(self,shares):
        self.table.setRowCount(0)
        for row,share in enumerate(shares):
            self.table.insertRow(row);item=QtWidgets.QTableWidgetItem(share['email']);item.setData(QtCore.Qt.ItemDataRole.UserRole,share['user_id']);self.table.setItem(row,0,item)
            self.table.setItem(row,1,QtWidgets.QTableWidgetItem(self.t(share['role'])))
        self.status.setText(self.t('saved'))
    def save_metadata(self):
        name=self.name.text().strip();description=self.description.toPlainText();visibility=self.visibility.currentData()
        if not name:return
        def completed(project):self.project=project;self.status.setText(self.t('saved'))
        self.perform(lambda:self.client.update_project(self.project,name,description,visibility),completed)
    def grant(self):
        email=self.email.text().strip();role=self.role.currentData()
        if not email:return
        self.perform(lambda:self.client.share(self.project,email,role),lambda _:self.load())
    def remove(self):
        row=self.table.currentRow()
        if row<0:return
        identifier=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        self.perform(lambda:self.client.revoke_share(self.project,identifier),lambda _:self.load())
    def reject(self):
        if self.worker:self.status.setText(self.t('wait'));return
        super().reject()
    def closeEvent(self,event):
        if self.worker:self.status.setText(self.t('wait'));event.ignore()
        else:event.accept()
