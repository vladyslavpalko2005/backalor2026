from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import Mock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6 import QtCore,QtWidgets
from app.api_client import ApiClient,ApiError
from app.portal import PortalWindow
from app.session_store import SecureSessionStore,SessionStoreError
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
ORIGIN='https://test.example.org'
PROFILE={'id':'google-a','name':'Researcher','email':'a@example.org'}
TOKEN='A'*48


class Vault:
    def __init__(self):self.entries={}
    def set_password(self,service,user,value):self.entries[service,user]=value
    def get_password(self,service,user):return self.entries.get((service,user))
    def delete_password(self,service,user):self.entries.pop((service,user),None)


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name);self.vault=Vault();self.store=SecureSessionStore(self.directory,backend=self.vault)
    def tearDown(self):self.temp.cleanup()
    def test_token_is_only_in_vault_and_profile_survives_restart(self):
        self.store.save(ORIGIN,TOKEN,PROFILE)
        raw=next(self.directory.glob('*.json')).read_text()
        self.assertNotIn(TOKEN,raw);self.assertNotIn('access_token',raw)
        self.assertEqual(json.loads(raw)['profile'],PROFILE)
        self.assertEqual(SecureSessionStore(self.directory,backend=self.vault).load(ORIGIN),TOKEN)
        self.assertEqual(next(self.directory.glob('*.json')).stat().st_mode & 0o777,0o600)
    def test_origins_are_isolated(self):
        self.store.save(ORIGIN,TOKEN,PROFILE)
        self.assertIsNone(self.store.load('https://different.example.org'))
    def test_corrupt_hint_never_restores_a_session(self):
        self.store.save(ORIGIN,TOKEN,PROFILE)
        next(self.directory.glob('*.json')).write_text('{bad')
        self.assertFalse(self.store.has_record(ORIGIN));self.assertIsNone(self.store.load(ORIGIN))
    def test_missing_vault_item_forgets_hint(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);self.vault.entries.clear()
        self.assertIsNone(self.store.load(ORIGIN));self.assertFalse(self.store.has_record(ORIGIN))
    def test_locked_vault_has_no_plaintext_fallback(self):
        self.vault.set_password=Mock(side_effect=RuntimeError('locked'))
        with self.assertRaises(SessionStoreError):self.store.save(ORIGIN,TOKEN,PROFILE)
        self.assertEqual(list(self.directory.iterdir()),[])
    def test_failed_deletion_still_prevents_restoration(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);self.vault.delete_password=Mock(side_effect=RuntimeError('locked'))
        with self.assertRaises(SessionStoreError):self.store.clear(ORIGIN)
        self.assertIsNone(self.store.load(ORIGIN))
    def test_invalid_tokens_and_profiles_are_not_saved(self):
        for token,profile in [('short',PROFILE),(TOKEN,{}),('token\n'+TOKEN,PROFILE)]:
            with self.assertRaises(SessionStoreError):self.store.save(ORIGIN,token,profile)
        self.assertFalse(self.store.has_record(ORIGIN))


class RememberLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=SecureSessionStore(self.root/'sessions',backend=Vault());self.windows=[]
    def tearDown(self):
        for window in self.windows:
            self.wait(window);window.close()
        APP.processEvents();self.temp.cleanup()
    def wait(self,window):
        deadline=monotonic()+5
        while window.worker is not None and monotonic()<deadline:APP.processEvents();QtCore.QThread.msleep(2)
        APP.processEvents();self.assertIsNone(window.worker)
    def window(self):
        client=ApiClient(ORIGIN);client.projects=Mock(return_value=[])
        runtime=Mock();runtime.ensure_running.return_value={'base_url':ORIGIN,'google_configured':True}
        window=PortalWindow(runtime=runtime,client=client,state_dir=self.root/'accounts',autostart=False,session_store=self.store)
        self.windows.append(window);return window
    def test_restart_restores_only_after_server_verification(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);window=self.window()
        def verify(*args,**kwargs):
            self.assertEqual(window.stack.currentIndex(),0);self.assertIsNone(window.workspace)
            self.assertEqual(window.client.token,TOKEN);return PROFILE
        window.client.json=Mock(side_effect=verify)
        window.bootstrap();self.wait(window)
        self.assertEqual(window.stack.currentIndex(),1);self.assertEqual(window.client.profile,PROFILE)
        window.client.json.assert_called_once_with('GET','/auth/me',timeout=(3,10))
    def test_expired_session_is_forgotten_and_editor_stays_closed(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);window=self.window();window.client.json=Mock(side_effect=ApiError('expired',401))
        window.bootstrap();self.wait(window)
        self.assertEqual(window.stack.currentIndex(),0);self.assertIsNone(window.workspace)
        self.assertIsNone(window.client.token);self.assertFalse(self.store.has_record(ORIGIN))
    def test_offline_restore_keeps_saved_session_for_retry(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);window=self.window();window.client.json=Mock(side_effect=ApiError('offline'))
        window.bootstrap();self.wait(window)
        self.assertTrue(self.store.has_record(ORIGIN));self.assertEqual(window.stack.currentIndex(),0)
        window.client.json=Mock(return_value=PROFILE);window.bootstrap();self.wait(window)
        self.assertEqual(window.stack.currentIndex(),1)
    def login(self,window,remember=True):
        window.configured=True;window.remember.setChecked(remember);window.flow={'state':'s','poll_secret':'p'};window.deadline=monotonic()+60
        def poll(flow):
            window.client.token=TOKEN;window.client.profile=dict(PROFILE);return {'status':'authenticated'}
        window.client.poll_login=Mock(side_effect=poll);window.poll_login();self.wait(window)
    def test_google_login_persists_and_second_window_restores(self):
        first=self.window();self.login(first)
        self.assertTrue(self.store.has_record(ORIGIN));self.assertEqual(self.store.load(ORIGIN),TOKEN)
        second=self.window();second.client.json=Mock(return_value=PROFILE);second.bootstrap();self.wait(second)
        self.assertEqual(second.stack.currentIndex(),1)
    def test_unchecked_remember_does_not_save(self):
        window=self.window();self.login(window,remember=False)
        self.assertEqual(window.stack.currentIndex(),1);self.assertFalse(self.store.has_record(ORIGIN))
    def test_vault_failure_does_not_block_successful_google_login(self):
        self.store._backend.set_password=Mock(side_effect=RuntimeError('locked'))
        window=self.window();self.login(window)
        self.assertEqual(window.stack.currentIndex(),1);self.assertTrue(window.session_notice.text())
        self.assertFalse(self.store.has_record(ORIGIN))
    def test_logout_revokes_then_forgets_saved_login(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);window=self.window();window.client.token=TOKEN;window.client.profile=dict(PROFILE)
        def logout():window.client.token=None;window.client.profile=None
        window.client.logout=Mock(side_effect=logout);window.sign_out();self.wait(window)
        self.assertFalse(self.store.has_record(ORIGIN));self.assertIsNone(self.store.load(ORIGIN))
        self.assertEqual(window.stack.currentIndex(),0)
    def test_failed_logout_preserves_the_valid_saved_session(self):
        self.store.save(ORIGIN,TOKEN,PROFILE);window=self.window();window.client.token=TOKEN;window.client.profile=dict(PROFILE)
        window.client.logout=Mock(side_effect=ApiError('offline'));window.sign_out();self.wait(window)
        self.assertTrue(self.store.has_record(ORIGIN));self.assertEqual(window.client.token,TOKEN)
