from __future__ import annotations
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from PyQt6 import QtCore,QtGui,QtWidgets
from .api_client import ApiClient,normalize_server_url
from .jobs import Task
from .datasets import export_bundle,import_bundle

COPY={
 'access':('Доступ і учасники…','Prístup a účastníci…'),
 'account':('Обліковий запис і сервер','Účet a server'), 'server':('Адреса сервера','Adresa servera'),
 'connect':('Перевірити сервер','Skontrolovať server'), 'login':('Увійти через Google','Prihlásiť cez Google'),
 'logout':('Вийти','Odhlásiť'), 'cancel':('Скасувати вхід','Zrušiť prihlásenie'),
 'refresh':('Оновити список','Obnoviť zoznam'), 'new':('Зберегти як новий проєкт','Uložiť ako nový projekt'),
 'update':('Оновити вибрану копію','Aktualizovať vybranú kópiu'), 'download':('Відкрити локальну копію…','Otvoriť lokálnu kópiu…'),
 'offline':('Вхід не виконано. Локальні проєкти доступні без облікового запису.','Nie si prihlásený. Lokálne projekty fungujú aj bez účtu.'),
 'help':('Вхід відкривається в системному браузері. Сесія діє в цьому запуску програми. Серверні копії включають скани та анотації; обмін запускається вручну.','Prihlásenie sa otvorí v systémovom prehliadači. Relácia platí počas tohto spustenia. Serverové kópie obsahujú skeny a anotácie; prenos sa spúšťa ručne.'),
 'waiting':('Заверши вхід у браузері…','Dokonči prihlásenie v prehliadači…'),
 'busy':('Виконується запит…','Prebieha požiadavka…'),
 'empty':('На сервері ще немає проєктів. Збережи поточний як новий.','Na serveri ešte nie sú projekty. Ulož aktuálny ako nový.'),
 'projects':('Мої проєкти на сервері','Moje projekty na serveri'),
 'choose':('Обери порожню папку для копії проєкту','Vyber prázdny priečinok pre kópiu projektu'),
 'overwrite':('Оновити серверну копію вибраного проєкту даними поточного локального проєкту?','Aktualizovať vybranú serverovú kópiu údajmi aktuálneho lokálneho projektu?'),
 'wait_close':('Дочекайся завершення запиту.','Počkaj na dokončenie požiadavky.'),
 'failed':('Вхід скасовано або не вдався. Спробуй ще раз.','Prihlásenie bolo zrušené alebo zlyhalo. Skús znova.'),
 'expired':('Час входу минув. Спробуй ще раз.','Čas prihlásenia vypršal. Skús znova.'),
 'ready':('Сервер доступний.','Server je dostupný.'),
 'config':('Сервер доступний, але Google OAuth ще не налаштований. Дивись DEPLOYMENT.md.','Server je dostupný, ale Google OAuth ešte nie je nastavený. Pozri DEPLOYMENT.md.'),
 'saved':('Копію збережено на сервері.','Kópia bola uložená na serveri.'),
 'title':('Назва проєкту','Názov projektu'), 'version':('Версія','Verzia'),
}


