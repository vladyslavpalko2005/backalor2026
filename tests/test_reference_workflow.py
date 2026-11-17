from __future__ import annotations
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from PyQt6 import QtCore,QtWidgets
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations,annotations_from_payload,annotations_payload
from app.annotation_ops import bulk_update,duplicate_subtree,reference_issues
from app.datasets import validate_annotations,export_bundle,import_bundle,export_coco
from app.digitization import structured_page,recognize_elements
from app.project import ensure_project_structure
from app.symbol_catalog import update_symbol,read_catalog,occurrence_index
from app.storage import SaveConflict
from app.workspace import WorkspaceWindow
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def fixture(image='page.png'):
    return AnnotationFile(image,[
        AnnotationItem(1,'L1',None,[0,0,280,180],label='Section'),
        AnnotationItem(2,'L2',1,[10,10,200,100],label='Pair'),
        AnnotationItem(3,'L3',2,[20,20,30,20],label='Letters',transcription='A',text_role='plaintext',element_type='readable',reviewed=True),
        AnnotationItem(4,'L3',2,[65,20,20,20],label='Signs',symbol_code='S001',text_role='ciphertext',element_type='cipher_symbol',transcription_ref_id=3,reviewed=True)],5)


class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        self.data=fixture();Image.new('RGB',(300,200),'white').save(self.root/'images_raw/page.png')
        save_annotations(self.root/'annotations/page.json',self.data)
    def tearDown(self):self.temp.cleanup()
    def test_version_four_roundtrip_and_v3_default(self):
        self.assertEqual(load_annotations(self.root/'annotations/page.json'),self.data)
        payload=annotations_payload(self.data);self.assertEqual(payload['schema_version'],4)
        payload['schema_version']=3
        for item in payload['items']:item.pop('transcription_ref_id')
        self.assertIsNone(annotations_from_payload(payload).items[3].transcription_ref_id)
    def test_valid_reference_is_exported_with_resolved_text(self):
        self.assertEqual(reference_issues(self.data.items[3],self.data.items),[])
        pair=structured_page(self.data,(300,200))['pairs'][0]
        self.assertEqual(pair['status'],'ready');self.assertEqual(pair['ciphertext'][0]['linked_transcription'],'A')
        coco=export_coco(self.root,self.root/'coco.json')
        attrs=coco['annotations'][3]['attributes'];self.assertEqual(attrs['transcription_ref_id'],3);self.assertEqual(attrs['transcription_ref_annotation_id'],3)
    def test_dangling_wrong_type_self_and_cross_pair_references_fail_validation(self):
        for target_id in (999,4,2):
            with self.subTest(target_id=target_id):
                self.data.items[3].transcription_ref_id=target_id
                self.assertTrue(reference_issues(self.data.items[3],self.data.items))
                self.assertTrue(any('invalid_transcription_reference' in item for item in validate_annotations(self.data,(300,200))))
                self.assertEqual(structured_page(self.data,(300,200))['pairs'][0]['status'],'draft')
        self.data.items[3].transcription_ref_id=3;self.data.items[2].parent_id=1
        self.assertTrue(reference_issues(self.data.items[3],self.data.items))
    def test_target_must_be_readable_plaintext(self):
        self.data.items[2].text_role='ciphertext'
        self.assertTrue(reference_issues(self.data.items[3],self.data.items))
    def test_bulk_edit_is_atomic_and_resets_dependent_review(self):
        before=copy.deepcopy(self.data.items)
        result,count=bulk_update(before,{3},{'text_role':'ciphertext','label':'Numbers'})
        self.assertEqual(count,1);self.assertEqual(result[2].label,'Numbers')
        self.assertFalse(result[2].reviewed);self.assertFalse(result[3].reviewed);self.assertEqual(before,self.data.items)
    def test_caption_only_bulk_change_preserves_review(self):
        result,count=bulk_update(self.data.items,{3,4},{'label':'Alphabet'})
        self.assertEqual(count,2);self.assertTrue(result[2].reviewed);self.assertTrue(result[3].reviewed)
    def test_invalid_bulk_selection_or_type_leaves_source_unchanged(self):
        before=copy.deepcopy(self.data.items)
        for ids,changes in [({1,3},{'element_type':'readable'}),({999},{'label':'x'}),({3},{'element_type':'cat'}),({3},{'bbox':[]})]:
            with self.subTest(ids=ids,changes=changes),self.assertRaises(ValueError):bulk_update(self.data.items,ids,changes)
        self.assertEqual(self.data.items,before)
    def test_bulk_clear_legacy_role_and_type(self):
        self.data.items[2].text_role='';self.data.items[2].kind='plaintext'
        result,_=bulk_update(self.data.items,{3},{'text_role':''})
        self.assertEqual(result[2].text_role,'');self.assertEqual(result[2].kind,'')
    def test_type_change_clears_source_link(self):
        result,_=bulk_update(self.data.items,{4},{'element_type':'readable'})
        self.assertIsNone(result[3].transcription_ref_id);self.assertEqual(result[3].symbol_code,'S001')
    def test_duplicate_pair_remaps_children_and_internal_links(self):
        result,selected=duplicate_subtree(self.data.items,2,(300,200))
        self.assertEqual(len(result),7);self.assertEqual(selected,5)
        self.assertEqual(result[-1].parent_id,selected);self.assertEqual(result[-1].transcription_ref_id,result[-2].id)
        self.assertFalse(result[-1].reviewed);self.assertEqual(validate_annotations(AnnotationFile('page.png',result,8),(300,200)),[])
    def test_duplicate_symbol_preserves_same_pair_target(self):
        result,selected=duplicate_subtree(self.data.items,4,(300,200))
        self.assertEqual(result[-1].transcription_ref_id,3);self.assertEqual(result[-1].parent_id,2)
    def test_duplicate_outside_bounds_is_rejected_without_mutation(self):
        before=copy.deepcopy(self.data.items)
        with self.assertRaises(ValueError):duplicate_subtree(self.data.items,2,(300,200),dx=300)
        self.assertEqual(self.data.items,before)
    def test_ocr_invalidates_review_of_linked_symbol(self):
        self.data.items[2].transcription=''
        result,_=recognize_elements(Image.new('RGB',(300,200)),self.data.items,text_recognizer=lambda image:'B')
        self.assertEqual(result[2].transcription,'B');self.assertFalse(result[3].reviewed)
    def test_catalog_preserves_metadata_and_has_backup(self):
        initial={'title':'Project','image_groups':{'page.png':'doc-a'}}
        path=self.root/'project.json';path.write_text(json.dumps(initial));before=path.read_bytes()
        update_symbol(self.root,'S001','Cross','historical',{'image':'page.png','annotation_id':4})
        current=json.loads(path.read_text());self.assertEqual(current['title'],'Project');self.assertEqual(current['image_groups'],initial['image_groups'])
        self.assertEqual(path.with_suffix('.json.bak').read_bytes(),before);self.assertEqual(read_catalog(self.root)['S001']['title'],'Cross')
    def test_invalid_catalog_representative_is_rejected(self):
        for rep in [{'image':'../page.png','annotation_id':4},{'image':'page.png','annotation_id':3}]:
            with self.subTest(rep=rep),self.assertRaises(ValueError):update_symbol(self.root,'S001',representative=rep)
        self.assertFalse((self.root/'project.json').exists())
    def test_invalid_catalog_shape_is_rejected_before_rendering(self):
        for catalog in ({'S001':None},{'S001':{'title':7}},{'S001':{'representative':{'image':'page.png'}}}):
            (self.root/'project.json').write_text(json.dumps({'symbol_catalog':catalog}))
            with self.subTest(catalog=catalog),self.assertRaises(ValueError):read_catalog(self.root)
    def test_catalog_conflict_keeps_original_metadata(self):
        path=self.root/'project.json';path.write_text('{"title":"Keep"}');before=path.read_bytes()
        with patch('app.symbol_catalog.file_revision',side_effect=['revision-1','revision-2']):
            with self.assertRaises(SaveConflict):update_symbol(self.root,'S001')
        self.assertEqual(path.read_bytes(),before)
    def test_occurrences_group_across_pages_and_catalog_deletion_preserves_codes(self):
        Image.new('RGB',(300,200)).save(self.root/'images_raw/other.png');save_annotations(self.root/'annotations/other.json',fixture('other.png'))
        update_symbol(self.root,'S001','Symbol');before=(self.root/'annotations/page.json').read_bytes()
        self.assertEqual(len(occurrence_index(self.root)['occurrences']['S001']),2)
        update_symbol(self.root,'S001',delete=True)
        self.assertNotIn('S001',read_catalog(self.root));self.assertEqual((self.root/'annotations/page.json').read_bytes(),before)
        self.assertEqual(len(occurrence_index(self.root)['occurrences']['S001']),2)
    def test_corrupt_annotation_is_reported_and_other_occurrences_survive(self):
        Image.new('RGB',(300,200)).save(self.root/'images_raw/other.png');(self.root/'annotations/other.json').write_text('{bad')
        index=occurrence_index(self.root);self.assertEqual(len(index['occurrences']['S001']),1);self.assertTrue(index['failures'])
    def test_catalog_and_reference_survive_project_zip(self):
        update_symbol(self.root,'S001','Symbol',representative={'image':'page.png','annotation_id':4})
        export_bundle(self.root,self.root/'bundle.zip');dest=self.root/'imported';import_bundle(self.root/'bundle.zip',dest)
        self.assertEqual(read_catalog(dest),read_catalog(self.root));self.assertEqual(load_annotations(dest/'annotations/page.json'),self.data)
        from app.digitization import build_key
        self.assertEqual(build_key(dest)['symbol_catalog']['S001']['title'],'Symbol')


class ReferenceWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        Image.new('RGB',(300,200),'white').save(self.root/'images_raw/page.png');save_annotations(self.root/'annotations/page.json',fixture())
        self.window=WorkspaceWindow(self.root);self.errors=[];self.window._error=self.errors.append
        APP.processEvents();self.window.select_annotation(4)
    def wait(self):
        deadline=monotonic()+8
        while self.window._task is not None and monotonic()<deadline:APP.processEvents();QtCore.QThread.msleep(2)
        APP.processEvents();self.assertIsNone(self.window._task);self.assertFalse(self.errors,self.errors)
    def tearDown(self):self.wait();self.window.close();APP.processEvents();self.temp.cleanup()
    def test_tree_has_real_hierarchy_and_deferred_selection(self):
        tree=self.window.hierarchy_panel
        self.assertEqual(tree.tree.topLevelItemCount(),1);self.assertEqual(tree.nodes[2].childCount(),2)
        tree.tree.setCurrentItem(tree.nodes[3]);APP.processEvents();APP.processEvents()
        self.assertEqual(self.window._active_annotation,3)
    def test_tree_search_keeps_ancestors_visible(self):
        panel=self.window.hierarchy_panel;panel.search.setText('S001')
        self.assertFalse(panel.nodes[1].isHidden());self.assertFalse(panel.nodes[2].isHidden());self.assertFalse(panel.nodes[4].isHidden());self.assertTrue(panel.nodes[3].isHidden())
    def test_property_caption_reference_persistence_and_undo(self):
        self.assertEqual(self.window.reference_combo.currentData(),3)
        self.window.fields['caption'].setText('Named group');self.window.reference_combo.setCurrentIndex(0);self.window.apply_properties()
        self.window.save_annotations_current(silent=True)
        item=load_annotations(self.root/'annotations/page.json').items[3]
        self.assertIsNone(item.transcription_ref_id);self.assertEqual(item.label,'Named group')
        self.window.undo();self.assertEqual(self.window.annotation_items[3].transcription_ref_id,3)
    def test_duplicate_branch_is_one_undo_step(self):
        self.window.select_annotation(2);self.window.duplicate_current_annotation();self.assertEqual(len(self.window.annotation_items),7)
        self.window.undo();self.assertEqual(len(self.window.annotation_items),4);self.assertEqual(self.window.hierarchy_panel.nodes[2].childCount(),2)
    def test_manual_text_edit_invalidates_linked_symbol_review(self):
        self.window.select_annotation(3);self.window.fields['transcription'].setText('B');self.window.apply_properties()
        self.assertFalse(self.window.annotation_items[3].reviewed)
    def test_reference_and_caption_in_recovery_draft(self):
        from app.recovery import read_draft
        self.window.fields['caption'].setText('Pending');self.window._property_modified();self.window._checkpoint()
        draft=read_draft(self.root,self.window.current_image_path)
        self.assertEqual(draft['pending']['caption'],'Pending');self.assertEqual(draft['pending']['transcription_ref_id'],3)
    def test_catalog_load_preview_and_open_occurrence(self):
        panel=self.window.catalog_panel;panel.refresh();self.wait()
        self.assertEqual(panel.codes.rowCount(),1);self.assertEqual(panel.occurrences.rowCount(),1)
        self.assertFalse(panel.preview.pixmap().isNull())
        panel.open_occurrence();APP.processEvents();self.assertEqual(self.window._active_annotation,4);self.assertEqual(self.window.center_tabs.currentIndex(),1)
    def test_bulk_dialog_selected_rows_apply_and_undo(self):
        panel=self.window.digitization;panel.refresh()
        panel.table.selectAll()
        def interact(dialog):
            for check in dialog.findChildren(QtWidgets.QCheckBox):
                if check.text()==self.window.text('code'):check.setChecked(True)
            edits=dialog.findChildren(QtWidgets.QLineEdit);edits[-1].setText('S009')
            return QtWidgets.QDialog.DialogCode.Accepted
        with patch('app.digitization_ui.QtWidgets.QDialog.exec',interact):panel.bulk_edit()
        self.assertEqual([item.symbol_code for item in self.window.annotation_items if item.level=='L3'],['S009','S009'])
        self.window.undo();self.assertEqual(self.window.annotation_items[2].symbol_code,'');self.assertEqual(self.window.annotation_items[3].symbol_code,'S001')
    def test_odd_width_previews_preserve_pixels_without_row_padding(self):
        for mode in ('RGB','RGBA','L'):
            with self.subTest(mode=mode):
                image=Image.new(mode,(7,9))
                for y in range(image.height):
                    for x in range(image.width):
                        value=(x*30,y*25,90) if mode=='RGB' else (x*30,y*25,90,180) if mode=='RGBA' else y*20+x
                        image.putpixel((x,y),value)
                qimage=self.window._pil_to_qimage(image)
                for y in range(image.height):
                    for x in range(image.width):
                        actual=qimage.pixelColor(x,y);expected=image.getpixel((x,y))
                        if mode=='L':self.assertEqual(actual.red(),expected)
                        else:
                            self.assertEqual((actual.red(),actual.green(),actual.blue()),expected[:3])
                            if mode=='RGBA':self.assertEqual(actual.alpha(),expected[3])
