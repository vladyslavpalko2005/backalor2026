from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image, ImageDraw
from app.annotations import AnnotationFile, AnnotationItem, save_annotations
from app.project import ensure_project_structure
from app.portable import (build_symbol_library, export_symbol_library, import_symbol_library,
                          encode_sample, decode_sample, validate_library, export_settings, import_settings)
from app.library_recognition import recognize_from_library, LibraryMatcher
from app.symbol_catalog import read_catalog, update_symbol
from app.digitization import recognize_elements
from app.storage import SaveConflict


def glyph(diagonal=False):
    image=Image.new('RGB',(40,40),'white');draw=ImageDraw.Draw(image)
    if diagonal:draw.line((5,5,35,35),fill='black',width=4)
    else:draw.rectangle((8,5,13,35),fill='black');draw.rectangle((8,30,32,35),fill='black')
    return image


def library():
    return {'schema_version':1,'document_type':'symbol_library','symbols':{
        'S001':{'title':'Corner','notes':'Known symbol','samples':[encode_sample(glyph())]}},
        'readable_samples':[{'transcription':'x','png':encode_sample(glyph(True))}]}


class PortableSymbolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_library_roundtrip_in_empty_project_and_preserve_descriptions(self):
        import_symbol_library(self.root,library())
        path=self.root/'project.json';before=json.loads(path.read_text());before['title']='Archive';path.write_text(json.dumps(before))
        imported=export_symbol_library(self.root,self.root/'library.json')
        self.assertEqual(imported['symbols']['S001']['samples'],library()['symbols']['S001']['samples'])
        self.assertEqual(decode_sample(imported['symbols']['S001']['samples'][0]).size,(40,40))
        edited=library();edited['symbols']['S001']['title']='Different description'
        import_symbol_library(self.root,edited)
        self.assertEqual(read_catalog(self.root)['S001']['title'],'Corner')
        self.assertEqual(json.loads(path.read_text())['title'],'Archive')
        self.assertTrue(path.with_suffix('.json.bak').exists())
        self.assertEqual(len(read_catalog(self.root)['S001']['samples']),1)
    def test_editing_catalog_preserves_imported_samples(self):
        import_symbol_library(self.root,library());update_symbol(self.root,'S001','Edited')
        self.assertEqual(read_catalog(self.root)['S001']['samples'],library()['symbols']['S001']['samples'])
    def test_bad_samples_and_versions_do_not_change_project(self):
        import_symbol_library(self.root,library());before=(self.root/'project.json').read_bytes()
        payload=library();payload['symbols']['S001']['samples']=['not base64']
        with self.assertRaises(ValueError):import_symbol_library(self.root,payload)
        for payload in ({}, {'schema_version':99}, {**library(),'symbols':[]}):
            with self.assertRaises(ValueError):import_symbol_library(self.root,payload)
        self.assertEqual((self.root/'project.json').read_bytes(),before)
    def test_wrong_png_dimensions_rejected(self):
        import base64,io
        stream=io.BytesIO();Image.new('RGB',(257,2)).save(stream,format='PNG')
        with self.assertRaises(ValueError):decode_sample(base64.b64encode(stream.getvalue()).decode())
    def test_conflict_rejected(self):
        import_symbol_library(self.root,library())
        with self.assertRaises(SaveConflict):import_symbol_library(self.root,library(),expected_revision='stale')
    def test_reviewed_source_crops_become_portable_samples(self):
        glyph().save(self.root/'images_raw/page.png')
        items=[AnnotationItem(1,'L3',None,[0,0,40,40],element_type='cipher_symbol',symbol_code='S2',reviewed=True),
               AnnotationItem(2,'L3',None,[0,0,40,40],element_type='readable',transcription='A',reviewed=True),
               AnnotationItem(3,'L3',None,[0,0,40,40],element_type='cipher_symbol',symbol_code='UNREVIEWED')]
        save_annotations(self.root/'annotations/page.json',AnnotationFile('page.png',items,4))
        payload=build_symbol_library(self.root)
        self.assertEqual(set(payload['symbols']),{'S2'})
        self.assertEqual(payload['readable_samples'][0]['transcription'],'A')
    def test_symbol_recognition_type_and_undo_input_preserved(self):
        items=[AnnotationItem(1,'L3',None,[0,0,40,40])];before=copy.deepcopy(items)
        result,counts=recognize_from_library(glyph(),items,library())
        self.assertEqual(counts['changed'],1)
        self.assertEqual((result[0].element_type,result[0].symbol_code),('cipher_symbol','S001'))
        self.assertFalse(result[0].reviewed);self.assertIsNone(result[0].recognition_confidence)
        self.assertEqual(items,before)
    def test_readable_and_cipher_types_are_distinguished(self):
        item=AnnotationItem(1,'L3',None,[0,0,40,40])
        result,counts=recognize_from_library(glyph(True),[item],library())
        self.assertEqual((result[0].element_type,result[0].transcription),('readable','x'))
        self.assertEqual(result[0].symbol_code,'')
    def test_ambiguous_unknown_and_blank_never_force_a_label(self):
        payload=library();payload['symbols']['S002']=copy.deepcopy(payload['symbols']['S001'])
        item=AnnotationItem(1,'L3',None,[0,0,40,40])
        result,counts=recognize_from_library(glyph(),[item],payload)
        self.assertEqual(counts['uncertain'],1);self.assertEqual(result[0].element_type,'')
        result,counts=recognize_from_library(Image.new('RGB',(40,40),'white'),[item],library())
        self.assertEqual(counts['uncertain'],1)
    def test_filled_or_reviewed_annotations_are_preserved(self):
        for item in [AnnotationItem(1,'L3',None,[0,0,40,40],element_type='cipher_symbol',symbol_code='MANUAL'),
                     AnnotationItem(1,'L3',None,[0,0,40,40],reviewed=True),
                     AnnotationItem(1,'L3',None,[0,0,40,40],element_type='readable',transcription='Manual')]:
            result,counts=recognize_from_library(glyph(),[item],library())
            self.assertEqual(result,[item]);self.assertEqual(counts['skipped'],1)
    def test_deleting_description_preserves_portable_samples(self):
        import_symbol_library(self.root,library());update_symbol(self.root,'S001',delete=True)
        self.assertEqual(read_catalog(self.root)['S001']['title'],'')
        self.assertEqual(read_catalog(self.root)['S001']['samples'],library()['symbols']['S001']['samples'])
    def test_settings_write_failure_rolls_back_first_file(self):
        from app.storage import atomic_write
        initial={'schema_version':1,'document_type':'backalor_settings','pipeline':[], 'models':{'L1':'old.pt'}}
        import_settings(self.root,initial)
        updated={**initial,'pipeline':[{'step_type':'invert','enabled':True,'params':{}}], 'models':{'L1':'new.pt'}}
        def write(path,content):
            if path.name=='yolo_config.json':raise OSError('Disk full')
            atomic_write(path,content)
        with patch('app.portable.atomic_write',side_effect=write),self.assertRaises(OSError):import_settings(self.root,updated)
        self.assertEqual(export_settings(self.root,self.root/'after.json'),initial)
    def test_empty_library_is_actionable(self):
        payload=library();payload['symbols']={};payload['readable_samples']=[]
        with self.assertRaisesRegex(ValueError,'no usable samples'):recognize_from_library(glyph(),[],payload)
    def test_model_codes_outside_library_are_not_assigned(self):
        item=AnnotationItem(1,'L3',None,[0,0,40,40],element_type='cipher_symbol')
        result,counts=recognize_elements(glyph(),[item],symbol_classifier=lambda image:('ALIEN',.99),allowed_codes={'S1'})
        self.assertEqual(counts['uncertain'],1);self.assertEqual(result[0].symbol_code,'')
    def test_settings_roundtrip_and_backup(self):
        settings={'schema_version':1,'document_type':'backalor_settings',
                  'pipeline':[{'step_type':'contrast','enabled':True,'params':{'factor':1.5}}],
                  'models':{'L1':'model.pt','conf':{'L1':.4},'ocr_model':'/local/trocr','library_threshold':.9,'library_margin':.1}}
        import_settings(self.root,settings)
        self.assertEqual(export_settings(self.root,self.root/'settings.json'),settings)
        import_settings(self.root,{**settings,'models':{'L1':'changed.pt'}})
        self.assertEqual(json.loads((self.root/'results/yolo_config.json.bak').read_text()),settings['models'])
    def test_invalid_settings_rejected_before_any_write(self):
        for models,pipeline in [({'token':'secret'},[]),({'recognition_threshold':2},[]),({},[{'step_type':'shell','enabled':True,'params':{}}]),({},[{'step_type':'gamma','enabled':True,'params':{'gamma':0}}])]:
            payload={'schema_version':1,'document_type':'backalor_settings','pipeline':pipeline,'models':models}
            with self.assertRaises(ValueError):import_settings(self.root,payload)
        self.assertFalse((self.root/'results/yolo_config.json').exists())
        self.assertFalse((self.root/'results/preprocess_pipeline.json').exists())
    def test_project_zip_preserves_portable_samples(self):
        from app.datasets import export_bundle,import_bundle
        import_symbol_library(self.root,library());export_bundle(self.root,self.root/'project.zip')
        import_bundle(self.root/'project.zip',self.root/'new')
        self.assertEqual(build_symbol_library(self.root/'new'),library())
