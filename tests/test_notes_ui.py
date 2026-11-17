from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6 import QtCore, QtWidgets
from app.workspace import WorkspaceWindow
from app.portal import PortalWindow
from app.api_client import ApiClient
from app.sharing_ui import SharingDialog
from app.portable import import_symbol_library, import_settings
from app.annotations import AnnotationFile, AnnotationItem, save_annotations
from test_portable_symbols import library, glyph
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_until_idle(obj, attribute):
    deadline=monotonic()+5
    while getattr(obj,attribute) is not None and monotonic()<deadline:
        APP.processEvents();QtCore.QThread.msleep(2)
    APP.processEvents()
    assert getattr(obj,attribute) is None


class NotesUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.workspace=WorkspaceWindow(self.root)
    def tearDown(self):
        wait_until_idle(self.workspace,'_task');self.workspace.close();APP.processEvents();self.temp.cleanup()
    def test_imported_catalog_has_samples_and_a_preview_without_source_scans(self):
        import_symbol_library(self.root,library())
        panel=self.workspace.catalog_panel;panel.refresh();wait_until_idle(self.workspace,'_task')
        self.assertEqual(panel.codes.rowCount(),1)
        self.assertEqual(panel.codes.item(0,3).text(),'1')
        self.assertEqual(panel.occurrences.rowCount(),0)
        self.assertFalse(panel.preview.pixmap().isNull())
        self.assertTrue(panel.transfer_buttons['import_library'].text())
        self.workspace.apply_language('sk')
        self.assertEqual(panel.transfer_buttons['export_library'].text(),'Exportovať knižnicu…')
    def test_library_recognition_is_undoable_from_review(self):
        glyph().save(self.root/'images_raw/page.png')
        save_annotations(self.root/'annotations/page.json',AnnotationFile('page.png',[
            AnnotationItem(1,'L1',None,[0,0,40,40],text_role='ciphertext'),
            AnnotationItem(2,'L2',1,[0,0,40,40]),AnnotationItem(3,'L3',2,[0,0,40,40])],4))
        import_symbol_library(self.root,library())
        self.workspace.refresh_images();self.workspace.image_list.setCurrentRow(0)
        self.workspace.digitization.recognize_library();wait_until_idle(self.workspace,'_task')
        self.assertEqual(self.workspace.annotation_items[2].symbol_code,'S001')
        self.workspace.undo();self.assertEqual(self.workspace.annotation_items[2].symbol_code,'')
    def test_ocr_does_not_require_a_symbol_catalog(self):
        glyph(True).save(self.root/'images_raw/page.png')
        save_annotations(self.root/'annotations/page.json',AnnotationFile('page.png',[
            AnnotationItem(1,'L1',None,[0,0,40,40],text_role='plaintext'),
            AnnotationItem(2,'L2',1,[0,0,40,40]),AnnotationItem(3,'L3',2,[0,0,40,40],element_type='readable')],4))
        self.workspace.refresh_images();self.workspace.image_list.setCurrentRow(0);self.workspace.ocr_path.setText('/local/test-model')
        with patch('app.jobs.LocalTextRecognizer',return_value=lambda image:'Handwritten text'),patch('app.symbol_catalog.occurrence_index') as catalog:
            self.workspace.digitization.recognize();wait_until_idle(self.workspace,'_task')
            catalog.assert_not_called()
        self.assertEqual(self.workspace.annotation_items[2].transcription,'Handwritten text')
    def test_expanded_automation_scrolls_at_small_window_size(self):
        glyph().save(self.root/'images_raw/page.png');self.workspace.refresh_images();self.workspace.image_list.setCurrentRow(0)
        self.workspace.resize(1100,720);self.workspace.show();self.workspace.center_tabs.setCurrentIndex(4)
        panel=self.workspace.digitization;panel.automation.setChecked(True);APP.processEvents()
        self.assertGreaterEqual(panel.threshold.height(),20)
        self.assertGreater(panel.automation_scroll.verticalScrollBar().maximum(),0)
        self.assertGreater(panel.table.horizontalHeader().minimumSectionSize(),0)
    def test_settings_actions_translate_and_roundtrip_current_values(self):
        from app.portable_ui import transfer_settings
        path=self.root/'exported.json'
        self.workspace.digitization.library_threshold.setValue(.93)
        with patch('app.portable_ui.QtWidgets.QFileDialog.getSaveFileName',return_value=(str(path),'JSON')):
            transfer_settings(self.workspace,False)
        self.assertEqual(json.loads(path.read_text())['models']['library_threshold'],.93)
        self.workspace.digitization.library_threshold.setValue(.8)
        with patch('app.portable_ui.QtWidgets.QFileDialog.getOpenFileName',return_value=(str(path),'JSON')):
            transfer_settings(self.workspace,True)
        self.assertEqual(self.workspace.digitization.library_threshold.value(),.93)
        self.workspace.apply_language('sk')
        self.assertEqual(self.workspace.workflow.settings_actions['import_settings'].text(),'Importovať nastavenia…')


