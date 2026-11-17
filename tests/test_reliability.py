from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PyQt6 import QtWidgets,QtCore,QtTest
from app.annotations import AnnotationFile,AnnotationItem,save_annotations,load_annotations,annotation_path
from app.project import ensure_project_structure
from app.storage import atomic_write,file_revision,SaveConflict
from app.recovery import save_draft,read_draft,draft_path
from app.yolo_export import export_yolo_dataset,export_all_levels,validate_cascade_dataset
from app.yolo_infer import DetectedBox,cascade_detect
from app.workspace import WorkspaceWindow

APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def fixture(name='a.png'):
    return AnnotationFile(name,[AnnotationItem(1,'L1',None,[10,10,80,80]),
        AnnotationItem(2,'L2',1,[20,20,40,40]),AnnotationItem(3,'L3',2,[30,30,10,10])],4)

class FixtureMixin:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);ensure_project_structure(self.root)
        for name in ('a.png','b.png','c.png'):
            Image.new('RGB',(100,100),'white').save(self.root/'images_raw'/name)
            save_annotations(self.root/'annotations'/f'{Path(name).stem}.json',fixture(name))
        self.path=self.root/'annotations/a.json'
    def tearDown(self):self.temp.cleanup()

class ReliabilityTests(FixtureMixin, unittest.TestCase):
    def test_l2_and_l3_crop_geometry(self):
        export_all_levels(self.root)
        for level,size,suffix,expected in [('L2',(80,80),'L1_1','0 0.375000 0.375000 0.500000 0.500000'),
                                          ('L3',(40,40),'L2_2','0 0.375000 0.375000 0.250000 0.250000')]:
            images=list((self.root/f'results/yolo/{level}/images').rglob('*.png'))
            self.assertEqual(len(images),3)
            with Image.open(images[0]) as image:self.assertEqual(image.size,size)
            label=next((self.root/f'results/yolo/{level}/labels').rglob('*.txt'))
            self.assertEqual(label.read_text(),expected)
            manifest=validate_cascade_dataset(self.root,level)
            self.assertEqual(manifest['samples'][0]['parent_id'],1 if level=='L2' else 2)
    def test_invalid_hierarchy_preserves_all_old_exports(self):
        export_all_levels(self.root)
        paths=list((self.root/'results/yolo').rglob('manifest.json'));before={p:p.read_bytes() for p in paths}
        data=load_annotations(self.path);data.items[2].parent_id=1;save_annotations(self.path,data)
        with self.assertRaisesRegex(ValueError,'parent_level'):export_all_levels(self.root)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})
    def test_parent_without_children_is_negative_crop(self):
        for path in (self.root/'annotations').glob('*.json'):
            data=load_annotations(path);data.items=data.items[:1];save_annotations(path,data)
        result=export_yolo_dataset(self.root,'L2');self.assertEqual(result.images,3)
        self.assertTrue(all(p.read_text()=='' for p in (self.root/'results/yolo/L2/labels').rglob('*.txt')))
    def test_old_dataset_cannot_start_new_cascade_training(self):
        folder=self.root/'results/yolo/L2';folder.mkdir(parents=True)
        (folder/'data.yaml').write_text('train: images\nval: images\n')
        with self.assertRaisesRegex(ValueError,'old dataset'):validate_cascade_dataset(self.root,'L2')
    def test_cropped_samples_preserve_document_partitions(self):
        groups={'a.png':'A','b.png':'B','c.png':'C'}
        for base in ('a','b','c'):
            name=base+'2.png';Image.new('RGB',(100,100)).save(self.root/'images_raw'/name)
            save_annotations(self.root/'annotations'/f'{base}2.json',fixture(name));groups[name]=base.upper()
        (self.root/'project.json').write_text(json.dumps({'image_groups':groups}))
        export_all_levels(self.root)
        manifest=validate_cascade_dataset(self.root,'L3')
        assigned={}
        for sample in manifest['samples']:
            subset=sample['sample'].split('/')[1]
            self.assertEqual(assigned.setdefault(sample['document'],subset),subset)
        self.assertEqual(len(assigned),3)
    def test_fractional_detections_use_actual_integer_crop_origin(self):
        results=[[DetectedBox(10.7,20.9,90.7,95.9,.8)],
                 [DetectedBox(5.8,6.2,45.8,50.2,.7)], [DetectedBox(2.5,3.5,6.5,8.5,.6)]]
        with patch('app.yolo_infer._load_model',side_effect=[1,2,3]),patch('app.yolo_infer._run_detect',side_effect=results) as detect:
            _,l2,l3=cascade_detect(Image.new('RGB',(100,100)),Path('1'),Path('2'),Path('3'))
        self.assertEqual((l2[0].x1,l2[0].y1),(15.8,26.2))
        self.assertEqual((l3[0].x1,l3[0].y1),(17.5,29.5))
        self.assertEqual(detect.call_args_list[1].args[1].size,(80,75))
    def test_backup_preserves_previous_valid_file(self):
        original=self.path.read_bytes();data=load_annotations(self.path);data.items[2].notes='new';save_annotations(self.path,data)
        self.assertEqual(self.path.with_suffix('.json.bak').read_bytes(),original)
    def test_failed_atomic_replace_preserves_file_and_cleans_temp(self):
        original=self.path.read_bytes()
        with patch('app.storage.os.replace',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):atomic_write(self.path,b'broken')
        self.assertEqual(self.path.read_bytes(),original)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))
    def test_conflict_does_not_overwrite_external_change(self):
        expected=file_revision(self.path);data=load_annotations(self.path);data.items[2].notes='external';save_annotations(self.path,data)
        with self.assertRaises(SaveConflict):save_annotations(self.path,fixture(),expected_revision=expected)
        self.assertEqual(load_annotations(self.path).items[2].notes,'external')
    def test_newer_schema_is_never_overwritten(self):
        self.path.write_text(json.dumps({'schema_version':99,'items':[]}));before=self.path.read_bytes()
        with self.assertRaises(ValueError):save_annotations(self.path,fixture())
        self.assertEqual(before,self.path.read_bytes())
    def test_modified_yaml_partition_is_rejected(self):
        export_all_levels(self.root)
        path=self.root/'results/yolo/L3/data.yaml';path.write_text(path.read_text().replace('val: images/val','val: images/train'))
        with self.assertRaisesRegex(ValueError,'YAML'):validate_cascade_dataset(self.root,'L3')
    def test_ambiguous_source_stems_are_rejected_before_export(self):
        Image.new('RGB',(100,100)).save(self.root/'images_raw/a.jpg')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):export_all_levels(self.root)
        self.assertFalse((self.root/'results/yolo').exists())

