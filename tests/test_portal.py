from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6 import QtWidgets,QtCore
from PIL import Image
from app.portal import PortalWindow
from app.api_client import ApiClient,ApiError
from app.project_registry import ProjectRegistry
from app.project import ensure_project_structure
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.project=self.root/'existing';ensure_project_structure(self.project)
        Image.new('RGB',(200,150),'white').save(self.project/'images_raw/page.png')
        self.annotation_path=self.project/'annotations/page.json'
        save_annotations(self.annotation_path,AnnotationFile('page.png',[AnnotationItem(1,'L1',None,[0,0,190,140])],2))
        self.runtime=Mock();self.runtime.ensure_running.return_value={'base_url':'http://127.0.0.1:8000','service':'backalor','status':'ok','google_configured':True}
        self.client=ApiClient();self.client.projects=Mock(return_value=[])
        self.portal=PortalWindow(initial_project=self.project,runtime=self.runtime,client=self.client,state_dir=self.root/'state',autostart=False,session_store=Mock(has_record=Mock(return_value=False)))
        self.portal.show();APP.processEvents()
    def wait(self):
        deadline=monotonic()+8
        while self.portal.worker is not None and monotonic()<deadline:APP.processEvents();QtCore.QThread.msleep(2)
        APP.processEvents();self.assertIsNone(self.portal.worker)
    def identity(self,sub='user-a'):
        self.client.token='a-valid-test-token';self.client.profile={'id':sub,'name':'Test Person','email':'test@example.com'}
        self.portal.enter_projects();self.wait()
    def tearDown(self):
        self.wait();self.portal.close();APP.processEvents();self.temp.cleanup()
    def test_no_workspace_or_projects_before_google_authentication(self):
        self.assertIsNone(self.portal.workspace);self.assertEqual(self.portal.stack.currentIndex(),0)
        self.portal.open_workspace(self.project);self.assertIsNone(self.portal.workspace)
        self.portal.enter_projects();self.assertEqual(self.portal.stack.currentIndex(),0)
    def test_bootstrap_starts_backend_without_user_entering_a_server(self):
        self.portal.bootstrap();self.wait();self.runtime.ensure_running.assert_called_once()
        self.assertTrue(self.portal.google_button.isEnabled());self.assertIsNone(self.portal.workspace)
        self.assertFalse(any('127.0.0.1' in field.text() for field in self.portal.findChildren(QtWidgets.QLineEdit)))
    def test_missing_oauth_configuration_keeps_workspace_locked(self):
        self.runtime.ensure_running.return_value['google_configured']=False
        self.portal.bootstrap();self.wait();self.assertFalse(self.portal.google_button.isEnabled());self.assertIsNone(self.portal.workspace)
        self.assertIn('GOOGLE_CLIENT_ID',self.portal.login_status.text())
    def test_backend_failure_offers_retry_without_local_bypass(self):
        self.runtime.ensure_running.side_effect=RuntimeError('server unavailable')
        self.portal.bootstrap();self.wait();self.assertTrue(self.portal.retry_button.isVisible());self.assertFalse(self.portal.google_button.isEnabled());self.assertIsNone(self.portal.workspace)
    def test_google_browser_login_opens_projects_not_editor(self):
        self.portal.configured=True
        flow={'state':'state','poll_secret':'proof','authorization_url':'https://accounts.google.com/o/oauth2/v2/auth?state=state','expires_in':300}
        self.client.start_login=Mock(return_value=flow)
        def poll(_):
            self.client.token='new-token';self.client.profile={'id':'new-user','name':'New User','email':'new@example.com'}
            return {'status':'authenticated','access_token':'new-token'}
        self.client.poll_login=Mock(side_effect=poll)
        with patch('app.portal.QtGui.QDesktopServices.openUrl',return_value=True) as browser:
            self.portal.start_login();self.wait();browser.assert_called_once()
        self.portal.poll_login();self.wait();self.assertEqual(self.portal.stack.currentIndex(),1);self.assertIsNone(self.portal.workspace)
        self.assertFalse(self.portal.poll_timer.isActive());self.assertTrue(self.portal.session_timer.isActive())
    def test_invalid_google_destination_is_never_opened(self):
        self.portal.configured=True;self.client.start_login=Mock(return_value={'authorization_url':'https://evil.example/auth','state':'state','expires_in':300})
        with patch('app.portal.QtGui.QDesktopServices.openUrl') as browser:
            self.portal.start_login();self.wait();browser.assert_not_called()
        self.assertIsNone(self.portal.workspace);self.assertIsNone(self.portal.flow)
    def test_denied_or_expired_login_remains_on_login_screen(self):
        self.portal.configured=True;self.portal.flow={'state':'s','poll_secret':'p'};self.portal.deadline=0
        self.portal.poll_login();self.assertEqual(self.portal.stack.currentIndex(),0);self.assertIsNone(self.portal.flow)
        self.portal.flow={'state':'s','poll_secret':'p'};self.portal.deadline=monotonic()+300;self.client.poll_login=Mock(return_value={'status':'failed'})
        self.portal.poll_login();self.wait();self.assertEqual(self.portal.stack.currentIndex(),0);self.assertIsNone(self.portal.workspace)
    def test_open_project_passes_authenticated_client_and_preserves_annotations(self):
        before=self.annotation_path.read_bytes();self.identity();self.portal.open_workspace(self.project)
        self.assertIs(self.portal.workspace.api_client,self.client);self.assertIs(self.portal.workspace.session_controller,self.portal)
        self.assertFalse(self.portal.isVisible());self.assertTrue(self.portal.workspace.isVisible());self.assertEqual(self.annotation_path.read_bytes(),before)
        self.assertEqual(self.portal.registry.list()[0]['path'],str(self.project.resolve()))
    def test_return_to_hub_and_close_editor_keep_session(self):
        self.identity();self.portal.open_workspace(self.project);self.portal.show_projects()
        self.assertTrue(self.portal.isVisible());self.assertFalse(self.portal.workspace.isVisible())
        self.portal.open_workspace(self.project);self.portal.workspace.close();APP.processEvents()
        self.assertTrue(self.portal.isVisible());self.assertIsNone(self.portal.workspace);self.assertTrue(self.client.token)
    def test_sign_out_saves_edits_and_locks_editor(self):
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace
        editor.annotation_items[0].notes='keep me';editor.annotation_dirty=True
        def logout():self.client.token=None;self.client.profile=None
        self.client.logout=Mock(side_effect=logout)
        self.portal.sign_out();self.wait();self.assertEqual(load_annotations(self.annotation_path).items[0].notes,'keep me')
        self.assertFalse(editor.isVisible());self.assertFalse(editor.isEnabled());self.assertEqual(self.portal.stack.currentIndex(),0)
    def test_failed_logout_does_not_pretend_session_was_revoked(self):
        self.identity();self.portal.open_workspace(self.project);self.client.logout=Mock(side_effect=ApiError('offline'))
        self.portal.sign_out();self.wait();self.assertTrue(self.client.token);self.assertTrue(self.portal.workspace.isVisible());self.assertIn('offline',self.portal.workspace.statusBar().currentMessage())
    def test_expired_session_hides_editor_and_blocks_reopening(self):
        self.identity();self.portal.open_workspace(self.project)
        self.client.json=Mock(side_effect=ApiError('expired',401));self.portal.verify_session();self.wait()
        self.assertFalse(self.portal.workspace.isVisible());self.assertTrue(self.portal._locked)
        self.portal.open_workspace(self.project);self.assertFalse(self.portal.workspace.isVisible())
    def test_offline_session_verification_cannot_bypass_gate(self):
        self.identity();self.portal.open_workspace(self.project);self.client.json=Mock(side_effect=ApiError('offline'))
        self.portal.verify_session();self.wait();self.assertEqual(self.portal.stack.currentIndex(),0);self.assertFalse(self.portal.workspace.isVisible())
    def test_api_401_notifies_gate_immediately(self):
        self.identity();self.portal.open_workspace(self.project)
        response=Mock();response.status_code=401;response.json.return_value={'detail':'Expired'}
        with patch('app.api_client.requests.request',return_value=response):
            with self.assertRaises(ApiError):self.client.projects=ApiClient.projects.__get__(self.client);self.client.projects()
        APP.processEvents();self.assertFalse(self.portal.workspace.isVisible());self.assertIsNone(self.client.token)
    def test_cloud_list_is_requested_only_with_identity(self):
        self.portal.source_tabs.setCurrentIndex(1);self.client.projects.assert_not_called()
        self.identity();self.wait();self.client.projects.assert_called()
    def test_new_project_rejects_nonempty_destination(self):
        self.identity();before=self.annotation_path.read_bytes()
        with patch('app.portal.QtWidgets.QFileDialog.getExistingDirectory',return_value=str(self.project)):
            self.portal.new_project()
        self.assertEqual(self.annotation_path.read_bytes(),before);self.assertIsNone(self.portal.workspace)
    def test_close_cleans_up_owned_backend(self):
        self.portal.close();self.runtime.close.assert_called()
    def test_locked_editor_with_invalid_pending_geometry_can_quit_with_recovery(self):
        from app.recovery import read_draft
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace
        editor._error=Mock();editor.select_annotation(1);editor.coords[0].setValue(9999)
        before=self.annotation_path.read_bytes();self.portal.lock('expired')
        self.assertTrue(self.portal.close());self.assertEqual(self.annotation_path.read_bytes(),before)
        draft=read_draft(self.project,self.project/'images_raw/page.png')
        self.assertEqual(draft['pending']['bbox'][0],9999)
    def test_invalid_pending_fields_can_be_saved_to_draft_before_sign_out(self):
        from app.recovery import read_draft
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace
        editor.select_annotation(1);editor.coords[0].setValue(9999)
        def logout():self.client.token=None;self.client.profile=None
        self.client.logout=Mock(side_effect=logout);self.portal.sign_out();self.wait()
        self.assertEqual(self.portal.stack.currentIndex(),0)
        self.assertEqual(read_draft(self.project,self.project/'images_raw/page.png')['pending']['bbox'][0],9999)
    def test_direct_editor_close_waits_for_account_transfer_worker(self):
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace;editor._error=Mock()
        transfer=QtWidgets.QDialog(editor);transfer.worker=Mock()
        self.assertFalse(editor.close());self.assertIs(self.portal.workspace,editor);editor._error.assert_called_once()
        transfer.worker=None;transfer.close()
    def test_different_identity_can_open_project_after_locked_invalid_editor(self):
        from app.recovery import read_draft
        self.identity();self.portal.open_workspace(self.project);old=self.portal.workspace;old._error=Mock()
        old.select_annotation(1);old.coords[0].setValue(9999);self.portal.lock('expired')
        self.identity('user-b');destination=self.root/'new-account-project';destination.mkdir()
        self.portal.open_workspace(destination)
        self.assertEqual(self.portal.workspace_user,'user-b');self.assertEqual(self.portal.workspace.root,destination.resolve())
        self.assertEqual(read_draft(self.project,self.project/'images_raw/page.png')['pending']['bbox'][0],9999)
    def test_failed_draft_write_is_reported_without_revoking_session(self):
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace
        editor.select_annotation(1);editor.coords[0].setValue(9999);self.client.logout=Mock()
        with patch.object(editor,'_checkpoint',side_effect=OSError('disk full')):self.portal.guard(self.portal.sign_out)
        self.client.logout.assert_not_called();self.assertTrue(editor.isVisible());self.assertIn('disk full',editor.statusBar().currentMessage())
        editor.discard_properties()
    def test_rejected_project_switch_keeps_correct_recent_folder(self):
        self.identity();self.portal.open_workspace(self.project);editor=self.portal.workspace;editor._error=Mock()
        editor.select_annotation(1);editor.coords[0].setValue(9999)
        other=self.root/'other';other.mkdir();self.portal.open_workspace(other)
        self.assertEqual(editor.root,self.project.resolve());self.assertEqual(self.portal.registry.list()[0]['path'],str(self.project.resolve()))
        editor.discard_properties()


class RegistryTests(unittest.TestCase):
    def test_recent_projects_are_isolated_per_account(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);project=root/'project';project.mkdir()
            a=ProjectRegistry(root/'state','google-a');b=ProjectRegistry(root/'state','google-b')
            a.add(project);self.assertEqual(len(a.list()),1);self.assertEqual(b.list(),[])
    def test_missing_folders_and_corrupt_registry_are_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);registry=ProjectRegistry(root,'google-a');registry.path.write_text('{broken')
            self.assertEqual(registry.list(),[])
            registry.path.write_text(json.dumps([{'path':str(root/'gone'),'title':'gone'}]));self.assertEqual(registry.list(),[])