class SharingUITests(unittest.TestCase):
    def setUp(self):
        self.client=Mock();self.client.shares.return_value=[{'email':'reader@example.com','user_id':'reader','role':'reader'}]
        self.project={'id':'doc','title':'Key','version':1,'visibility':'private','access_role':'owner'}
        self.dialog=SharingDialog(self.client,self.project)
        wait_until_idle(self.dialog,'worker')
    def tearDown(self):wait_until_idle(self.dialog,'worker');self.dialog.close();APP.processEvents()
    def test_share_update_and_revoke_use_server_routes(self):
        self.dialog.email.setText('new@example.com');self.dialog.role.setCurrentIndex(1);self.dialog.grant();wait_until_idle(self.dialog,'worker')
        self.client.share.assert_called_once_with(self.project,'new@example.com','editor')
        self.dialog.table.selectRow(0);self.dialog.remove();wait_until_idle(self.dialog,'worker')
        self.client.revoke_share.assert_called_once_with(self.project,'reader')
    def test_visibility_updates_keep_new_server_version(self):
        self.client.update_project.return_value={**self.project,'version':2,'visibility':'public'}
        self.dialog.visibility.setCurrentIndex(1);self.dialog.save_metadata();wait_until_idle(self.dialog,'worker')
        self.assertEqual(self.dialog.project['version'],2)
        self.client.update_project.assert_called_once_with(self.project,'Key','','public')
    def test_failure_does_not_claim_success(self):
        self.client.share.side_effect=RuntimeError('Recipient must sign in first')
        self.dialog.email.setText('new@example.com');self.dialog.grant();wait_until_idle(self.dialog,'worker')
        self.assertIn('sign in',self.dialog.status.text());self.assertTrue(self.dialog.invite.isEnabled())


class GlobalDocumentsUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.client=ApiClient();self.client.projects=Mock(return_value=[])
        self.portal=PortalWindow(runtime=Mock(),client=self.client,state_dir=self.root,autostart=False,session_store=Mock(has_record=Mock(return_value=False)))
        self.client.token='test';self.client.profile={'id':'user','name':'User','email':'u@example.com'}
        self.portal.enter_projects();wait_until_idle(self.portal,'worker')
    def tearDown(self):
        self.portal.search_timer.stop();wait_until_idle(self.portal,'worker');self.portal.close();APP.processEvents();self.temp.cleanup()
    def test_scopes_search_and_snapshot_filters_are_sent_to_server(self):
        self.portal.source_tabs.setCurrentIndex(2);wait_until_idle(self.portal,'worker')
        self.assertEqual(self.client.projects.call_args.kwargs['scope'],'public')
        self.portal.document_search.setText('archive');self.portal.snapshot_filter.setCurrentIndex(1);wait_until_idle(self.portal,'worker')
        filters=self.client.projects.call_args.kwargs
        self.assertEqual(filters['q'],'archive');self.assertIs(filters['has_snapshot'],True)
        self.portal.source_tabs.setCurrentIndex(3);wait_until_idle(self.portal,'worker')
        self.assertEqual(self.client.projects.call_args.kwargs['scope'],'shared')
    def test_reader_cannot_manage_access_and_no_snapshot_cannot_download(self):
        self.portal.source_tabs.setCurrentIndex(2);wait_until_idle(self.portal,'worker')
        self.portal.populate([{'id':'doc','title':'Public key','version':1,'visibility':'public','access_role':'reader','has_snapshot':False}])
        self.portal.table.selectRow(0);self.portal.controls()
        self.assertFalse(self.portal.access_button.isEnabled());self.assertFalse(self.portal.selected_button.isEnabled())
    def test_pagination_keeps_query(self):
        self.portal.source_tabs.setCurrentIndex(1);wait_until_idle(self.portal,'worker')
        self.portal.document_search.setText('key');self.portal.search_timer.stop()
        self.portal.document_has_next=True;self.portal.change_page(1);wait_until_idle(self.portal,'worker')
        self.assertEqual(self.client.projects.call_args.kwargs['offset'],100)
        self.assertEqual(self.client.projects.call_args.kwargs['q'],'key')
