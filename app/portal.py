"""Authenticated application entry and projects hub.
THESIS: researcher work begins with a verified identity and a chosen project.
OWN-WORLD: charcoal navigation, warm white surfaces, forest-green actions.
STORY: start API → Google sign-in → choose/create/download → annotate → review.
FIRST VIEWPORT: quiet dark identity panel and a focused light sign-in form.
FORM: native code-led research workbench; direction seed a66aa05c, candidate 6.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
"""
from __future__ import annotations
import json
import tempfile
import time
from pathlib import Path
from PyQt6 import QtCore,QtGui,QtWidgets
from .api_client import ApiClient,ApiError
from .backend_runtime import BackendRuntime
from .jobs import Task
from .project import ensure_project_structure
from .project_registry import ProjectRegistry
from .datasets import import_bundle
from .storage import atomic_write
from .session_store import SecureSessionStore,SessionStoreError

COPY={
 'welcome':('Робочий простір\nдля історичних шифрів','Pracovný priestor\npre historické šifry'),
 'brand_detail':('Від скану до структури, символів і перевіреного ключа.','Od skenu k štruktúre, symbolom a overenému kľúču.'),
 'sign_in':('Увійди, щоб почати','Prihlás sa a začni'),
 'sign_detail':('Продовж із Google. Якщо ти тут уперше, обліковий запис створиться автоматично.','Pokračuj cez Google. Ak si tu prvýkrát, účet sa vytvorí automaticky.'),
 'google':('Продовжити з Google','Pokračovať cez Google'),
 'remember':('Запам’ятати вхід на цьому комп’ютері','Zapamätať prihlásenie na tomto počítači'),
 'remember_help':('Сесію збережемо в захищеному сховищі системи. Після запуску перевіримо її на сервері.','Reláciu uložíme do zabezpečeného úložiska systému. Pri spustení ju overíme na serveri.'),
 'restoring':('Перевіряємо збережений вхід…','Overujeme uložené prihlásenie…'),
 'cloud_setup':('Вкажи BACKALOR_API_URL з HTTPS-адресою хмарного API. Локальний сервер і база вимкнені. Інструкція: CLOUD.md.','Nastav BACKALOR_API_URL na HTTPS adresu cloudového API. Lokálny server a databáza sú vypnuté. Návod: CLOUD.md.'),
 'restore_unavailable':('Не вдалося прочитати збережений вхід. Продовж із Google.','Uložené prihlásenie sa nepodarilo prečítať. Pokračuj cez Google.'),
 'restore_expired':('Збережений вхід закінчився. Продовж із Google.','Uložené prihlásenie vypršalo. Pokračuj cez Google.'),
 'remember_failed':('Вхід виконано, але зберегти його не вдалося. Наступного разу увійди через Google.','Prihlásenie prebehlo, ale nepodarilo sa ho uložiť. Nabudúce sa prihlás cez Google.'),
 'browser':('Вхід відкриється у твоєму браузері. Пароль Google програма не запитує.','Prihlásenie sa otvorí v tvojom prehliadači. Aplikácia nežiada heslo Google.'),
 'starting':('Запускаємо робочий простір…','Spúšťame pracovný priestor…'),
 'ready':('Усе готово. Увійди через Google.','Všetko je pripravené. Prihlás sa cez Google.'),
 'waiting':('Заверши вхід у браузері й повернися сюди.','Dokonči prihlásenie v prehliadači a vráť sa sem.'),
 'retry':('Спробувати знову','Skúsiť znova'),'cancel':('Скасувати вхід','Zrušiť prihlásenie'),
 'config':('Google-вхід ще не налаштований на сервері. Вкажи там GOOGLE_CLIENT_ID і GOOGLE_CLIENT_SECRET та перезапусти API.','Prihlásenie Google ešte nie je nastavené na serveri. Nastav tam GOOGLE_CLIENT_ID a GOOGLE_CLIENT_SECRET a reštartuj API.'),
 'failed':('Вхід не завершено. Спробуй ще раз.','Prihlásenie nebolo dokončené. Skús znova.'),
 'expired':('Час входу минув. Спробуй ще раз.','Čas prihlásenia vypršal. Skús znova.'),
 'busy':('Виконуємо запит…','Spracúvame požiadavku…'),
 'close_wait':('Завершуємо поточний запит…','Dokončujeme aktuálnu požiadavku…'),
 'public':('Публічні','Verejné'),'shared':('Спільні','Zdieľané'),'all_docs':('Усі доступні','Všetky dostupné'),
 'search':('Пошук за назвою або описом…','Hľadať podľa názvu alebo popisu…'),
 'any_visibility':('Будь-яка видимість','Každá viditeľnosť'),'private':('Приватні','Súkromné'),
 'any_snapshot':('Усі документи','Všetky dokumenty'),'with_snapshot':('Зі сканами','So skenmi'),'without_snapshot':('Без сканів','Bez skenov'),
 'updated':('Нещодавно змінені','Naposledy zmenené'),'by_title':('За назвою','Podľa názvu'),
 'previous_page':('Попередні','Predchádzajúce'),'next_page':('Наступні','Ďalšie'),
 'access':('Доступ і учасники…','Prístup a účastníci…'),
 'projects':('Проєкти','Projekty'),'hub_detail':('Відкрий знайомий документ або почни нове дослідження.','Otvor známy dokument alebo začni nový výskum.'),
 'new':('Новий проєкт','Nový projekt'),'open':('Відкрити папку…','Otvoriť priečinok…'),
 'local':('На цьому комп’ютері','Na tomto počítači'),'cloud':('Серверні копії','Serverové kópie'),
 'title':('Назва','Názov'),'location':('Розташування / версія','Umiestnenie / verzia'),
 'open_selected':('Відкрити вибраний','Otvoriť vybraný'),'download':('Завантажити й відкрити…','Stiahnuť a otvoriť…'),
 'refresh':('Оновити','Obnoviť'),'logout':('Вийти','Odhlásiť sa'),
 'empty_local':('Тут з’являться твої відкриті проєкти. Створи новий або відкрий наявну папку.','Tu sa zobrazia tvoje otvorené projekty. Vytvor nový alebo otvor existujúci priečinok.'),
 'empty_cloud':('На сервері поки немає копій. Збережи проєкт із редактора, щоб відкрити його тут.','Na serveri zatiaľ nie sú kópie. Ulož projekt z editora a otvor ho tu.'),
 'choose_empty':('Обери порожню папку проєкту','Vyber prázdny priečinok projektu'),
 'not_empty':('Потрібна порожня папка. Наявні файли не змінено.','Je potrebný prázdny priečinok. Existujúce súbory neboli zmenené.'),
 'name_prompt':('Як назвати проєкт?','Ako sa má projekt volať?'),
 'session_expired':('Сесія завершилася. Увійди знову — незбережені зміни залишилися в пам’яті та чернетці.','Relácia sa skončila. Prihlás sa znova — neuložené zmeny zostali v pamäti a koncepte.'),
 'offline':('Не вдалося перевірити сесію. Віднови з’єднання та спробуй знову.','Reláciu sa nepodarilo overiť. Obnov pripojenie a skús znova.'),
 'different_account':('Попередній редактор ще виконує задачу. Дочекайся завершення.','Predchádzajúci editor ešte spracúva úlohu. Počkaj na dokončenie.'),
 'backend_status':('Сервіс працює','Služba je pripravená'),
}


