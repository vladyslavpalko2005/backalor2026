"""Isolated integration test: fake Google identity only in this test process.
No production authentication bypass is exposed by the application.
"""
from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import requests
import uvicorn
from PIL import Image
from PyQt6 import QtWidgets,QtCore
from backend.main import create_app
from backend.config import Settings
from app.workspace import WorkspaceWindow
from app.account import AccountDialog
from app.theme import apply_theme
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations
from app.project import ensure_project_structure


def main():
    root=Path(__file__).resolve().parent.parent
    evidence=Path(os.environ.get('BACKALOR_TEST_ARTIFACTS',str(root/'.impeccable/review')));evidence.mkdir(parents=True,exist_ok=True)
    app=QtWidgets.QApplication([]);apply_theme(app)
    with tempfile.TemporaryDirectory() as temporary:
        base=Path(temporary)
        source=base/'local';ensure_project_structure(source)
        Image.new('RGB',(120,80),'white').save(source/'images_raw/page.png')
        annotation=AnnotationFile('page.png',[AnnotationItem(1,'L1',None,[0,0,100,60],transcription='smoke č')],2)
        save_annotations(source/'annotations/page.json',annotation)
        backend=create_app(Settings(base/'server',google_client_id='test-client',google_client_secret='test-secret'))
        backend.state.identity_provider=lambda *args:{'sub':'smoke-user','name':'Test User','email':'test@example.com'}
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(backend,log_level='error',access_log=False))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        settings_type=QtCore.QSettings
        settings_patch=patch.object(QtCore,'QSettings',side_effect=lambda *args:
            settings_type(str(base/'settings.ini'),settings_type.Format.IniFormat))
        settings_patch.start()
        window=WorkspaceWindow(source)
        window.api_client.base_url=f'http://127.0.0.1:{port}'
        dialog=AccountDialog(window);dialog.show();app.processEvents()
        dialog.grab().save(str(evidence/'account-offline.png'))
        def wait():
            deadline=time.monotonic()+20
            while dialog.worker is not None and time.monotonic()<deadline:
                app.processEvents();QtCore.QThread.msleep(5)
            assert dialog.worker is None,'Background request timeout'
            assert dialog.failure is None,dialog.failure
            app.processEvents()
        try:
            with patch('app.account.QtGui.QDesktopServices.openUrl',return_value=True):dialog.login();wait()
            assert dialog.flow
            callback=requests.get(f'http://127.0.0.1:{port}/auth/google/callback',params={'state':dialog.flow['state'],'code':'test-code'},timeout=5)
            assert callback.status_code==200,callback.text
            dialog.poll();wait();assert window.api_client.profile['email']=='test@example.com'
            dialog.upload(True);wait();assert dialog.table.rowCount()==1
            dialog.table.selectRow(0);app.processEvents()
            dialog.grab().save(str(evidence/'account-signed-in.png'))
            project=dialog.selected();assert project['has_snapshot'] and project['version']==1
            with patch('app.account.QtWidgets.QMessageBox.question',return_value=QtWidgets.QMessageBox.StandardButton.Yes):dialog.upload(False);wait()
            dialog.table.selectRow(0);app.processEvents();assert dialog.selected()['version']==2
            target=base/'downloaded';target.mkdir()
            with patch('app.account.QtWidgets.QFileDialog.getExistingDirectory',return_value=str(target)):dialog.download();wait()
            assert window.root==target
            assert load_annotations(target/'annotations/page.json')==annotation
            assert (target/'images_raw/page.png').is_file()
            token=window.api_client.token;dialog.logout();wait();assert window.api_client.token is None
            assert requests.get(f'http://127.0.0.1:{port}/auth/me',headers={'Authorization':'Bearer '+token},timeout=5).status_code==401
            print(json.dumps({'live_http':True,'browser_google_identity':'mocked only in this isolated smoke process',
                'desktop_login':True,'project_upload':True,'versioned_update':True,'project_download':True,'logout_revocation':True},indent=2))
        finally:
            dialog.close();window.close();server.should_exit=True;thread.join(timeout=10);sock.close()
            settings_patch.stop()

if __name__=='__main__':main()
