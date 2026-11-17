from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import json
import tempfile
import unittest
import zipfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from PyQt6 import QtCore, QtWidgets, QtTest
from app.annotations import AnnotationFile, AnnotationItem, load_annotations, save_annotations, annotation_path
from app.datasets import export_bundle, import_bundle, export_coco, validate_annotations
from app.project import ensure_project_structure, list_raw_images
from app.pipeline import apply_pipeline, Step
from app.segmentation import segment_image
from app.yolo_export import export_yolo_dataset, dataset_split, _items_to_yolo
from app.workspace import WorkspaceWindow

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        ensure_project_structure(self.root)
    def tearDown(self): self.temp.cleanup()
    def image(self,name='page.png'):
        path=self.root/'images_raw'/name; Image.new('RGB',(100,80),'white').save(path); return path
    def annotations(self):
        return AnnotationFile('page.png',[
            AnnotationItem(1,'L1',None,[0,0,100,80]),
            AnnotationItem(2,'L2',1,[10,10,70,50]),
            AnnotationItem(3,'L3',2,[20,20,10,10],transcription='А — č',symbol_code='42',kind='ciphertext')],4)
    def test_roundtrip_metadata(self):
        path=annotation_path(self.root,self.image()); data=self.annotations(); save_annotations(path,data)
        self.assertEqual(data,load_annotations(path)); self.assertEqual(json.loads(path.read_text())['schema_version'],4)
    def test_legacy_defaults_and_next_id(self):
        path=self.root/'annotations'/'legacy.json'; path.write_text(json.dumps({'items':[{'id':8,'level':'L1','parent_id':None,'bbox':[0,0,1,1]}],'next_id':2}))
        data=load_annotations(path); self.assertEqual(data.next_id,9); self.assertEqual(data.items[0].transcription,'')
    def test_validation_finds_wrong_parent_and_bounds(self):
        data=self.annotations(); data.items[2].parent_id=1; data.items[2].bbox=[95,0,10,10]
        issues=validate_annotations(data,(100,80)); self.assertTrue(any('parent_level' in i for i in issues)); self.assertTrue(any('outside_image' in i for i in issues))
    def test_coco_preserves_hierarchy_and_transcription(self):
        path=self.image(); save_annotations(annotation_path(self.root,path),self.annotations())
        data=export_coco(self.root,self.root/'results'/'coco.json'); self.assertEqual(data['annotations'][2]['parent_id'],2)
        self.assertEqual(data['annotations'][2]['attributes']['transcription'],'А — č')
    def test_bundle_roundtrip(self):
        path=self.image(); save_annotations(annotation_path(self.root,path),self.annotations())
        target=self.root/'bundle.zip'; export_bundle(self.root,target)
        dest=self.root/'imported'; import_bundle(target,dest)
        self.assertEqual(load_annotations(dest/'annotations'/'page.json'),self.annotations())
    def test_zip_traversal_blocked(self):
        source=self.root/'bad.zip'
        with zipfile.ZipFile(source,'w') as z: z.writestr('../escape.txt','x')
        with self.assertRaises(ValueError): import_bundle(source,self.root/'target')
        self.assertFalse((self.root/'escape.txt').exists())
    def test_import_does_not_overwrite(self):
        target=self.root/'bundle.zip'; export_bundle(self.root,target)
        with self.assertRaises(ValueError): import_bundle(target,self.root)
    def test_split_disjoint_reproducible(self):
        split=dataset_split([str(i) for i in range(20)])
        self.assertEqual(split,dataset_split([str(i) for i in range(20)])); self.assertEqual([len(split[k]) for k in ['train','val','test']],[14,3,3])
        self.assertFalse(set(split['train']) & set(split['val'])); self.assertFalse(set(split['train']) & set(split['test']))
    def test_document_pages_stay_together(self):
        split=dataset_split(['a1','a2','b1','c1'],groups={'a1':'A','a2':'A'})
        self.assertTrue(any('a1' in subset and 'a2' in subset for subset in split.values()))
        with self.assertRaises(ValueError): dataset_split(['a1','a2','a3'],groups={'a1':'A','a2':'A','a3':'A'})
    def test_import_pdf_and_stem_collision(self):
        import fitz
        from app.importing import import_sources
        pdf=fitz.open(); pdf.new_page(); pdf.new_page(); source=self.root/'document.pdf'; pdf.save(source); pdf.close()
        self.assertEqual(import_sources(self.root,[source]),2)
        metadata=json.loads((self.root/'project.json').read_text()); self.assertEqual(len(set(metadata['image_groups'].values())),1)
        src=self.root/'source'; src.mkdir(); Image.new('RGB',(30,20)).save(src/'same.png'); Image.new('RGB',(30,20)).save(src/'same.jpg')
        import_sources(self.root,[src/'same.png',src/'same.jpg']); self.assertTrue((self.root/'images_raw/same_1.jpg').exists())
    def test_failed_import_does_not_commit_partial_images(self):
        from app.importing import import_sources
        source=self.root/'valid.png'; Image.new('RGB',(30,20)).save(source)
        broken=self.root/'broken.png'; broken.write_text('invalid')
        with self.assertRaises(Exception): import_sources(self.root,[source,broken])
        self.assertFalse(list_raw_images(self.root))
    def test_yolo_export_refreshes_and_excludes_not_symbol(self):
        for i in range(3):
            path=self.image(f'page{i}.png'); data=self.annotations(); data.items[2].label='not_symbol'; save_annotations(annotation_path(self.root,path),data)
        result=export_yolo_dataset(self.root,'L3'); self.assertEqual(result.images,3)
        self.assertEqual(sum(len(p.read_text().splitlines()) for p in (self.root/'results/yolo/L3/labels').rglob('*.txt')),0)
        name=dataset_split([f'page{i}.png' for i in range(3)])['train'][0]
        first=self.root/'results/yolo/L3/images/train'/f'{Path(name).stem}__L2_2.png'
        Image.new('RGB',(100,80),'black').save(self.root/'images_raw'/name)
        export_yolo_dataset(self.root,'L3')
        with Image.open(first) as image: self.assertEqual(image.getpixel((0,0)),(0,0,0))
    def test_export_failure_leaves_old_dataset(self):
        for i in range(3):
            path=self.image(f'page{i}.png'); save_annotations(annotation_path(self.root,path),self.annotations())
        export_yolo_dataset(self.root,'L1'); yaml=self.root/'results/yolo/L1/data.yaml'; before=yaml.read_bytes()
        invalid=self.annotations(); invalid.items[0].bbox=[0,0,999,80]; save_annotations(self.root/'annotations/page0.json',invalid)
        with self.assertRaises(ValueError): export_yolo_dataset(self.root,'L1')
        self.assertEqual(yaml.read_bytes(),before)
    def test_yolo_geometry_and_processed_guard(self):
        box=AnnotationItem(1,'L1',None,[10,20,40,20]); self.assertEqual(_items_to_yolo([box],100,100),['0 0.300000 0.300000 0.400000 0.200000'])
        with self.assertRaises(ValueError): export_yolo_dataset(self.root,'L1',True)
    def test_uppercase_images(self):
        self.image('PAGE.PNG'); self.assertEqual(list_raw_images(self.root)[0].name,'PAGE.PNG')
    def test_natural_image_order(self):
        for name in ('img10.png','img2.png','img1.png'): self.image(name)
        self.assertEqual([p.name for p in list_raw_images(self.root)],['img1.png','img2.png','img10.png'])
    def test_resize_preserves_aspect_with_both_dimensions(self):
        image=Image.new('RGB',(100,50)); result=apply_pipeline(image,[Step('resize',True,{'width':40,'height':40,'keep_aspect':True})]); self.assertEqual(result.size,(40,20))
    def test_segmentation_ignores_geometric_preprocessing(self):
        image=Image.new('L',(120,80),255); draw=ImageDraw.Draw(image); draw.rectangle((10,15,40,25),fill=0); draw.rectangle((50,15,80,25),fill=0)
        steps=[Step('resize',True,{'width':20,'height':20}),Step('crop',True,{'left':0,'top':0,'right':5,'bottom':5})]
        items=segment_image(image,steps); self.assertEqual(items,segment_image(image)); self.assertTrue(items); self.assertFalse(validate_annotations(AnnotationFile('',items,20),image.size))
    def test_crash_diagnostics_persist_exception_and_stack(self):
        script="from pathlib import Path; import sys,faulthandler; from app import diagnostics; diagnostics.install_diagnostics(Path(sys.argv[1])); faulthandler.dump_traceback(file=diagnostics._fault_stream); raise RuntimeError('diagnostic-probe')"
        result=subprocess.run([sys.executable,'-c',script,str(self.root)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1)
        log=(self.root/'results/application_crash.log').read_text()
        self.assertIn('diagnostic-probe',log);self.assertIn('Application start:',log);self.assertIn('File "<string>"',log)

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); ensure_project_structure(self.root)
        for name in ('page.png','other.png'): Image.new('RGB',(200,150),'white').save(self.root/'images_raw'/name)
        self.original=AnnotationFile('page.png',[AnnotationItem(1,'L1',None,[10,10,180,130]),AnnotationItem(2,'L2',1,[20,20,80,70]),AnnotationItem(3,'L3',2,[30,30,20,20])],4)
        self.path=self.root/'annotations/page.json'; save_annotations(self.path,self.original)
        self.window=WorkspaceWindow(self.root)
        self.errors=[]; self.window._error=lambda message:self.errors.append(message)
        self.select('page.png')
    def select(self,name):
        for index in range(self.window.image_list.count()):
            item=self.window.image_list.item(index)
            if item.text()==name: self.window.image_list.setCurrentItem(item); break
        APP.processEvents()
    def tearDown(self):
        self.window.close(); APP.processEvents(); self.temp.cleanup()
    def test_autoload_does_not_rewrite_existing_file(self):
        before=self.path.read_bytes(); self.select('other.png'); self.assertEqual(before,self.path.read_bytes())
    def test_disabled_load_never_deletes_annotations(self):
        self.window.set_load_saved_annotations(False); self.select('other.png'); self.select('page.png'); self.select('other.png'); self.assertEqual(load_annotations(self.path),self.original)
    def test_explicit_save_without_load_preserves_annotations(self):
        self.window.set_load_saved_annotations(False); self.select('other.png'); self.select('page.png')
        self.window.save_annotations_current(); self.assertEqual(load_annotations(self.path),self.original)
    def test_inspector_geometry_updates_canvas(self):
        self.window.select_annotation(3); self.window.coords[0].setValue(35); self.window.apply_properties()
        self.assertEqual(self.window.annotation_rects[3].rect().x(),35)
    def test_layer_visibility(self):
        self.window._redraw_annotations(); self.window.layer_checks['L3'].setChecked(False)
        self.assertFalse(self.window.annotation_rects[3].isVisible()); self.assertTrue(self.window.annotation_rects[1].isVisible())
    def test_edit_transcription_undo_redo(self):
        self.window.select_annotation(3); self.window.fields['transcription'].setText('číslo 42'); self.window.apply_properties()
        self.assertEqual(self.window.annotation_items[2].transcription,'číslo 42')
        self.window.undo(); self.assertEqual(self.window.annotation_items[2].transcription,'')
        self.window.redo(); self.assertEqual(self.window.annotation_items[2].transcription,'číslo 42')
    def test_delete_parent_cascade_undo(self):
        self.window.delete_annotation(1); self.assertFalse(self.window.annotation_items)
        self.window.undo(); self.assertEqual(self.window.annotation_items,self.original.items)
    def test_parent_move_moves_descendants(self):
        self.window.edit_box(2,QtCore.QRectF(25,25,80,70)); self.assertEqual(self.window.annotation_items[2].bbox,[35,35,20,20]); self.assertFalse(self.errors)
        self.window.undo(); self.assertEqual(self.window.annotation_items,self.original.items)
    def test_invalid_resize_rejected_without_history(self):
        self.window.edit_box(2,QtCore.QRectF(20,20,10,10)); self.assertEqual(self.window.annotation_items,self.original.items); self.assertTrue(self.errors); self.assertFalse(self.window._undo)
    def test_strict_l3_parent(self):
        self.window.annotation_level='L3'; self.window.on_rect_created(QtCore.QRectF(130,100,10,10)); self.assertEqual(len(self.window.annotation_items),3); self.assertTrue(self.errors)
    def test_preview_geometry_never_moves_canvas(self):
        self.window.steps=[Step('resize',True,{'width':50,'height':50})]; self.window._render_preview()
        self.assertEqual(self.window.annotation_canvas.sceneRect().size(),QtCore.QSizeF(200,150)); self.assertEqual(self.window.annotation_items,self.original.items)
    def test_symbols_search_and_navigation(self):
        self.window.annotation_items[2].transcription='abc'; self.window.annotation_dirty=True
        self.window.refresh_symbols(); self.assertEqual(self.window.symbol_table.rowCount(),1)
        self.window.filter_symbols('absent'); self.assertTrue(self.window.symbol_table.isRowHidden(0))
        self.window.filter_symbols('abc'); self.assertFalse(self.window.symbol_table.isRowHidden(0))
        self.select('other.png'); self.window.open_symbol(0,0); self.assertEqual(self.window.current_image_path.name,'page.png'); self.assertEqual(self.window._active_annotation,3)
    def test_project_switch_flushes_and_resets(self):
        self.window.select_annotation(3); self.window.fields['transcription'].setText('save me'); self.window.apply_properties()
        self.window.switch_project(self.root/'new'); self.assertEqual(load_annotations(self.path).items[2].transcription,'save me'); self.assertFalse(self.window._undo)
    def test_async_task_delivers_result_and_enables_ui(self):
        received=[]; self.window.run_task(lambda:42,received.append)
        from time import monotonic
        deadline=monotonic()+5
        while self.window._task is not None and monotonic()<deadline: APP.processEvents(); QtCore.QThread.msleep(5)
        self.assertEqual(received,[42]); self.assertTrue(self.window.image_list.parentWidget().isEnabled())
    def test_close_autosaves(self):
        self.window.annotation_items[2].notes='close save'; self.window.annotation_dirty=True; self.window.close()
        self.assertEqual(load_annotations(self.path).items[2].notes,'close save')
    def test_both_languages(self):
        self.window.apply_language('uk'); self.assertEqual(self.window.center_tabs.tabText(2),'Символи')
        self.window.apply_language('sk'); self.assertEqual(self.window.center_tabs.tabText(2),'Symboly')
    def test_unapplied_text_survives_navigation(self):
        self.window.select_annotation(3)
        self.window.fields['transcription'].setText('pending 42')
        self.window._property_modified()
        self.select('other.png')
        self.assertEqual(load_annotations(self.path).items[2].transcription,'pending 42')
    def test_invalid_pending_geometry_blocks_navigation(self):
        self.window.select_annotation(3);self.window.coords[0].setValue(190)
        self.select('other.png')
        self.assertEqual(self.window.current_image_path.name,'page.png')
        self.assertEqual(self.window.coords[0].value(),190)
        self.assertTrue(self.errors)
        self.window.coords[0].setValue(30);self.window.apply_properties()
    def test_discard_pending_properties_restores_form(self):
        self.window.select_annotation(3);self.window.coords[0].setValue(190)
        self.window.discard_properties()
        self.assertEqual(self.window.coords[0].value(),30)
        self.assertFalse(self.window._property_dirty)
    def test_canvas_selection_reveals_hierarchy(self):
        self.window._select_from_canvas(3)
        self.assertEqual(self.window._selected_id(self.window.list_l1),1)
        self.assertEqual(self.window._selected_id(self.window.list_l2),2)
        self.assertEqual(self.window._selected_id(self.window.list_l3),3)
        self.assertEqual(self.window.inspector_tabs.currentIndex(),1)
    def test_annotation_toolbar_contextual(self):
        self.window.center_tabs.setCurrentIndex(0);self.assertTrue(self.window.annotation_toolbar.isHidden())
        self.window.center_tabs.setCurrentIndex(1);self.assertFalse(self.window.annotation_toolbar.isHidden())
    def test_preview_modes_and_linked_zoom(self):
        self.window._render_preview()
        self.window.original_view.zoom(2)
        self.assertAlmostEqual(self.window.original_view.transform().m11(),self.window.processed_view.transform().m11(),places=5)
        self.window.preview_mode.setCurrentIndex(1)
        self.assertTrue(self.window.preview_frames[1].isHidden())
        self.window.preview_mode.setCurrentIndex(2)
        self.assertTrue(self.window.preview_frames[0].isHidden())
    def test_image_navigation_uses_filtered_results(self):
        self.window.image_search.setText('other');self.window.navigate_image(1)
        self.assertEqual(self.window.current_image_path.name,'other.png')
        self.assertEqual(self.window.navigation.text(),'1 / 1')
    def test_mode_menu_and_combo_stay_consistent(self):
        self.window.draw_action.setChecked(False)
        self.assertEqual(self.window.mode_combo.currentData(),False)
        self.assertFalse(self.window.annotation_canvas._drawing_enabled)
        self.window.mode_combo.setCurrentIndex(0);self.assertTrue(self.window.draw_action.isChecked())
    def test_digit_shortcuts_do_not_intercept_transcription(self):
        self.window.show();self.window.center_tabs.setCurrentIndex(1)
        self.window._select_from_canvas(3)
        field=self.window.fields['transcription'];field.setFocus();QtTest.QTest.keyClicks(field,'f123')
        self.assertEqual(field.text(),'f123');self.assertEqual(self.window.annotation_level,'L1')
    def test_resize_top_left_handle(self):
        self.window.show();self.window.center_tabs.setCurrentIndex(1)
        APP.processEvents();self.window._redraw_annotations();self.window.select_annotation(3)
        self.window.mode_combo.setCurrentIndex(1)
        canvas=self.window.annotation_canvas;canvas.fit_image()
        start=canvas.mapFromScene(QtCore.QPointF(30,30));end=canvas.mapFromScene(QtCore.QPointF(25,25))
        QtTest.QTest.mousePress(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start)
        QtTest.QTest.mouseMove(canvas.viewport(),end)
        QtTest.QTest.mouseRelease(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(self.window.annotation_items[2].bbox,[25,25,25,25])
    def test_new_step_selects_new_parameters_and_preserves_previous(self):
        self.window.step_combo.setCurrentIndex(self.window.step_combo.findData('brightness'));self.window.add_step()
        self.window.step_combo.setCurrentIndex(self.window.step_combo.findData('threshold'));self.window.add_step()
        self.assertEqual(self.window.steps_list.currentRow(),1)
        self.window.refresh_steps_list();self.assertEqual(self.window.steps_list.currentRow(),1)
        editor=self.window.params_form.itemAt(0,QtWidgets.QFormLayout.ItemRole.FieldRole).widget()
        self.assertEqual((editor.minimum(),editor.maximum()),(0,255))
    def test_native_list_selection_does_not_destroy_signal_item(self):
        self.window.show();self.window.center_tabs.setCurrentIndex(1);APP.processEvents()
        observed=[]
        self.window.list_l1.currentItemChanged.connect(lambda current,previous:observed.append(current is self.window.list_l1.currentItem()))
        item=self.window.list_l1.item(0)
        QtTest.QTest.mouseClick(self.window.list_l1.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=self.window.list_l1.visualItemRect(item).center())
        self.assertTrue(observed);self.assertTrue(all(observed))
        APP.processEvents();self.assertEqual(self.window._active_annotation,1)
    def test_selection_queue_is_canceled_when_image_changes(self):
        self.window.list_l1.setCurrentRow(0)
        self.assertIsNotNone(self.window._pending_selection)
        self.select('other.png');APP.processEvents()
        self.assertIsNone(self.window._active_annotation)
    def test_repeated_mouse_selection_across_hierarchy(self):
        self.window.annotation_items.extend([AnnotationItem(10,'L1',None,[130,10,50,70]),
            AnnotationItem(11,'L2',10,[135,15,40,60]),AnnotationItem(12,'L3',11,[140,20,10,10])])
        self.window.annotation_next_id=13;self.window._redraw_annotations();self.window.refresh_annotation_lists()
        self.window.show();self.window.center_tabs.setCurrentIndex(1);APP.processEvents()
        for index in range(80):
            row=index%2;item=self.window.list_l1.item(row)
            QtTest.QTest.mouseClick(self.window.list_l1.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=self.window.list_l1.visualItemRect(item).center())
            APP.processEvents()
            pair=self.window.list_l2.item(0)
            self.assertEqual(pair.data(QtCore.Qt.ItemDataRole.UserRole),2 if row==0 else 11)
            self.window.list_l2.setCurrentRow(0);APP.processEvents()
            self.window.list_l3.setCurrentRow(0);APP.processEvents()
            self.assertEqual(self.window._active_annotation,3 if row==0 else 12)
    def test_pending_properties_cancel_stale_canvas_drag(self):
        self.window.show();self.window.center_tabs.setCurrentIndex(1);APP.processEvents()
        self.window._redraw_annotations();self.window.select_annotation(3);self.window.mode_combo.setCurrentIndex(1)
        self.window.fields['notes'].setText('pending note');self.window._property_modified()
        canvas=self.window.annotation_canvas;canvas.fit_image()
        start=canvas.mapFromScene(QtCore.QPointF(40,40));end=canvas.mapFromScene(QtCore.QPointF(43,43))
        QtTest.QTest.mousePress(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start)
        self.assertIsNone(canvas._edit_item)
        QtTest.QTest.mouseMove(canvas.viewport(),end)
        QtTest.QTest.mouseRelease(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(self.window.annotation_items[2].notes,'pending note')
    def test_repeated_mouse_drawing_l1_l2_l3_and_deleting(self):
        self.window.show();self.window.center_tabs.setCurrentIndex(1);APP.processEvents()
        self.window.draw_action.setChecked(True)
        canvas=self.window.annotation_canvas;canvas.fit_image()
        for cycle in range(25):
            root_id=self.window.annotation_next_id
            for level,start,end in [('L1',(120,85),(180,135)),('L2',(130,95),(170,125)),('L3',(140,100),(150,110))]:
                self.window.set_annotation_level(level)
                point1=canvas.mapFromScene(QtCore.QPointF(*start));point2=canvas.mapFromScene(QtCore.QPointF(*end))
                QtTest.QTest.mousePress(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=point1)
                QtTest.QTest.mouseMove(canvas.viewport(),point2)
                QtTest.QTest.mouseRelease(canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=point2)
                APP.processEvents()
            self.assertEqual([i.parent_id for i in self.window.annotation_items[-3:]],[None,root_id,root_id+1])
            self.window.delete_annotation(root_id);APP.processEvents()
            self.assertEqual(len(self.window.annotation_items),3)

if __name__ == '__main__': unittest.main()
