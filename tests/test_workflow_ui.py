from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from PyQt6 import QtCore,QtWidgets
from app.workspace import WorkspaceWindow
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations
from app.project import ensure_project_structure
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class WorkflowUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        Image.new('RGB',(300,200),'white').save(self.root/'images_raw/page.png')
        save_annotations(self.root/'annotations/page.json',AnnotationFile('page.png',[
            AnnotationItem(1,'L1',None,[0,0,280,180]),AnnotationItem(2,'L2',1,[10,10,220,130]),
            AnnotationItem(3,'L3',2,[20,20,30,20],text_role='plaintext',element_type='readable',transcription='A',reviewed=True),
            AnnotationItem(4,'L3',2,[65,20,20,20],text_role='ciphertext',element_type='cipher_symbol',symbol_code='S001')],5))
        self.window=WorkspaceWindow(self.root);self.errors=[];self.window._error=self.errors.append
        self.window.show();APP.processEvents()
    def tearDown(self):self.window.close();APP.processEvents();self.temp.cleanup()
    def test_models_are_reachable_through_tools_with_stable_indices(self):
        self.assertFalse(self.window.center_tabs.isTabVisible(3))
        self.window.workflow.model_action.trigger();self.assertEqual(self.window.center_tabs.currentIndex(),3);self.assertTrue(self.window.center_tabs.isTabVisible(3))
        self.window.center_tabs.setCurrentIndex(4);self.assertFalse(self.window.center_tabs.isTabVisible(3));self.assertEqual(self.window.center_tabs.count(),5)
    def test_selection_is_default_and_drawing_is_explicit(self):
        self.assertFalse(self.window.draw_action.isChecked());self.assertFalse(self.window.annotation_canvas._drawing_enabled)
        self.window.mode_combo.setCurrentIndex(0);self.assertTrue(self.window.annotation_canvas._drawing_enabled)
    def test_tree_stays_visible_while_properties_are_open(self):
        self.window.center_tabs.setCurrentIndex(1);self.window._select_from_canvas(4);APP.processEvents()
        self.assertEqual(self.window.hierarchy_panel.parentWidget(),self.window.image_list.parentWidget())
        self.assertTrue(self.window.hierarchy_panel.isVisible());self.assertEqual(self.window.inspector_tabs.currentIndex(),1)
        self.assertTrue(self.window.properties.isVisible());self.assertFalse(self.window.inspector_tabs.tabBar().isVisible())
    def test_advanced_coordinates_remain_editable_and_saveable(self):
        self.window.select_annotation(3);self.assertFalse(self.window.workflow.advanced.isChecked())
        self.window.workflow.advanced.setChecked(True);self.window.coords[0].setValue(22);self.window.apply_properties();self.window.save_annotations_current(silent=True)
        self.assertEqual(load_annotations(self.root/'annotations/page.json').items[2].bbox[0],22)
    def test_properties_show_the_fields_for_current_element_type(self):
        self.window.select_annotation(3);self.assertFalse(self.window.fields['transcription'].isHidden());self.assertTrue(self.window.fields['code'].isHidden())
        self.window.select_annotation(4);self.assertTrue(self.window.fields['transcription'].isHidden());self.assertFalse(self.window.fields['code'].isHidden());self.assertFalse(self.window.reference_combo.isHidden())
    def test_type_change_updates_properties_before_apply(self):
        self.window.select_annotation(3);self.window.type_combo.setCurrentIndex(self.window.type_combo.findData('cipher_symbol'))
        self.assertFalse(self.window.fields['code'].isHidden());self.assertTrue(self.window.fields['transcription'].isHidden())
    def test_review_filters_and_next_issue_focus_correct_frame(self):
        self.window.center_tabs.setCurrentIndex(4);panel=self.window.digitization
        self.assertFalse(panel.automation.isChecked())
        panel.filter_combo.setCurrentIndex(panel.filter_combo.findData('unreviewed'))
        self.assertTrue(panel.table.isRowHidden(0));self.assertFalse(panel.table.isRowHidden(1))
        before=self.window.annotation_canvas.transform().m11();panel.next_issue();APP.processEvents()
        self.assertEqual(self.window._active_annotation,4);self.assertEqual(self.window.center_tabs.currentIndex(),1);self.assertFalse(self.window.annotation_canvas._fitted)
        self.assertNotEqual(self.window.annotation_canvas.transform().m11(),before);self.assertFalse(self.window.annotation_items[3].reviewed)
    def test_incomplete_filter_excludes_complete_but_unreviewed_element(self):
        self.window.center_tabs.setCurrentIndex(4);panel=self.window.digitization
        panel.filter_combo.setCurrentIndex(panel.filter_combo.findData('incomplete'))
        self.assertTrue(panel.table.isRowHidden(0));self.assertTrue(panel.table.isRowHidden(1))
        self.window.annotation_items[3].symbol_code='';panel.refresh();self.assertFalse(panel.table.isRowHidden(1))
    def test_global_export_routes_to_existing_key_export(self):
        with patch.object(self.window.digitization,'export') as export:self.window.workflow.key_action.trigger();export.assert_called_once()
    def test_page_flow_continues_to_annotation_then_review(self):
        self.window.workflow.advance();self.assertEqual(self.window.center_tabs.currentIndex(),1)
        self.window.workflow.advance();self.assertEqual(self.window.center_tabs.currentIndex(),4)
    def test_level_picker_and_existing_shortcuts_share_state(self):
        self.window.workflow.level.setCurrentIndex(2);self.assertEqual(self.window.annotation_level,'L3')
        self.window.level_l2.setChecked(True);self.assertEqual(self.window.workflow.level.currentIndex(),1);self.assertEqual(self.window.annotation_level,'L2')
    def test_account_header_reflects_current_session(self):
        self.window.api_client.profile={'name':'Test Person','email':'test@example.com'}
        self.window.account_action.setText('Account · Test Person');self.assertEqual(self.window.workflow.account.text(),'Test')
    def test_help_is_inline_and_can_be_closed(self):
        self.window.workflow.help_action.setChecked(True);self.assertTrue(self.window.workflow.help_text.isVisible())
        self.window.workflow.help_action.setChecked(False);self.assertFalse(self.window.workflow.help_text.isVisible())


class EmptyWorkflowTests(unittest.TestCase):
    def test_empty_project_offers_import_and_disables_annotation_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=WorkspaceWindow(Path(tmp));window.show();APP.processEvents()
            self.assertTrue(window.workflow.empty.isVisible());self.assertFalse(window.pipeline_panel.isVisible())
            self.assertFalse(window.center_tabs.isTabEnabled(1));self.assertFalse(window.workflow.next_button.isVisible())
            window.close();APP.processEvents()
