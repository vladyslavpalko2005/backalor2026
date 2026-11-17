"""Google registration → remembered restart → logout over HTTP and PostgreSQL.

External Google identity and the OS vault are replaced only in this test. The
API, PostgreSQL, session checks, Qt flow and nonsecret metadata files are real.
"""
from pathlib import Path
import os,sys,socket,tempfile,threading,time,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from unittest.mock import Mock,patch
import requests,uvicorn,embedded_postgres
from PyQt6 import QtCore,QtWidgets
from backend.config import Settings
from backend.main import create_app
from app.api_client import ApiClient
from app.portal import PortalWindow
from app.session_store import SecureSessionStore


class TestVault:
    def __init__(self):self.values={}
    def get_password(self,service,key):return self.values.get((service,key))
    def set_password(self,service,key,value):self.values[service,key]=value
    def delete_password(self,service,key):self.values.pop((service,key),None)


def main():
    app=QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory(prefix='backalor-remember-') as directory:
        root=Path(directory)
        with embedded_postgres.get_server(root/'postgres') as postgres:
            backend=create_app(Settings(root/'server',google_client_id='isolated-test',google_client_secret='isolated-test',database_url=postgres.get_uri(),require_postgres=True))
            backend.state.identity_provider=lambda *args:{'sub':'test-user','name':'Test User','email':'test@example.org'}
            sock=socket.socket();sock.bind(('127.0.0.1',0));origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
            server=uvicorn.Server(uvicorn.Config(backend,log_level='error',access_log=False))
            thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
            deadline=time.monotonic()+10
            while not server.started and time.monotonic()<deadline:time.sleep(.02)
            assert server.started
            vault=TestVault();windows=[]
            def portal():
                runtime=Mock();runtime.ensure_running.return_value={'base_url':origin,**requests.get(origin+'/health',timeout=3).json()}
                store=SecureSessionStore(root/'desktop-sessions',backend=vault)
                window=PortalWindow(runtime=runtime,client=ApiClient(origin),state_dir=root/'desktop',session_store=store,autostart=False)
                windows.append(window);return window
            def wait(window):
                deadline=time.monotonic()+10
                while window.worker is not None and time.monotonic()<deadline:app.processEvents();QtCore.QThread.msleep(2)
                app.processEvents();assert window.worker is None;assert window.failure is None,window.failure
            try:
                first=portal();first.bootstrap();wait(first)
                with patch('app.portal.QtGui.QDesktopServices.openUrl',return_value=True):first.start_login();wait(first)
                response=requests.get(origin+'/auth/google/callback',params={'state':first.flow['state'],'code':'isolated-test-code'},timeout=5)
                assert response.status_code==200
                first.poll_login();wait(first);assert first.stack.currentIndex()==1
                token=first.client.token;profile=first.client.profile
                assert first.session_store.has_record(origin)
                assert token not in ''.join(path.read_text() for path in (root/'desktop-sessions').glob('*.json'))
                first.close();app.processEvents()
                second=portal();second.bootstrap();wait(second)
                assert second.stack.currentIndex()==1 and second.client.profile['id']==profile['id']
                with backend.state.database.connect() as db:
                    assert db.execute('SELECT count(*) FROM users').fetchone()[0]==1
                    assert db.execute('SELECT count(*) FROM login_flows').fetchone()[0]==1
                second.sign_out();wait(second)
                assert not second.session_store.has_record(origin) and not vault.values
                assert requests.get(origin+'/auth/me',headers={'Authorization':'Bearer '+token},timeout=3).status_code==401
                third=portal();third.bootstrap();wait(third);assert third.stack.currentIndex()==0
                assert not (root/'server/backalor.sqlite3').exists()
                print(json.dumps({'automatic_google_registration':True,'restart_restores_verified_session':True,
                    'no_repeated_google_flow_on_restart':True,'no_token_in_metadata_json':True,
                    'logout_revokes_and_forgets':True,'postgresql':True,'sqlite_created':False,
                    'test_doubles':['external Google identity','OS credential vault']},indent=2))
            finally:
                for window in windows:window.close()
                app.processEvents();server.should_exit=True;thread.join(timeout=10);sock.close()


if __name__=='__main__':main()
