"""Connect to a cloud API; own a local child only in explicitly allowed development mode."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import requests
from .api_client import normalize_server_url


class BackendRuntime:
    def __init__(self,repo_root=None,base_url=None,data_dir=None,python=None,environment=None,allow_local=True):
        self.repo_root=Path(repo_root or Path(__file__).resolve().parent.parent)
        self.base_url=normalize_server_url(base_url) if base_url else None
        self.data_dir=Path(data_dir) if data_dir else None
        self.python=str(python or self.repo_root/'.venv-backend/bin/python')
        self.environment=environment;self.allow_local=allow_local
        self.process=None;self._log=None
    def _configuration(self):
        if self.base_url is not None:
            self.data_dir=self.data_dir or self.repo_root/'backend_data';return
        from .client_config import configured_api_url
        remote=configured_api_url(self.repo_root,self.environment)
        if remote:
            self.base_url=remote
            self.data_dir=self.data_dir or self.repo_root/'backend_data'
            return
        if not self.allow_local:
            raise RuntimeError('Set BACKALOR_API_URL to your cloud HTTPS API address. A local backend/database is disabled for normal desktop startup.')
        if not Path(self.python).is_file():
            raise RuntimeError('Backend environment is missing. Start Backalor with launch.command to prepare it.')
        code="from backend.config import Settings; import json; s=Settings.from_env(); print(json.dumps({'url':s.public_url,'directory':str(s.data_dir)}))"
        try:
            response=subprocess.run([self.python,'-c',code],cwd=self.repo_root,env=self.environment,
                                    capture_output=True,text=True,timeout=15,check=True)
            data=json.loads(response.stdout);self.base_url=normalize_server_url(data['url']);self.data_dir=Path(data['directory'])
        except (OSError,subprocess.SubprocessError,ValueError,KeyError) as exc:
            raise RuntimeError('Cannot read backend configuration. Check .env and requirements-backend.txt.') from None
    def _probe(self):
        try:
            with requests.get(self.base_url+'/health',timeout=(1,2),allow_redirects=False) as response:
                if response.status_code!=200:return None
                payload=response.json()
            if payload.get('service')=='backalor' and payload.get('status')=='ok':return payload
            # Compatible server already running from an older Backalor launch.
            if payload.get('status')=='ok' and isinstance(payload.get('google_configured'),bool):
                with requests.get(self.base_url+'/openapi.json',timeout=(1,2),allow_redirects=False) as response:
                    if response.status_code==200 and response.json().get('info',{}).get('title')=='Backalor API':return payload
        except (requests.RequestException,ValueError,AttributeError):pass
        return None
    def ensure_running(self):
        self._configuration()
        healthy=self._probe()
        if healthy:return {'base_url':self.base_url,**healthy}
        url=urlsplit(self.base_url)
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1'):
            raise RuntimeError('The configured backend is unavailable. Try again when the server is reachable.')
        if not Path(self.python).is_file():raise RuntimeError('Backend Python environment is missing. Run launch.command.')
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError('Backend is still starting. Try again in a moment.')
        self.data_dir.mkdir(parents=True,exist_ok=True)
        if self._log:self._log.close()
        log_path=self.data_dir/'backend.log'
        self._log=log_path.open('a',encoding='utf-8');log_path.chmod(0o600)
        try:
            self.process=subprocess.Popen([self.python,'-m','uvicorn','backend.main:create_app','--factory',
                '--host',url.hostname,'--port',str(url.port or 80),'--no-access-log'],
                cwd=self.repo_root,env=self.environment,stdout=self._log,stderr=self._log)
        except OSError:raise RuntimeError('Cannot start the backend. Check the Python environment.') from None
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            healthy=self._probe()
            if healthy:return {'base_url':self.base_url,**healthy}
            if self.process.poll() is not None:
                raise RuntimeError('Backend could not start. Check backend_data/backend.log and whether the port is occupied.')
            time.sleep(.15)
        self.close()
        raise RuntimeError('Backend startup timed out. Check backend_data/backend.log and retry.')
    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        self.process=None
        if self._log:self._log.close();self._log=None
