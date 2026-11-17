from __future__ import annotations
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from app.backend_runtime import BackendRuntime

REPO=Path(__file__).resolve().parent.parent


class BackendRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{self.port}'
        self.environment={**os.environ,'BACKALOR_PUBLIC_URL':self.url,'BACKALOR_DATA_DIR':str(self.root/'data'),
                          'GOOGLE_CLIENT_ID':'isolated-test-client','GOOGLE_CLIENT_SECRET':'isolated-test-secret'}
        self.runtime=BackendRuntime(REPO,self.url,self.root/'data',REPO/'.venv-backend/bin/python',self.environment)
    def tearDown(self):self.runtime.close();self.temp.cleanup()
    def test_owned_backend_starts_before_auth_and_stops_cleanly(self):
        health=self.runtime.ensure_running();self.assertEqual(health['service'],'backalor');self.assertTrue(health['google_configured'])
        self.assertIsNotNone(self.runtime.process);self.assertIsNone(self.runtime.process.poll())
        self.assertEqual(requests.get(self.url+'/auth/me',timeout=2).status_code,401)
        child=self.runtime.process;self.runtime.close();self.assertIsNotNone(child.poll())
    def test_existing_backend_is_reused_and_never_stopped_by_second_client(self):
        self.runtime.ensure_running();child=self.runtime.process
        second=BackendRuntime(REPO,self.url,self.root/'other',REPO/'.venv-backend/bin/python',self.environment)
        try:
            self.assertEqual(second.ensure_running()['service'],'backalor');self.assertIsNone(second.process)
            second.close();self.assertIsNone(child.poll());self.assertEqual(requests.get(self.url+'/health',timeout=2).status_code,200)
        finally:second.close()
    def test_public_settings_are_read_without_returning_secrets(self):
        runtime=BackendRuntime(REPO,python=REPO/'.venv-backend/bin/python',environment=self.environment)
        runtime._configuration();self.assertEqual(runtime.base_url,self.url);self.assertEqual(runtime.data_dir,(self.root/'data').resolve())
        self.assertNotIn('secret',str({'base_url':runtime.base_url,'data_dir':str(runtime.data_dir)}))
    def test_remote_failure_does_not_start_an_unrelated_local_server(self):
        runtime=BackendRuntime(REPO,'https://api.example.com',self.root/'data',REPO/'.venv-backend/bin/python')
        with patch.object(runtime,'_probe',return_value=None),patch('app.backend_runtime.subprocess.Popen') as spawn:
            with self.assertRaises(RuntimeError):runtime.ensure_running()
            spawn.assert_not_called()
    def test_occupied_port_does_not_kill_other_service(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=json.dumps({'status':'ok','google_configured':True} if self.path=='/health' else {'info':{'title':'Different service'}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(RuntimeError):self.runtime.ensure_running()
            self.assertEqual(requests.get(self.url+'/health',timeout=2).status_code,200)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)