class RecoveryWindowTests(FixtureMixin, unittest.TestCase):
    def setUp(self):
        FixtureMixin.setUp(self)
        self.window=WorkspaceWindow(self.root)
        self.errors=[];self.window._error=self.errors.append
    def tearDown(self):
        if self.window._property_dirty:self.window.discard_properties()
        # Restore the known disk revision after the deliberate conflict test.
        self.window._disk_revision=file_revision(annotation_path(self.root,self.window.current_image_path))
        self.window.close();APP.processEvents();FixtureMixin.tearDown(self)
    def restart_without_close(self,accept=True):
        old=self.window
        old.autosave_timer.stop();old.journal_timer.stop();old.hide();old.deleteLater()
        APP.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
        with patch.object(WorkspaceWindow,'_ask_recovery',return_value=accept):self.window=WorkspaceWindow(self.root)
        self.window._error=self.errors.append
    def test_periodic_save_commits_and_preserves_backup(self):
        self.window.annotation_items[2].notes='automatic';self.window.annotation_dirty=True
        self.window._autosave_tick()
        self.assertEqual(load_annotations(self.path).items[2].notes,'automatic')
        self.assertFalse(draft_path(self.root,self.root/'images_raw/a.png').exists())
        self.assertEqual(load_annotations(self.path.with_suffix('.json.bak')).items[2].notes,'')
    def test_pending_invalid_fields_survive_restart(self):
        self.window.select_annotation(3);self.window.fields['transcription'].setText('lost? no')
        self.window.coords[0].setValue(999);self.window._autosave_tick()
        self.assertEqual(load_annotations(self.path).items[2].transcription,'')
        self.restart_without_close()
        self.assertEqual(self.window.fields['transcription'].text(),'lost? no')
        self.assertEqual(self.window.coords[0].value(),999)
        self.assertTrue(self.window._property_dirty)
    def test_annotation_draft_recovers_unsaved_undo_state(self):
        self.window.delete_annotation(3);self.window._checkpoint()
        self.restart_without_close()
        self.assertEqual([i.id for i in self.window.annotation_items],[1,2])
        self.window.save_annotations_current();self.assertEqual(len(load_annotations(self.path).items),2)
    def test_declining_recovery_preserves_saved_file(self):
        self.window.annotation_items[2].notes='draft';self.window.annotation_dirty=True;self.window._checkpoint()
        self.restart_without_close(accept=False)
        self.assertEqual(self.window.annotation_items[2].notes,'')
        self.assertFalse(draft_path(self.root,self.root/'images_raw/a.png').exists())
    def test_corrupt_primary_restores_valid_backup(self):
        data=load_annotations(self.path);data.items[2].notes='second';save_annotations(self.path,data)
        self.path.write_text('{broken')
        self.restart_without_close()
        self.assertEqual(self.window.annotation_items[2].notes,'')
        self.assertTrue(self.window.annotation_dirty)
        self.window.save_annotations_current()
        self.assertEqual(load_annotations(self.path).items[2].notes,'')
    def test_deleting_all_annotations_retains_recoverable_previous_file(self):
        self.window.delete_annotation(1);self.window._autosave_tick()
        self.assertEqual(load_annotations(self.path).items,[])
        self.assertEqual(len(load_annotations(self.path.with_suffix('.json.bak')).items),3)
    def test_autosave_failure_keeps_draft_without_modal(self):
        self.window.annotation_items[2].notes='retained';self.window.annotation_dirty=True
        with patch('app.workspace.save_annotations',side_effect=PermissionError('read only')):self.window._autosave_tick()
        draft=read_draft(self.root,self.root/'images_raw/a.png')
        self.assertEqual(draft['data'].items[2].notes,'retained');self.assertTrue(self.window.annotation_dirty)
        self.assertFalse(self.errors)
    def test_external_change_stops_autosave(self):
        data=load_annotations(self.path);data.items[2].notes='external';save_annotations(self.path,data)
        self.window.annotation_items[2].notes='mine';self.window.annotation_dirty=True;self.window._autosave_tick()
        self.assertEqual(load_annotations(self.path).items[2].notes,'external')
        self.assertEqual(read_draft(self.root,self.root/'images_raw/a.png')['data'].items[2].notes,'mine')
        self.assertTrue(self.window.annotation_dirty)
    def test_corrupt_draft_does_not_block_saved_annotations(self):
        draft=draft_path(self.root,self.root/'images_raw/a.png');draft.parent.mkdir(exist_ok=True);draft.write_text('{bad')
        self.restart_without_close()
        self.assertEqual(len(self.window.annotation_items),3);self.assertTrue(draft.exists())
    def test_reload_after_conflict_keeps_draft_and_loads_external_file(self):
        data=load_annotations(self.path);data.items[2].notes='external';save_annotations(self.path,data)
        self.window.annotation_items[2].notes='mine';self.window.annotation_dirty=True
        with patch.object(self.window,'_ask_recovery',return_value=True):self.window.reload_saved_annotations()
        self.assertEqual(self.window.annotation_items[2].notes,'external')
        self.assertEqual(read_draft(self.root,self.root/'images_raw/a.png')['data'].items[2].notes,'mine')
        self.assertFalse(self.window.annotation_dirty)
    def test_replacing_annotations_clears_old_property_selection(self):
        self.window.select_annotation(3)
        self.window._replace_annotations([AnnotationItem(1,'L1',None,[0,0,90,90])])
        self.assertIsNone(self.window._active_annotation)
        self.assertFalse(self.window.properties.isEnabled())
    def test_periodic_timer_really_saves_changes(self):
        self.window.annotation_items[2].notes='timer';self.window.annotation_dirty=True
        from time import monotonic
        self.window.autosave_timer.setInterval(5)
        deadline=monotonic()+1
        while self.window.annotation_dirty and monotonic()<deadline:QtTest.QTest.qWait(10)
        self.assertEqual(load_annotations(self.path).items[2].notes,'timer')
    def test_invalid_pending_fields_prevent_image_deletion(self):
        self.window.select_annotation(3);self.window.coords[0].setValue(999)
        with patch('app.workspace.QtWidgets.QMessageBox.question',return_value=QtWidgets.QMessageBox.StandardButton.Yes):
            self.window.delete_image()
        self.assertTrue((self.root/'images_raw/a.png').exists());self.assertTrue(self.path.exists())
        self.assertFalse((self.root/'.trash').exists())

if __name__=='__main__':unittest.main()
