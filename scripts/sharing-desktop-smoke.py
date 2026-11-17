"""Real loopback HTTP + Qt sharing scenario, using isolated test identities only.

Run with the desktop environment plus backend dependencies on PYTHONPATH.
No production data, OAuth configuration, tokens or accounts are used.
"""
from __future__ import annotations
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import requests
import uvicorn
from PIL import Image, ImageDraw
from PyQt6 import QtCore, QtWidgets
from backend.main import create_app
from backend.config import Settings
from app.api_client import ApiClient, ApiError
from app.sharing_ui import SharingDialog
from app.annotations import AnnotationFile, AnnotationItem, save_annotations
from app.project import ensure_project_structure
from app.datasets import export_bundle, import_bundle
from app.portable import build_symbol_library, import_symbol_library
from app.library_recognition import recognize_from_library


def main():
    app=QtWidgets.QApplication([])
    outcomes={}
    with tempfile.TemporaryDirectory(prefix='backalor-sharing-') as temporary:
        root=Path(temporary)
        backend=create_app(Settings(root/'server',google_client_id='test',google_client_secret='test'))
        backend.state.identity_provider=lambda settings,code,*args:{'sub':code,'email':code+'@example.com','name':code}
        sock=socket.socket();sock.bind(('127.0.0.1',0));origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
        server=uvicorn.Server(uvicorn.Config(backend,log_level='error',access_log=False))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        end=time.monotonic()+10
        while not server.started and time.monotonic()<end:time.sleep(.02)
        assert server.started
        dialog=None
        def login(name):
            client=ApiClient(origin);flow=client.start_login()
            response=requests.get(origin+'/auth/google/callback',params={'state':flow['state'],'code':name},timeout=5)
            assert response.status_code==200
            assert client.poll_login(flow)['status']=='authenticated'
            return client
        def wait():
            end=time.monotonic()+10
            while dialog.worker is not None and time.monotonic()<end:app.processEvents();QtCore.QThread.msleep(2)
            app.processEvents();assert dialog.worker is None;assert dialog.failure is None,dialog.failure
        def denied(operation,status):
            try:operation()
            except ApiError as exc:assert exc.status==status,(exc.status,status)
            else:raise AssertionError('Access unexpectedly allowed')
        try:
            owner=login('owner');reader=login('reader');outsider=login('outsider')
            source=root/'source';ensure_project_structure(source)
            image=Image.new('RGB',(40,40),'white');draw=ImageDraw.Draw(image)
            draw.rectangle((8,5,13,35),fill='black');draw.rectangle((8,30,32,35),fill='black')
            image.save(source/'images_raw/page.png')
            save_annotations(source/'annotations/page.json',AnnotationFile('page.png',[
                AnnotationItem(1,'L1',None,[0,0,40,40]),AnnotationItem(2,'L2',1,[0,0,40,40]),
                AnnotationItem(3,'L3',2,[0,0,40,40],element_type='cipher_symbol',symbol_code='S001',reviewed=True)],4))
            import_symbol_library(source,build_symbol_library(source))
            archive=root/'source.zip';export_bundle(source,archive)
            project=owner.upload(owner.create_project('TEST key','Historical sample'),archive)
            assert reader.projects(scope='all')==[]
            dialog=SharingDialog(owner,project);wait()
            dialog.email.setText('reader@example.com');dialog.grant();wait()
            shared=reader.projects(scope='shared')[0];assert shared['access_role']=='reader'
            denied(lambda:reader.upload(shared,archive),403)
            outcomes['private_isolation_and_read_only_invitation']='passed'
            target=root/'download.zip';reader.download(shared,target);destination=root/'downloaded';import_bundle(target,destination)
            result,counts=recognize_from_library(image,[AnnotationItem(1,'L3',None,[0,0,40,40])],build_symbol_library(destination))
            assert result[0].symbol_code=='S001' and counts['changed']==1
            outcomes['shared_download_preserves_usable_symbol_samples']='passed'
            dialog.role.setCurrentIndex(1);dialog.grant();wait()
            editor=reader.projects(scope='shared')[0];updated=reader.upload(editor,archive)
            assert updated['version']==2 and updated['access_role']=='editor'
            denied(lambda:owner.upload(project,archive),409)
            outcomes['editor_upload_and_version_conflict']='passed'
            dialog.table.selectRow(0);dialog.remove();wait()
            assert reader.projects(scope='shared')==[]
            denied(lambda:reader.download(updated,root/'forbidden.zip'),404)
            outcomes['revocation_applies_to_snapshot_download']='passed'
            dialog.project=owner.json('GET',f"/projects/{project['id']}")
            dialog.visibility.setCurrentIndex(1);dialog.save_metadata();wait()
            public=outsider.projects(scope='public',q='HISTORICAL')[0]
            assert public['access_role']=='reader'
            outsider.download(public,root/'public.zip')
            denied(lambda:outsider.upload(public,archive),403)
            outcomes['public_discovery_and_read_only_download']='passed'
            dialog.visibility.setCurrentIndex(0);dialog.save_metadata();wait()
            assert outsider.projects(scope='public')==[]
            denied(lambda:outsider.download(public,root/'withdrawn.zip'),404)
            outcomes['public_withdrawal']='passed'
            reader.logout();denied(lambda:reader.projects(scope='shared'),401)
            outcomes['logout_revokes_session']='passed'
            print(json.dumps({'live_http':True,'qt_ui':True,'google_identity':'isolated test provider','scenarios':outcomes},indent=2))
        finally:
            if dialog is not None:dialog.close();app.processEvents()
            server.should_exit=True;thread.join(timeout=10);sock.close()


if __name__=='__main__':main()
