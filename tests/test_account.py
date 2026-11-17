from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PyQt6 import QtWidgets,QtCore
from app.workspace import WorkspaceWindow
from app.account import AccountDialog
from app.api_client import ApiClient,ApiError,normalize_server_url

APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class ApiClientTests(unittest.TestCase):
    def test_only_loopback_may_use_plain_http(self):
        self.assertEqual(normalize_server_url(' http://127.0.0.1:8000/ '),'http://127.0.0.1:8000')
        self.assertEqual(normalize_server_url('https://api.example.com'),'https://api.example.com')
        for value in ['http://api.example.com','https://user:pass@api.example.com','file:///tmp/x','https://api.example.com/path','https://api.example.com?x=1']:
            with self.subTest(value=value),self.assertRaises(ValueError):normalize_server_url(value)
    def test_expired_session_clears_local_identity(self):
        client=ApiClient();client.token='secret';client.profile={'name':'User'}
        response=Mock();response.status_code=401;response.json.return_value={'detail':'Expired'}
        with patch('app.api_client.requests.request',return_value=response):
            with self.assertRaises(ApiError):client.projects()
        self.assertIsNone(client.token);self.assertIsNone(client.profile)
    def test_token_uses_header_and_redirects_are_disabled(self):
        client=ApiClient();client.token='test-token';response=Mock();response.status_code=200
        with patch('app.api_client.requests.request',return_value=response) as request:client.request('GET','/projects')
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],'Bearer test-token')
        self.assertFalse(request.call_args.kwargs['allow_redirects'])
    def test_failed_logout_does_not_claim_revocation(self):
        client=ApiClient();client.token='token'
        with patch.object(client,'json',side_effect=ApiError('offline')):
            with self.assertRaises(ApiError):client.logout()
        self.assertEqual(client.token,'token')

class AccountDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.window=WorkspaceWindow(Path(self.temp.name));self.dialog=AccountDialog(self.window)
    def tearDown(self):self.dialog.close();self.window.close();APP.processEvents();self.temp.cleanup()
    def wait(self):
        from time import monotonic
        deadline=monotonic()+5
        while self.dialog.worker and monotonic()<deadline:APP.processEvents();QtCore.QThread.msleep(2)
        self.assertIsNone(self.dialog.worker)
    def test_logged_out_controls(self):
        self.assertTrue(self.dialog.login_button.isEnabled());self.assertFalse(self.dialog.logout_button.isEnabled())
        self.assertFalse(self.dialog.new_button.isEnabled());self.assertFalse(self.dialog.download_button.isEnabled())
    def test_server_check_is_background_and_actionable(self):
        with patch.object(self.dialog.client,'json',return_value={'status':'ok','google_configured':False}):
            self.dialog.check_server();self.wait()
        self.assertIn('OAuth',self.dialog.status.text());self.assertTrue(self.dialog.login_button.isEnabled())
    def test_network_failure_restores_controls(self):
        with patch.object(self.dialog.client,'projects',side_effect=ApiError('Network unavailable')):
            self.dialog.client.token='token';self.dialog.refresh();self.wait()
        self.assertEqual(self.dialog.status.text(),'Network unavailable');self.assertTrue(self.dialog.refresh_button.isEnabled())
    def test_browser_login_flow_then_profile(self):
        flow={'state':'s'*43,'poll_secret':'p'*43,'authorization_url':'https://accounts.google.com/o/oauth2/v2/auth?test=1','expires_in':300}
        with patch.object(self.dialog.client,'start_login',return_value=flow),patch('app.account.QtGui.QDesktopServices.openUrl',return_value=True):
            self.dialog.login();self.wait()
        self.assertEqual(self.dialog.flow,flow);self.assertTrue(self.dialog.cancel_button.isEnabled())
        def poll(_):
            self.dialog.client.token='token';self.dialog.client.profile={'name':'Vlad','email':'v@example.com'}
            return {'status':'authenticated'}
        with patch.object(self.dialog.client,'poll_login',side_effect=poll),patch.object(self.dialog.client,'projects',return_value=[]):
            self.dialog.poll();self.wait()
        self.assertIsNone(self.dialog.flow);self.assertTrue(self.dialog.new_button.isEnabled());self.assertIn('Vlad',self.window.account_action.text())
    def test_invalid_browser_destination_rejected(self):
        flow={'authorization_url':'https://evil.example/phishing','state':'s','poll_secret':'p','expires_in':300}
        with patch.object(self.dialog.client,'start_login',return_value=flow),patch('app.account.QtGui.QDesktopServices.openUrl') as opened:
            self.dialog.login();self.wait()
        opened.assert_not_called();self.assertIsNone(self.dialog.flow)
    def test_close_waits_for_running_task(self):
        self.dialog.worker=Mock();self.dialog.reject()
        self.assertEqual(self.dialog.status.text(),self.dialog.t('wait_close'));self.dialog.worker=None

if __name__=='__main__':unittest.main()