class PortalWindow(QtWidgets.QMainWindow):
    auth_expired=QtCore.pyqtSignal()

    def __init__(self,initial_project=None,runtime=None,client=None,state_dir=None,language='uk',autostart=True,session_store=None):
        super().__init__();self.setWindowTitle('Backalor');self.resize(1120,760);self.setMinimumSize(860,620)
        self.language=language;self.runtime=runtime or BackendRuntime(allow_local=False);self.client=client or ApiClient()
        self.auth_expired.connect(self._auth_expired);self.client.on_auth_expired=self.auth_expired.emit
        self.initial_project=Path(initial_project).resolve() if initial_project else None
        self.state_dir=Path(state_dir or QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation))/'accounts'
        self.session_store=session_store or SecureSessionStore(self.state_dir/'sessions')
        self.worker=None;self.result=None;self.failure=None;self.flow=None;self.deadline=0;self.configured=False
        self.workspace=None;self.workspace_user=None;self.registry=None;self._pending_close=False;self._closing_editor=False;self._locked=False
        self.poll_timer=QtCore.QTimer(self);self.poll_timer.setInterval(1500);self.poll_timer.timeout.connect(self.poll_login)
        self.session_timer=QtCore.QTimer(self);self.session_timer.setInterval(30000);self.session_timer.timeout.connect(self.verify_session)
        self.stack=QtWidgets.QStackedWidget();self.setCentralWidget(self.stack)
        self._build_login();self._build_hub();self.stack.setCurrentIndex(0)
        if autostart:QtCore.QTimer.singleShot(0,self.bootstrap)
    def t(self,key):return COPY[key][0 if self.language=='uk' else 1]
    def guard(self,callback):
        try:return callback()
        except Exception as exc:self.show_error(str(exc))
    def _build_login(self):
        page=QtWidgets.QWidget();outer=QtWidgets.QHBoxLayout(page);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.brand=QtWidgets.QFrame();self.brand.setObjectName('loginBrand');left=QtWidgets.QVBoxLayout(self.brand);left.setContentsMargins(42,42,42,42)
        logo=QtWidgets.QLabel('BACKALOR');logo.setObjectName('brandWordmark');left.addWidget(logo);left.addStretch(2)
        title=QtWidgets.QLabel(self.t('welcome'));title.setObjectName('loginHero');title.setWordWrap(True);left.addWidget(title)
        detail=QtWidgets.QLabel(self.t('brand_detail'));detail.setObjectName('brandMuted');detail.setWordWrap(True);left.addWidget(detail);left.addStretch(3)
        footer=QtWidgets.QLabel('L1 · L2 · L3');footer.setObjectName('brandMuted');left.addWidget(footer)
        self.brand.setMinimumWidth(300);self.brand.setMaximumWidth(460);outer.addWidget(self.brand,4)
        form_panel=QtWidgets.QWidget();form=QtWidgets.QVBoxLayout(form_panel);form.setContentsMargins(48,40,48,40);form.addStretch(2)
        heading=QtWidgets.QLabel(self.t('sign_in'));heading.setObjectName('screenTitle');heading.setWordWrap(True);form.addWidget(heading)
        text=QtWidgets.QLabel(self.t('sign_detail'));text.setWordWrap(True);text.setObjectName('secondaryText');form.addWidget(text);form.addSpacing(26)
        self.google_button=QtWidgets.QPushButton(self.t('google'));self.google_button.setObjectName('googleButton');self.google_button.setMinimumHeight(48);self.google_button.setEnabled(False)
        self.google_button.clicked.connect(lambda:self.guard(self.start_login));form.addWidget(self.google_button)
        self.remember=QtWidgets.QCheckBox(self.t('remember'));self.remember.setChecked(True);form.addWidget(self.remember)
        remember_help=QtWidgets.QLabel(self.t('remember_help'));remember_help.setWordWrap(True);remember_help.setObjectName('secondaryText');form.addWidget(remember_help)
        browser=QtWidgets.QLabel(self.t('browser'));browser.setObjectName('secondaryText');browser.setWordWrap(True);form.addWidget(browser);form.addSpacing(22)
        self.login_status=QtWidgets.QLabel(self.t('starting'));self.login_status.setWordWrap(True);form.addWidget(self.login_status)
        self.progress=QtWidgets.QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(4);form.addWidget(self.progress)
        actions=QtWidgets.QHBoxLayout();self.retry_button=QtWidgets.QPushButton(self.t('retry'));self.retry_button.clicked.connect(lambda:self.guard(self.bootstrap));self.retry_button.hide()
        self.cancel_button=QtWidgets.QPushButton(self.t('cancel'));self.cancel_button.clicked.connect(lambda:self.guard(self.cancel_login));self.cancel_button.hide();actions.addWidget(self.retry_button);actions.addWidget(self.cancel_button);actions.addStretch();form.addLayout(actions)
        form.addStretch(3);outer.addWidget(form_panel,6);self.stack.addWidget(page)
    def _build_hub(self):
        page=QtWidgets.QWidget();outer=QtWidgets.QHBoxLayout(page);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        rail=QtWidgets.QFrame();rail.setObjectName('navigationRail');rail.setFixedWidth(220);left=QtWidgets.QVBoxLayout(rail);left.setContentsMargins(22,30,22,24)
        brand=QtWidgets.QLabel('BACKALOR');brand.setObjectName('brandWordmark');left.addWidget(brand);left.addSpacing(42)
        active=QtWidgets.QPushButton(self.t('projects'));active.setObjectName('railActive');left.addWidget(active);left.addStretch()
        self.profile_label=QtWidgets.QLabel();self.profile_label.setWordWrap(True);self.profile_label.setObjectName('brandMuted');left.addWidget(self.profile_label)
        self.logout_button=QtWidgets.QPushButton(self.t('logout'));self.logout_button.setObjectName('railButton');self.logout_button.clicked.connect(lambda:self.guard(self.sign_out));left.addWidget(self.logout_button);outer.addWidget(rail)
        body=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(body);layout.setContentsMargins(34,30,34,28);layout.setSpacing(16)
        heading=QtWidgets.QLabel(self.t('projects'));heading.setObjectName('screenTitle');layout.addWidget(heading)
        detail=QtWidgets.QLabel(self.t('hub_detail'));detail.setObjectName('secondaryText');detail.setWordWrap(True);layout.addWidget(detail)
        self.session_notice=QtWidgets.QLabel();self.session_notice.setWordWrap(True);self.session_notice.hide();layout.addWidget(self.session_notice)
        row=QtWidgets.QHBoxLayout();self.new_button=QtWidgets.QPushButton(self.t('new'));self.new_button.setProperty('primary',True);self.new_button.clicked.connect(lambda:self.guard(self.new_project))
        self.open_button=QtWidgets.QPushButton(self.t('open'));self.open_button.clicked.connect(lambda:self.guard(self.open_local))
        row.addWidget(self.new_button);row.addWidget(self.open_button);row.addStretch();self.refresh_button=QtWidgets.QPushButton(self.t('refresh'));self.refresh_button.clicked.connect(lambda:self.guard(self.refresh_projects));row.addWidget(self.refresh_button);layout.addLayout(row)
        self.source_tabs=QtWidgets.QTabBar();self.source_tabs.addTab(self.t('local'));self.source_tabs.addTab(self.t('cloud'));self.source_tabs.addTab(self.t('public'));self.source_tabs.addTab(self.t('shared'));self.source_tabs.addTab(self.t('all_docs'))
        self.source_tabs.currentChanged.connect(self.reset_filters);layout.addWidget(self.source_tabs)
        self.document_offset=0;self.document_has_next=False
        filters=QtWidgets.QHBoxLayout();self.document_search=QtWidgets.QLineEdit();self.document_search.setPlaceholderText(self.t('search'));self.document_search.setAccessibleName(self.t('search'))
        self.document_search.returnPressed.connect(self.reset_filters);layout.addWidget(self.document_search)
        self.search_timer=QtCore.QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.reset_filters);self.document_search.textChanged.connect(lambda:self.search_timer.start())
        self.visibility_filter=QtWidgets.QComboBox()
        for key,value in [('any_visibility',''),('private','private'),('public','public')]:self.visibility_filter.addItem(self.t(key),value)
        self.snapshot_filter=QtWidgets.QComboBox()
        for key,value in [('any_snapshot',None),('with_snapshot',True),('without_snapshot',False)]:self.snapshot_filter.addItem(self.t(key),value)
        self.sort_filter=QtWidgets.QComboBox()
        for key,value in [('updated','updated'),('by_title','title')]:self.sort_filter.addItem(self.t(key),value)
        self.visibility_filter.setAccessibleName(self.t('any_visibility'));self.snapshot_filter.setAccessibleName(self.t('any_snapshot'));self.sort_filter.setAccessibleName(self.t('updated'))
        for field in (self.visibility_filter,self.snapshot_filter,self.sort_filter):
            field.currentIndexChanged.connect(self.reset_filters);filters.addWidget(field)
        layout.addLayout(filters)
        pager=QtWidgets.QHBoxLayout();self.previous_page=QtWidgets.QPushButton(self.t('previous_page'));self.next_page=QtWidgets.QPushButton(self.t('next_page'))
        self.previous_page.clicked.connect(lambda:self.change_page(-1));self.next_page.clicked.connect(lambda:self.change_page(1))
        self.access_button=QtWidgets.QPushButton(self.t('access'));self.access_button.clicked.connect(lambda:self.guard(self.manage_access))
        pager.addWidget(self.previous_page);pager.addWidget(self.next_page);pager.addStretch();pager.addWidget(self.access_button);layout.addLayout(pager)
        self.table=QtWidgets.QTableWidget(0,2);self.table.setHorizontalHeaderLabels([self.t('title'),self.t('location')]);self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_:self.guard(self.open_selected));self.table.itemSelectionChanged.connect(self.controls);layout.addWidget(self.table,1)
        self.hub_status=QtWidgets.QLabel();self.hub_status.setWordWrap(True);self.hub_status.setObjectName('secondaryText');layout.addWidget(self.hub_status)
        footer=QtWidgets.QHBoxLayout();self.service_label=QtWidgets.QLabel(self.t('backend_status'));self.service_label.setObjectName('serviceReady');footer.addWidget(self.service_label);footer.addStretch()
        self.selected_button=QtWidgets.QPushButton(self.t('open_selected'));self.selected_button.setProperty('primary',True);self.selected_button.clicked.connect(lambda:self.guard(self.open_selected));footer.addWidget(self.selected_button);layout.addLayout(footer)
        outer.addWidget(body,1);self.stack.addWidget(page)
    def controls(self):
        idle=self.worker is None;logged=bool(self.client.token and self.client.profile)
        self.google_button.setEnabled(idle and self.configured and self.flow is None)
        self.remember.setEnabled(idle and self.flow is None)
        self.retry_button.setEnabled(idle);self.cancel_button.setVisible(self.flow is not None);self.cancel_button.setEnabled(idle)
        self.progress.setVisible(not idle)
        for button in (self.new_button,self.open_button,self.refresh_button,self.logout_button):button.setEnabled(idle and logged)
        self.source_tabs.setEnabled(idle and logged);self.table.setEnabled(idle and logged)
        selected=self.table.item(self.table.currentRow(),0) if self.table.currentRow()>=0 else None
        record=selected.data(QtCore.Qt.ItemDataRole.UserRole) if selected else None
        cloud=self.source_tabs.currentIndex()!=0
        self.selected_button.setEnabled(idle and logged and bool(record) and (not cloud or record.get('has_snapshot',False)))
        self.access_button.setEnabled(idle and logged and cloud and bool(record and record.get('access_role','owner')=='owner'))
        self.document_search.setEnabled(idle and logged)
        for field in (self.visibility_filter,self.snapshot_filter,self.sort_filter):field.setEnabled(idle and logged and cloud)
        self.previous_page.setEnabled(idle and logged and cloud and self.document_offset>0)
        self.next_page.setEnabled(idle and logged and cloud and self.document_has_next)
    def perform(self,operation,completed,error=None):
        if self.worker is not None:return False
        self.result=None;self.failure=None;self.worker=Task(operation,self)
        self.worker.succeeded.connect(lambda value:setattr(self,'result',value));self.worker.failed.connect(lambda value:setattr(self,'failure',value))
        self.worker.finished.connect(lambda:self.finished(completed,error));self.controls();self.worker.start();return True
    def finished(self,completed,error):
        worker=self.worker;self.worker=None;worker.deleteLater()
        if self._pending_close:self._finish_close();return
        if self.failure:
            if error:error(self.failure)
            else:self.show_error(self.failure)
        else:
            try:completed(self.result)
            except Exception as exc:self.show_error(str(exc))
        self.controls()
    def show_error(self,message):
        (self.login_status if self.stack.currentIndex()==0 else self.hub_status).setText(message)
        if self.workspace is not None and self.workspace.isVisible():self.workspace.statusBar().showMessage(message)
        self.retry_button.show()
        if not self.client.token and self.stack.currentIndex()==1:self.lock(self.t('session_expired'))
    def bootstrap(self):
        if self.worker is not None:return
        self.login_status.setText(self.t('starting'));self.retry_button.hide();self.configured=False
        def ready(data):
            endpoint=data['base_url']
            if self.client.base_url!=endpoint:
                self.client=ApiClient(endpoint);self.client.on_auth_expired=self.auth_expired.emit
            self.configured=bool(data['google_configured']);self.login_status.setText(self.t('ready' if self.configured else 'config'))
            if self.client.token:self.verify_session()
            elif self.session_store.has_record(self.client.base_url):self.restore_session()
            elif not self.configured:self.retry_button.show()
        def failed(message):
            self.show_error(self.t('cloud_setup') if message.startswith('Set BACKALOR_API_URL') else message)
        self.perform(self.runtime.ensure_running,ready,failed)
    def restore_session(self):
        self.login_status.setText(self.t('restoring'))
        def operation():
            try:token=self.session_store.load(self.client.base_url)
            except SessionStoreError:return {'status':'unavailable'}
            if not token:return {'status':'missing'}
            self.client.token=token
            try:
                self.client.profile=self.client.json('GET','/auth/me',timeout=(3,10))
                return {'status':'authenticated'}
            except ApiError as exc:
                self.client.token=None;self.client.profile=None
                if exc.status==401:
                    try:self.session_store.clear(self.client.base_url)
                    except SessionStoreError:pass
                return {'status':'expired' if exc.status==401 else 'offline'}
        def completed(result):
            if result['status']=='authenticated':self.enter_projects()
            else:
                self.login_status.setText(self.t('offline' if result['status']=='offline' else 'restore_expired' if result['status']=='expired' else 'restore_unavailable' if result['status']=='unavailable' else 'ready'))
                self.retry_button.setVisible(result['status']=='offline')
        self.perform(operation,completed)
    def start_login(self):
        if not self.configured or self.worker is not None or self.flow:return
        if self._locked:
            self.client.on_auth_expired=None
            self.client=ApiClient(self.client.base_url);self.client.on_auth_expired=self.auth_expired.emit
        self.login_status.setText(self.t('busy'));self.retry_button.hide()
        def ready(flow):
            url=QtCore.QUrl(flow['authorization_url'])
            if url.scheme()!='https' or url.host()!='accounts.google.com':raise ValueError('Invalid Google authorization address')
            self.flow=flow;self.deadline=time.monotonic()+flow['expires_in']
            if not QtGui.QDesktopServices.openUrl(url):self.flow=None;raise RuntimeError('Cannot open the system browser')
            self.login_status.setText(self.t('waiting'));self.poll_timer.start()
        self.perform(self.client.start_login,ready)
    def poll_login(self):
        if self.worker is not None or self.flow is None:return
        if time.monotonic()>=self.deadline:
            self.poll_timer.stop();self.flow=None;self.login_status.setText(self.t('expired'));self.controls();return
        flow=dict(self.flow);remember=self.remember.isChecked()
        def operation():
            result=self.client.poll_login(flow)
            if result['status']=='authenticated':
                try:
                    if remember:self.session_store.save(self.client.base_url,self.client.token,self.client.profile)
                    else:self.session_store.clear(self.client.base_url)
                except SessionStoreError:result['remember_failed']=True
            return result
        def completed(result):
            if result['status']=='authenticated':
                self.poll_timer.stop();self.flow=None;self.enter_projects()
                self.session_notice.setText(self.t('remember_failed') if result.get('remember_failed') else '')
                self.session_notice.setVisible(bool(result.get('remember_failed')))
            elif result['status']=='failed':
                self.poll_timer.stop();self.flow=None;self.login_status.setText(self.t('failed'))
        def failed(message):
            self.poll_timer.stop();self.flow=None;self.show_error(message)
        self.perform(operation,completed,failed)
    def cancel_login(self):
        if self.worker is not None:return
        self.poll_timer.stop();flow=self.flow;self.flow=None
        if flow:self.perform(lambda:self.client.cancel_login(flow),lambda _:self.login_status.setText(self.t('ready')))
    def enter_projects(self):
        if not self.client.token or not self.client.profile:return
        profile=self.client.profile
        self.registry=ProjectRegistry(self.state_dir,profile['id']);self.profile_label.setText(profile['name']+'\n'+profile['email'])
        self.stack.setCurrentIndex(1);self.session_timer.start();self.retry_button.hide();self._locked=False
        self.show()
        if self.workspace is not None and self.workspace_user==profile['id']:
            self.workspace.api_client=self.client;self.workspace.setEnabled(True)
        self.refresh_projects()
    def reset_filters(self,*_):
        self.search_timer.stop();self.document_offset=0;self.guard(self.refresh_projects)
    def change_page(self,direction):
        self.document_offset=max(0,self.document_offset+direction*100);self.guard(self.refresh_projects)
    def manage_access(self):
        row=self.table.currentRow()
        if row<0 or self.source_tabs.currentIndex()==0:return
        from .sharing_ui import SharingDialog
        record=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        dialog=SharingDialog(self.client,record,self.language,self)
        dialog.exec();self.refresh_projects()
    def refresh_projects(self,*_):
        if not self.client.token or not self.client.profile or self.registry is None or self.worker is not None:return
        query=self.document_search.text().strip()
        if self.source_tabs.currentIndex()==0:
            records=self.registry.list()
            if query:records=[record for record in records if query.casefold() in (record['title']+' '+record['path']).casefold()]
            self.populate(records);return
        filters={'scope':('mine','public','shared','all')[self.source_tabs.currentIndex()-1],
                 'q':query,'sort':self.sort_filter.currentData(),'limit':101,'offset':self.document_offset}
        visibility=self.visibility_filter.currentData();snapshot=self.snapshot_filter.currentData()
        if visibility:filters['visibility']=visibility
        if snapshot is not None:filters['has_snapshot']=snapshot
        self.hub_status.setText(self.t('busy'));self.perform(lambda:self.client.projects(**filters),self.populate)
    def populate(self,records):
        self.table.setRowCount(0);cloud=self.source_tabs.currentIndex()!=0
        self.document_has_next=cloud and len(records)>100
        if cloud:records=records[:100]
        for record in records:
            row=self.table.rowCount();self.table.insertRow(row)
            item=QtWidgets.QTableWidgetItem(record['title']);item.setData(QtCore.Qt.ItemDataRole.UserRole,record);self.table.setItem(row,0,item)
            self.table.setItem(row,1,QtWidgets.QTableWidgetItem((self.t('public' if record.get('visibility')=='public' else 'private')+' · '+str(record['version'])) if cloud else record['path']))
        self.selected_button.setText(self.t('download' if cloud else 'open_selected'))
        self.hub_status.setText('' if records else self.t('empty_cloud' if cloud else 'empty_local'));self.controls()
    def open_local(self):
        if not self.client.token or not self.client.profile:return
        directory=QtWidgets.QFileDialog.getExistingDirectory(self,self.t('open'),str(self.initial_project or Path.home()))
        if directory:self.open_workspace(Path(directory))
    def new_project(self):
        if not self.client.token or not self.client.profile:return
        directory=QtWidgets.QFileDialog.getExistingDirectory(self,self.t('choose_empty'),str(self.initial_project.parent if self.initial_project else Path.home()))
        if not directory:return
        target=Path(directory)
        if any(target.iterdir()):self.show_error(self.t('not_empty'));return
        title,ok=QtWidgets.QInputDialog.getText(self,self.t('new'),self.t('name_prompt'))
        if not ok or not title.strip():return
        ensure_project_structure(target);atomic_write(target/'project.json',json.dumps({'schema_version':1,'title':title.strip(),'description':'','source':''},ensure_ascii=False,indent=2).encode('utf-8'))
        self.open_workspace(target)
    def open_selected(self):
        if self.worker is not None or not self.client.token:return
        row=self.table.currentRow()
        if row<0:return
        record=self.table.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole)
        if self.source_tabs.currentIndex()==0:self.open_workspace(Path(record['path']));return
        if not record['has_snapshot']:return
        directory=QtWidgets.QFileDialog.getExistingDirectory(self,self.t('choose_empty'),str(Path.home()))
        if not directory:return
        target=Path(directory)
        if any(target.iterdir()):self.show_error(self.t('not_empty'));return
        def transfer():
            with tempfile.TemporaryDirectory() as temporary:
                archive=Path(temporary)/'project.zip';self.client.download(record,archive);import_bundle(archive,target)
            return target
        self.hub_status.setText(self.t('busy'));self.perform(transfer,self.open_workspace)
    def open_workspace(self,path):
        if self._locked or not self.client.token or not self.client.profile or self.registry is None:return
        path=Path(path).resolve()
        if self.workspace is not None:
            if self.editor_busy():self.show_error(self.t('different_account'));return
            if self.workspace_user!=self.client.profile['id']:
                self._closing_editor=True
                self.workspace._close_to_recovery=True
                if not self.workspace.close():self.workspace._close_to_recovery=False;self._closing_editor=False;return
                self._closing_editor=False;self.workspace.deleteLater();self.workspace=None
            elif self.workspace.root!=path:
                self.workspace.switch_project(path)
                if self.workspace.root!=path:return
        if self.workspace is None:
            from .workspace import WorkspaceWindow
            self.workspace=WorkspaceWindow(path,api_client=self.client);self.workspace.session_controller=self
            self.workspace.apply_language(self.language)
            self.workspace.closed.connect(self.editor_closed)
        self.workspace_user=self.client.profile['id'];self.registry.add(path)
        self.workspace.setEnabled(True);self.workspace.show();self.workspace.raise_();self.hide()
    def show_projects(self):
        if self._locked or not self.client.token:self.lock(self.t('session_expired'));return
        if self.workspace is not None and self.workspace.save_annotations_current(silent=True) is False:return
        if self.workspace is not None:self.workspace.hide()
        self.stack.setCurrentIndex(1);self.refresh_projects();self.show();self.raise_()
    def editor_closed(self):
        if self._closing_editor:return
        self.workspace=None;self.workspace_user=None
        if self.client.token:self.show_projects()
        else:self.stack.setCurrentIndex(0);self.show()
    def verify_session(self):
        if self.worker is not None or not self.client.token:return
        def operation():
            try:return {'profile':self.client.json('GET','/auth/me',timeout=(3,8))}
            except ApiError as exc:return {'error':str(exc),'status':exc.status}
        def completed(result):
            if 'profile' in result:
                self.client.profile=result['profile']
                if self.stack.currentIndex()==0:self.enter_projects()
            else:self.lock(self.t('session_expired' if result['status']==401 else 'offline'))
        self.perform(operation,completed)
    def lock(self,message):
        self.session_timer.stop();self._locked=True
        if self.workspace is not None:
            self.workspace._checkpoint_safely();self.workspace.setEnabled(False);self.workspace.hide()
            for dialog in self.workspace.findChildren(QtWidgets.QDialog):dialog.hide()
        self.stack.setCurrentIndex(0);self.login_status.setText(message);self.retry_button.show();self.show();self.raise_();self.controls()
    def _auth_expired(self):
        try:self.session_store.forget(self.client.base_url)
        except SessionStoreError:pass
        self.lock(self.t('session_expired'))
    def sign_out(self):
        if self.worker is not None:return
        if self.workspace is not None:
            if self.editor_busy():return
            if self.workspace._property_dirty:self.workspace._checkpoint()
            elif self.workspace.save_annotations_current(silent=True) is False:return
        def operation():
            self.client.logout()
            try:self.session_store.clear(self.client.base_url)
            except SessionStoreError:pass
        self.perform(operation,lambda _:self.lock(self.t('ready')))
    def closeEvent(self,event):
        if self.worker is not None:
            self._pending_close=True;self.login_status.setText(self.t('close_wait'));event.ignore();return
        if self.editor_busy():
            self.login_status.setText(self.t('different_account'));event.ignore();return
        self.poll_timer.stop();self.session_timer.stop()
        if self.flow:
            flow=self.flow;self.flow=None;self._pending_close=True;self.perform(lambda:self.client.cancel_login(flow),lambda _:None);event.ignore();return
        if self.workspace is not None:
            self._closing_editor=True
            self.workspace._close_to_recovery=self._locked or not self.workspace.isVisible()
            if not self.workspace.close():self.workspace._close_to_recovery=False;self._closing_editor=False;event.ignore();return
            self._closing_editor=False
        self.runtime.close();event.accept();QtWidgets.QApplication.instance().quit()
    def _finish_close(self):
        self._pending_close=False;self.close()
    def editor_busy(self):
        return self.workspace is not None and (self.workspace._task is not None or self.workspace._process is not None or
            any(getattr(dialog,'worker',None) is not None for dialog in self.workspace.findChildren(QtWidgets.QDialog)))
