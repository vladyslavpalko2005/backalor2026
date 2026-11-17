"""Real local HTTP + production portal flow; fake Google identity only in this process."""
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
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import requests
import uvicorn
from PIL import Image
from PyQt6 import QtCore,QtWidgets
from backend.main import create_app
from backend.config import Settings
from app.portal import PortalWindow
from app.account import AccountDialog
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations
from app.project import ensure_project_structure
from app.theme import apply_theme


def main():
    app=QtWidgets.QApplication([]);apply_theme(app)
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);source=root/'source';ensure_project_structure(source)
        Image.new('RGB',(120,80),'white').save(source/'images_raw/page.png')
        data=AnnotationFile('page.png',[AnnotationItem(1,'L1',None,[0,0,100,60],notes='preserve original')],2)
        save_annotations(source/'annotations/page.json',data);before=(source/'annotations/page.json').read_bytes()
        backend=create_app(Settings(root/'backend',google_client_id='isolated-test-client',google_client_secret='isolated-test-secret'))
        backend.state.identity_provider=lambda *args:{'sub':'portal-test','name':'Portal Test','email':'portal@example.com'}
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];origin=f'http://127.0.0.1:{port}'
        server=uvicorn.Server(uvicorn.Config(backend,log_level='error',access_log=False));thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        runtime=Mock();runtime.ensure_running.side_effect=lambda:{'base_url':origin,**requests.get(origin+'/health',timeout=2).json()}
        portal=PortalWindow(initial_project=source,runtime=runtime,state_dir=root/'registry',autostart=False,session_store=Mock(has_record=Mock(return_value=False)));portal.show()
        def wait(owner):
            deadline=time.monotonic()+20
            while owner.worker is not None and time.monotonic()<deadline:app.processEvents();QtCore.QThread.msleep(2)
            app.processEvents();assert owner.worker is None,'Request timed out';assert owner.failure is None,owner.failure
        try:
            portal.bootstrap();wait(portal);assert portal.configured;assert portal.workspace is None
            with patch('app.portal.QtGui.QDesktopServices.openUrl',return_value=True):portal.start_login();wait(portal)
            response=requests.get(origin+'/auth/google/callback',params={'state':portal.flow['state'],'code':'isolated-test-code'},timeout=3)
            assert response.status_code==200
            portal.poll_login();wait(portal);assert portal.stack.currentIndex()==1;assert portal.workspace is None
            portal.open_workspace(source);assert portal.workspace.api_client is portal.client
            account=AccountDialog(portal.workspace);account.show();wait(account)
            assert account.server.isHidden() and account.connect_button.isHidden()
            account.upload(True);wait(account);assert account.table.rowCount()==1;account.close()
            portal.show_projects();portal.source_tabs.setCurrentIndex(1);wait(portal);assert portal.table.rowCount()==1;portal.table.selectRow(0)
            target=root/'downloaded';target.mkdir()
            with patch('app.portal.QtWidgets.QFileDialog.getExistingDirectory',return_value=str(target)):portal.open_selected();wait(portal)
            assert portal.workspace.root==target.resolve();assert load_annotations(target/'annotations/page.json')==data
            assert (source/'annotations/page.json').read_bytes()==before
            token=portal.client.token;portal.sign_out();wait(portal)
            assert portal.stack.currentIndex()==0 and not portal.workspace.isVisible()
            assert requests.get(origin+'/auth/me',headers={'Authorization':'Bearer '+token},timeout=3).status_code==401
            print(json.dumps({'backend_ready_before_login':True,'mandatory_google_gate':True,'projects_before_editor':True,
                'manual_server_controls_removed':True,'upload_download_roundtrip':True,'source_annotations_preserved':True,
                'logout_revokes_and_locks':True,'google_identity':'mocked only inside this isolated smoke process'},indent=2))
        finally:
            portal.close();app.processEvents();server.should_exit=True;thread.join(timeout=10);sock.close()

if __name__=='__main__':main()
