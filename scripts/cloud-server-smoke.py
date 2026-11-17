"""Verify the production entrypoint with disposable PostgreSQL, without Docker."""
from pathlib import Path
import os,sys,socket,subprocess,tempfile,time,json
import requests,embedded_postgres
ROOT=Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix='backalor-cloud-cli-') as temporary:
        root=Path(temporary)
        with embedded_postgres.get_server(root/'postgres') as postgres:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            environment={**os.environ,'PORT':str(port),'BACKALOR_DATA_DIR':str(root/'cloud-storage'),
                         'BACKALOR_PUBLIC_URL':f'http://127.0.0.1:{port}',
                         'BACKALOR_REQUIRE_POSTGRES':'1','BACKALOR_DATABASE_URL':postgres.get_uri(),
                         'GOOGLE_CLIENT_ID':'','GOOGLE_CLIENT_SECRET':''}
            with (root/'server.log').open('w') as log:
                process=subprocess.Popen([sys.executable,'-m','backend.serve'],cwd=ROOT,env=environment,stdout=log,stderr=log)
                try:
                    deadline=time.monotonic()+10;data=None
                    while time.monotonic()<deadline:
                        if process.poll() is not None:raise RuntimeError((root/'server.log').read_text())
                        try:
                            response=requests.get(f'http://127.0.0.1:{port}/ready',timeout=1)
                            if response.status_code==200:data=response.json();break
                        except requests.RequestException:pass
                        time.sleep(.05)
                    assert data=={'status':'ok','database':'postgresql'},data
                    assert not (root/'cloud-storage/backalor.sqlite3').exists()
                    assert (root/'cloud-storage/snapshots').is_dir()
                    print(json.dumps({'production_entrypoint_started':True,'postgresql_ready':True,'sqlite_created':False,'port_environment_respected':True},indent=2))
                finally:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    return 0


if __name__=='__main__':raise SystemExit(main())
