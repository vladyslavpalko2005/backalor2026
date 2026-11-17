from __future__ import annotations
import copy
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from PyQt6 import QtCore, QtWidgets
from app.annotations import AnnotationFile, AnnotationItem, annotations_from_payload, annotations_payload, load_annotations, save_annotations
from app.digitization import (effective_role,effective_type,classify_elements,recognize_elements,
    structured_page,export_key,build_key,export_classification_dataset,LocalClassifier)
from app.project import ensure_project_structure
from app.datasets import export_coco,export_bundle,import_bundle
from app.workspace import WorkspaceWindow
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def example(image='page.png'):
    return AnnotationFile(image,[
        AnnotationItem(1,'L1',None,[0,0,100,80]),
        AnnotationItem(2,'L2',1,[5,5,90,60]),
        AnnotationItem(3,'L3',2,[10,10,20,20],text_role='plaintext',element_type='readable',transcription='A',reviewed=True),
        AnnotationItem(4,'L3',2,[40,10,20,20],text_role='ciphertext',element_type='cipher_symbol',symbol_code='S001',reviewed=True)],5)


class DigitizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        self.image=Image.new('RGB',(100,80),'white');self.image.save(self.root/'images_raw/page.png')
        self.data=example();save_annotations(self.root/'annotations/page.json',self.data)
    def tearDown(self):self.temp.cleanup()
    def test_v3_roundtrip_and_legacy_semantics(self):
        self.assertEqual(load_annotations(self.root/'annotations/page.json'),self.data)
        legacy=annotations_payload(self.data);legacy['schema_version']=2
        legacy['items'][2].pop('text_role');legacy['items'][2].pop('element_type');legacy['items'][2]['kind']='ciphertext'
        item=annotations_from_payload(legacy).items[2]
        self.assertEqual(effective_role(item,[item]),'ciphertext');self.assertEqual(effective_type(item),'')
        item.kind='symbol';self.assertEqual(effective_type(item),'cipher_symbol');self.assertEqual(effective_role(item,[item]),'')
    def test_explicit_role_overrides_inherited_role(self):
        parent=self.data.items[1];parent.text_role='plaintext';child=self.data.items[3]
        self.assertEqual(effective_role(child,self.data.items),'ciphertext')
        child.text_role='';self.assertEqual(effective_role(child,self.data.items),'plaintext')
    def test_inheritance_cycle_is_bounded(self):
        self.data.items[0].parent_id=2
        self.assertEqual(effective_role(self.data.items[0],self.data.items),'')
    def test_type_prediction_fills_only_unknown_and_is_unreviewed(self):
        self.data.items[2].element_type=''
        model=Mock(return_value=('readable',.95))
        result,counts=classify_elements(self.image,self.data.items,model)
        self.assertEqual(counts,{'changed':1,'uncertain':0,'skipped':1});model.assert_called_once()
        self.assertEqual(result[2].element_type,'readable');self.assertFalse(result[2].reviewed)
        self.assertEqual(result[2].type_confidence,.95);self.assertEqual(self.data.items[2].element_type,'')
    def test_low_confidence_is_not_assigned(self):
        self.data.items[2].element_type=''
        result,counts=classify_elements(self.image,self.data.items,lambda image:('readable',.5))
        self.assertEqual(result[2].element_type,'');self.assertEqual(counts['uncertain'],1)
    def test_invalid_scores_and_classes_rejected(self):
        self.data.items[2].element_type=''
        for value in [('person',.99),('readable',float('nan')),('readable',1.2)]:
            with self.subTest(value=value),self.assertRaises(ValueError):classify_elements(self.image,self.data.items,lambda image:value)
    def test_routes_readable_ciphertext_to_ocr_and_symbols_to_identifier(self):
        self.data.items[2].text_role='ciphertext';self.data.items[2].transcription='';self.data.items[3].symbol_code=''
        text=Mock(return_value=' 123 ');symbol=Mock(return_value=('S002',.99))
        result,counts=recognize_elements(self.image,self.data.items,text,symbol)
        self.assertEqual(result[2].transcription,'123');self.assertIsNone(result[2].recognition_confidence)
        self.assertEqual(result[3].symbol_code,'S002');self.assertEqual(result[3].recognition_confidence,.99)
        self.assertEqual(counts['changed'],2);self.assertFalse(result[3].reviewed)
        text.assert_called_once();symbol.assert_called_once()
    def test_existing_transcription_and_codes_preserved(self):
        text=Mock();symbol=Mock();result,counts=recognize_elements(self.image,self.data.items,text,symbol)
        self.assertEqual(result,self.data.items);text.assert_not_called();symbol.assert_not_called();self.assertEqual(counts['skipped'],2)
    def test_unknown_type_never_runs_ocr(self):
        self.data.items[2].element_type='';self.data.items[2].transcription=''
        text=Mock();recognize_elements(self.image,self.data.items,text_recognizer=text);text.assert_not_called()
    def test_recognition_failure_cannot_partially_modify_annotations(self):
        self.data.items[2].transcription='';self.data.items[3].symbol_code='';before=copy.deepcopy(self.data)
        with self.assertRaises(RuntimeError):recognize_elements(self.image,self.data.items,lambda image:'new',Mock(side_effect=RuntimeError('failed')))
        self.assertEqual(self.data,before)
    def test_empty_ocr_and_low_symbol_confidence_are_unresolved(self):
        self.data.items[2].transcription='';self.data.items[3].symbol_code=''
        result,counts=recognize_elements(self.image,self.data.items,lambda image:'',lambda image:('S002',.2))
        self.assertEqual(counts['uncertain'],2);self.assertEqual(result,self.data.items)
    def test_invalid_crop_is_rejected(self):
        self.data.items[2].element_type='';self.data.items[2].bbox=[99,0,20,20]
        with self.assertRaises(ValueError):classify_elements(self.image,self.data.items,lambda image:('readable',1))
    def test_ready_key_and_non_bijective_pair_are_preserved(self):
        self.data.items.append(AnnotationItem(5,'L3',2,[65,10,10,20],text_role='ciphertext',element_type='readable',transcription='42',reviewed=True))
        payload=structured_page(self.data,self.image.size)
        self.assertEqual(payload['pairs'][0]['status'],'ready');self.assertEqual(len(payload['pairs'][0]['ciphertext']),2)
    def test_unreviewed_or_unassigned_element_keeps_pair_draft(self):
        self.data.items[3].reviewed=False;self.data.items[3].text_role=''
        pair=structured_page(self.data,self.image.size)['pairs'][0]
        self.assertEqual(pair['status'],'draft');self.assertEqual(len(pair['unassigned']),1);self.assertIn('missing_ciphertext',pair['issues'])
    def test_geometry_problems_never_export_ready(self):
        self.data.items[2].bbox=[98,0,20,20]
        page=structured_page(self.data,self.image.size)
        self.assertTrue(page['issues']);self.assertEqual(page['pairs'][0]['status'],'draft')
    def test_json_csv_and_missing_annotation_page(self):
        self.assertEqual(build_key(self.root)['status'],'ready')
        Image.new('RGB',(100,80)).save(self.root/'images_raw/other.png')
        payload=export_key(self.root,self.root/'key.json');self.assertEqual(payload['status'],'draft')
        self.assertTrue(any('missing_annotations' in page['issues'] for page in payload['pages']))
        export_key(self.root,self.root/'key.csv')
        with (self.root/'key.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        row=next(row for row in rows if row['image']=='page.png')
        self.assertEqual(json.loads(row['plaintext'])[0]['transcription'],'A')
        self.assertTrue(any('missing_annotations' in row['issues'] for row in rows))
    def test_mismatched_image_and_orphan_are_visible_and_not_ready(self):
        self.data.image='wrong.png';self.data.items[3].parent_id=999
        save_annotations(self.root/'annotations/page.json',self.data)
        payload=export_key(self.root,self.root/'key.json');page=payload['pages'][0]
        self.assertEqual(payload['status'],'draft');self.assertIn('annotation_image_mismatch',page['issues'])
        self.assertEqual(page['unpaired_elements'][0]['id'],4)
    def test_coco_and_project_zip_preserve_semantics(self):
        coco=export_coco(self.root,self.root/'coco.json')
        self.assertEqual(coco['annotations'][2]['attributes']['text_role'],'plaintext')
        export_bundle(self.root,self.root/'bundle.zip');dest=self.root/'imported';import_bundle(self.root/'bundle.zip',dest)
        self.assertEqual(load_annotations(dest/'annotations/page.json'),self.data)
    def test_classification_model_rejects_detection_weights_and_bad_class_names(self):
        path=self.root/'model.pt';path.touch()
        for task,names in [('detect',{0:'readable',1:'cipher_symbol'}),('classify',{0:'cat'})]:
            with self.subTest(task=task),patch.dict('sys.modules',{'ultralytics':SimpleNamespace(YOLO=lambda _:SimpleNamespace(task=task,names=names))}):
                with self.assertRaises(ValueError):LocalClassifier(path,expected_types=True)
    def test_classification_dataset_has_disjoint_document_splits(self):
        for index in range(1,6):
            name=f'page{index}.png';self.image.save(self.root/'images_raw'/name)
            save_annotations(self.root/'annotations'/f'page{index}.json',example(name))
        count=export_classification_dataset(self.root,self.root/'dataset')
        manifest=json.loads((self.root/'dataset/manifest.json').read_text());self.assertEqual(count,12)
        groups=[{item['document'] for item in manifest['samples'] if item['file'].startswith(subset+'/')} for subset in ('train','val','test')]
        self.assertFalse(groups[0]&groups[1]);self.assertFalse(groups[1]&groups[2]);self.assertFalse(groups[0]&groups[2])
        self.assertEqual(set(manifest['classes']),{'readable','cipher_symbol'})
    def test_no_dataset_from_unreviewed_or_too_few_documents(self):
        with self.assertRaises(ValueError):export_classification_dataset(self.root,self.root/'dataset')
        self.assertFalse((self.root/'dataset').exists())
    def test_unknown_task_and_nonempty_destination_rejected(self):
        with self.assertRaises(ValueError):export_classification_dataset(self.root,self.root,'types')
        with self.assertRaises(ValueError):export_classification_dataset(self.root,self.root/'dataset','unknown')


class DigitizationWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        Image.new('RGB',(100,80),'white').save(self.root/'images_raw/page.png')
        save_annotations(self.root/'annotations/page.json',example())
        self.window=WorkspaceWindow(self.root);self.errors=[];self.window._error=self.errors.append
        self.window.select_annotation(3);APP.processEvents()
    def tearDown(self):self.window.close();APP.processEvents();self.temp.cleanup()
    def test_tab_lists_roles_types_and_manual_review(self):
        panel=self.window.digitization;panel.refresh();self.assertEqual(panel.table.rowCount(),2)
        self.assertEqual(self.window.center_tabs.count(),5)
        self.window.annotation_items[2].reviewed=False;panel.refresh();panel.table.selectRow(0);panel.review()
        self.assertTrue(self.window.annotation_items[2].reviewed)
    def test_property_changes_persist_invalidate_review_and_undo(self):
        self.window.role_combo.setCurrentIndex(self.window.role_combo.findData('ciphertext'))
        self.window.type_combo.setCurrentIndex(self.window.type_combo.findData('cipher_symbol'))
        self.window.fields['code'].setText('S002');self.window.apply_properties()
        item=self.window.annotation_items[2];self.assertEqual((item.text_role,item.element_type),('ciphertext','cipher_symbol'));self.assertFalse(item.reviewed)
        self.window.save_annotations_current(silent=True)
        self.assertEqual(load_annotations(self.root/'annotations/page.json').items[2],item)
        self.window.undo();self.assertEqual(self.window.annotation_items[2].text_role,'plaintext');self.assertTrue(self.window.annotation_items[2].reviewed)
    def test_changing_parent_role_invalidates_child_review(self):
        self.window.select_annotation(2);self.window.role_combo.setCurrentIndex(self.window.role_combo.findData('ciphertext'));self.window.apply_properties()
        self.assertFalse(self.window.annotation_items[2].reviewed);self.assertFalse(self.window.annotation_items[3].reviewed)
    def test_clearing_legacy_role_is_possible(self):
        self.window.annotation_items[2].kind='plaintext';self.window.annotation_items[2].text_role=''
        self.window.select_annotation(3);self.window.role_combo.setCurrentIndex(0);self.window.apply_properties()
        self.assertEqual(effective_role(self.window.annotation_items[2],self.window.annotation_items),'')
    def test_recovery_contains_pending_role_and_type(self):
        from app.recovery import read_draft
        self.window.type_combo.setCurrentIndex(self.window.type_combo.findData('cipher_symbol'))
        self.window.role_combo.setCurrentIndex(self.window.role_combo.findData('ciphertext'))
        self.window._checkpoint();draft=read_draft(self.root,self.window.current_image_path)
        self.assertEqual(draft['pending']['text_role'],'ciphertext');self.assertEqual(draft['pending']['element_type'],'cipher_symbol')
    def test_classification_snapshot_applies_as_one_undoable_action(self):
        panel=self.window.digitization;self.window.annotation_items[2].element_type=''
        items,counts=classify_elements(Image.new('RGB',(100,80)),self.window.annotation_items,lambda image:('readable',.99))
        panel.complete((items,counts));self.assertEqual(self.window.annotation_items[2].type_source,'model');self.assertFalse(self.window.annotation_items[2].reviewed)
        self.window.undo();self.assertEqual(self.window.annotation_items[2].type_source,'')
        self.assertEqual(panel.table.rowCount(),2)
    def test_incomplete_element_cannot_be_confirmed(self):
        panel=self.window.digitization;self.window.annotation_items[2].text_role='';self.window.annotation_items[2].reviewed=False
        panel.refresh();panel.table.selectRow(0);panel.review();self.assertFalse(self.window.annotation_items[2].reviewed)
    def test_type_and_symbol_model_paths_saved(self):
        panel=self.window.digitization;panel.model_fields['type_model'].setText('/tmp/types.pt');panel.model_fields['symbol_model'].setText('/tmp/symbols.pt');panel.threshold.setValue(.92)
        self.window.save_model_settings();panel.model_fields['type_model'].clear();self.window._load_model_settings()
        self.assertEqual(panel.model_fields['type_model'].text(),'/tmp/types.pt');self.assertEqual(panel.threshold.value(),.92)
    def test_ocr_does_not_process_cipher_symbol(self):
        self.window.select_annotation(4)
        with patch('app.workspace.recognize_text') as recognizer:self.window.run_ocr();recognizer.assert_not_called()
        self.assertTrue(self.errors)
    def test_page_change_refreshes_digitization_rows(self):
        Image.new('RGB',(100,80)).save(self.root/'images_raw/other.png')
        self.window.refresh_images();self.window.center_tabs.setCurrentIndex(4)
        for index in range(self.window.image_list.count()):
            item=self.window.image_list.item(index)
            if item.text()=='other.png':self.window.image_list.setCurrentItem(item)
        APP.processEvents();self.assertEqual(self.window.digitization.table.rowCount(),0)