class AccountDialog(QtWidgets.QDialog):
    def __init__(self,workspace):
        super().__init__(workspace)
        self.workspace=workspace;self.client=workspace.api_client
        self.worker=None;self.flow=None;self.result=None;self.failure=None
        self.setWindowTitle(self.t('account'));self.resize(740,570);self.setMinimumSize(620,480)
        layout=QtWidgets.QVBoxLayout(self);layout.setSpacing(12)
        form=QtWidgets.QFormLayout();self.server=QtWidgets.QLineEdit(self.client.base_url)
        form.addRow(self.t('server'),self.server);layout.addLayout(form)
        actions=QtWidgets.QHBoxLayout();self.connect_button=QtWidgets.QPushButton(self.t('connect'))
        self.login_button=QtWidgets.QPushButton(self.t('login'));self.login_button.setProperty('primary',True)
        self.logout_button=QtWidgets.QPushButton(self.t('logout'));self.cancel_button=QtWidgets.QPushButton(self.t('cancel'))
        for button in (self.connect_button,self.login_button,self.logout_button,self.cancel_button):actions.addWidget(button)
        layout.addLayout(actions)
        self.status=QtWidgets.QLabel();self.status.setWordWrap(True);self.status.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        help_label=QtWidgets.QLabel(self.t('help'));help_label.setWordWrap(True);help_label.setObjectName('mutedLabel');layout.addWidget(help_label)
        title_row=QtWidgets.QHBoxLayout();title=QtWidgets.QLabel(self.t('projects'));title.setObjectName('panelTitle')
        title_row.addWidget(title);title_row.addStretch();self.refresh_button=QtWidgets.QPushButton(self.t('refresh'));title_row.addWidget(self.refresh_button);layout.addLayout(title_row)
        self.table=QtWidgets.QTableWidget(0,2);self.table.setHorizontalHeaderLabels([self.t('title'),self.t('version')])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide();layout.addWidget(self.table,1)
        bottom=QtWidgets.QHBoxLayout();self.new_button=QtWidgets.QPushButton(self.t('new'))
        self.update_button=QtWidgets.QPushButton(self.t('update'));self.download_button=QtWidgets.QPushButton(self.t('download'))
        for button in (self.new_button,self.update_button,self.download_button):bottom.addWidget(button)
        layout.addLayout(bottom)
        self.connect_button.clicked.connect(self.check_server);self.login_button.clicked.connect(self.login)
        self.logout_button.clicked.connect(self.logout);self.cancel_button.clicked.connect(self.cancel_login)
        self.refresh_button.clicked.connect(self.refresh);self.new_button.clicked.connect(lambda:self.upload(True))
        self.update_button.clicked.connect(lambda:self.upload(False));self.download_button.clicked.connect(self.download)
        self.table.itemSelectionChanged.connect(self.controls)
        self.access_button=QtWidgets.QPushButton(self.t('access'))
        self.access_button.clicked.connect(self.manage_access);layout.addWidget(self.access_button)
        self.table.itemSelectionChanged.connect(self.controls)
        self.poll_timer=QtCore.QTimer(self);self.poll_timer.setInterval(2000);self.poll_timer.timeout.connect(self.poll)
        self.show_identity();self.controls()
        if self.client.token:self.refresh()
        if getattr(workspace,'session_controller',None) is not None:
            for widget in (self.server,form.labelForField(self.server),self.connect_button,self.login_button,self.cancel_button):widget.hide()

    def t(self,key):return COPY[key][0 if self.workspace.language=='uk' else 1]
    def selected(self):
        row=self.table.currentRow()
        return self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole) if row>=0 else None
    def controls(self):
        idle=self.worker is None;logged=bool(self.client.token);waiting=self.flow is not None
        self.server.setEnabled(idle and not logged and not waiting)
        self.connect_button.setEnabled(idle and not waiting)
        self.login_button.setEnabled(idle and not logged and not waiting)
        self.logout_button.setEnabled(idle and logged)
        self.cancel_button.setVisible(waiting);self.cancel_button.setEnabled(idle)
        for button in (self.refresh_button,self.new_button):button.setEnabled(idle and logged and not waiting)
        selected=self.selected()
        self.update_button.setEnabled(idle and logged and bool(selected and selected.get('access_role','owner') in ('owner','editor')))
        self.access_button.setEnabled(idle and logged and bool(selected and selected.get('access_role','owner')=='owner'))
        self.download_button.setEnabled(idle and logged and bool(selected and selected['has_snapshot']))
        self.table.setEnabled(idle and logged)
    def show_identity(self):
        profile=self.client.profile
        self.status.setText(f"{profile['name']} · {profile['email']}" if profile else self.t('offline'))
        self.workspace.account_action.setText(self.t('account')+(f" · {profile['name']}" if profile else ''))
    def operation(self,fn,done):
        if self.worker:return
        self.failure=None;self.result=None;self.worker=Task(fn,self)
        self.worker.succeeded.connect(lambda value:setattr(self,'result',value))
        self.worker.failed.connect(lambda error:setattr(self,'failure',error))
        self.worker.finished.connect(lambda:self.finished_operation(done))
        self.status.setText(self.t('busy'));self.controls();self.worker.start()
    def finished_operation(self,done):
        worker=self.worker;self.worker=None;worker.deleteLater()
        if self.failure:
            self.show_identity()
            self.status.setText(self.failure)
            if self.flow:self.poll_timer.stop();self.flow=None
        else:
            try:done(self.result)
            except Exception as exc:self.status.setText(str(exc))
        self.controls()
    def apply_server(self):
        try:value=normalize_server_url(self.server.text())
        except ValueError as exc:self.status.setText(str(exc));return False
        if value!=self.client.base_url:
            if self.client.token:return False
            self.client=ApiClient(value);self.workspace.api_client=self.client
        QtCore.QSettings('Backalor','Desktop').setValue('backend_url',value)
        return True
    def check_server(self):
        if self.apply_server():self.operation(lambda:self.client.json('GET','/health'),lambda data:self.status.setText(self.t('ready' if data['google_configured'] else 'config')))
    def login(self):
        if not self.apply_server():return
        def ready(flow):
            url=QtCore.QUrl(flow['authorization_url'])
            if url.scheme()!='https' or url.host()!='accounts.google.com':raise ValueError('Invalid Google authorization URL')
            self.flow=flow;self.deadline=time.monotonic()+flow['expires_in']
            if not QtGui.QDesktopServices.openUrl(url):
                self.flow=None;raise RuntimeError('Cannot open the system browser')
            self.status.setText(self.t('waiting'));self.poll_timer.start()
        self.operation(self.client.start_login,ready)
    def poll(self):
        if self.worker or not self.flow:return
        if time.monotonic()>=self.deadline:
            self.poll_timer.stop();self.flow=None;self.status.setText(self.t('expired'));self.controls();return
        def completed(data):
            if data['status']=='authenticated':
                self.flow=None;self.poll_timer.stop();self.show_identity();self.refresh()
            elif data['status']=='failed':
                self.flow=None;self.poll_timer.stop();self.status.setText(self.t('failed'))
            else:self.status.setText(self.t('waiting'))
        flow=self.flow.copy();self.operation(lambda:self.client.poll_login(flow),completed)
    def cancel_login(self):
        flow=self.flow;self.flow=None;self.poll_timer.stop()
        if flow:self.operation(lambda:self.client.cancel_login(flow),lambda _:self.show_identity())
    def logout(self):
        if getattr(self.workspace,'session_controller',None) is not None:
            self.accept();self.workspace.session_controller.sign_out();return
        def done(_):self.table.setRowCount(0);self.show_identity()
        self.operation(self.client.logout,done)
    def refresh(self):
        def done(projects):
            self.table.setRowCount(0)
            for project in projects:
                row=self.table.rowCount();self.table.insertRow(row)
                item=QtWidgets.QTableWidgetItem(project['title']);item.setData(QtCore.Qt.ItemDataRole.UserRole,project)
                self.table.setItem(row,0,item);self.table.setItem(row,1,QtWidgets.QTableWidgetItem(str(project['version'])))
            self.show_identity()
            if not projects:self.status.setText(self.t('empty'))
        self.operation(lambda:self.client.projects(scope='all'),done)
    def manage_access(self):
        from .sharing_ui import SharingDialog
        project=self.selected()
        if project is None:return
        dialog=SharingDialog(self.client,project,self.workspace.language,self)
        dialog.exec();self.refresh()
    def upload(self,new):
        try:
            if self.workspace.save_annotations_current(silent=True) is False:return
        except Exception as exc:self.status.setText(str(exc));return
        root=self.workspace.root;project=None if new else self.selected()
        if not new and (not project or QtWidgets.QMessageBox.question(self,self.t('update'),self.t('overwrite'))!=QtWidgets.QMessageBox.StandardButton.Yes):return
        def transfer():
            with tempfile.TemporaryDirectory() as folder:
                archive=Path(folder)/'project.zip';export_bundle(root,archive)
                metadata=root/'project.json';data=json.loads(metadata.read_text()) if metadata.exists() else {}
                target=project or self.client.create_project(data.get('title') or root.name,data.get('description',''))
                return self.client.upload(target,archive)
        def done(_):self.status.setText(self.t('saved'));self.refresh()
        self.operation(transfer,done)
    def download(self):
        project=self.selected()
        if not project:return
        directory=QtWidgets.QFileDialog.getExistingDirectory(self,self.t('choose'),str(self.workspace.root.parent))
        if not directory:return
        target=Path(directory)
        if any(target.iterdir()):self.status.setText(self.t('choose'));return
        try:
            if self.workspace.save_annotations_current(silent=True) is False:return
        except Exception as exc:self.status.setText(str(exc));return
        def transfer():
            with tempfile.TemporaryDirectory() as folder:
                archive=Path(folder)/'project.zip';self.client.download(project,archive);import_bundle(archive,target)
            return target
        def done(path):self.workspace.switch_project(path);self.show_identity()
        self.operation(transfer,done)
    def reject(self):
        if self.worker:self.status.setText(self.t('wait_close'));return
        if self.flow:self.cancel_login();return
        super().reject()
    def closeEvent(self,event):
        if self.worker or self.flow:
            self.status.setText(self.t('wait_close'));event.ignore();return
        self.poll_timer.stop();event.accept()
