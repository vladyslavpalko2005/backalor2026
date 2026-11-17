"""Exercise actual Qt paint events with selected foreground handles."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from time import monotonic
from PyQt6 import QtCore,QtGui,QtWidgets,QtTest
from app.canvas import EditorCanvas
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class RecordingCanvas(EditorCanvas):
    def __init__(self):
        self.paint_regions=[]
        super().__init__()
    def paintEvent(self,event):
        self.paint_regions.append(QtCore.QRect(event.region().boundingRect()))
        super().paintEvent(event)


class CanvasRepaintTests(unittest.TestCase):
    def setUp(self):
        self.canvas=RecordingCanvas();self.canvas.resize(640,480)
        image=QtGui.QImage(2400,1800,QtGui.QImage.Format.Format_RGB32);image.fill(QtGui.QColor('#eee9de'))
        self.canvas.set_image(image);self.box=self.canvas.add_rect(QtCore.QRectF(980,780,80,60),QtGui.QColor('red'),7)
        self.canvas.highlight_item(7);self.canvas.enable_drawing(False);self.canvas.show();APP.processEvents()
        self.canvas._fitted=False;self.canvas.resetTransform();self.canvas.centerOn(1020,810);APP.processEvents();QtTest.QTest.qWait(30)
        self.original=QtCore.QRectF(self.box.rect());self.canvas.paint_regions.clear()
    def tearDown(self):self.canvas.close();APP.processEvents()
    def wait_for_paint(self):
        deadline=monotonic()+1
        while not self.canvas.paint_regions and monotonic()<deadline:QtTest.QTest.qWait(10)
        self.assertTrue(self.canvas.paint_regions,'The canvas must repaint after an interaction')
    def assert_full_repaint(self):
        self.wait_for_paint();viewport=self.canvas.viewport().rect()
        self.assertTrue(any(region.contains(viewport) for region in self.canvas.paint_regions),
                        f'Foreground handles need a full repaint, got {self.canvas.paint_regions} for {viewport}')
    def test_scrolling_selected_overlay_repaints_entire_viewport(self):
        for horizontal,vertical in [(9,0),(0,13),(-17,0),(0,-11)]:
            with self.subTest(delta=(horizontal,vertical)):
                self.canvas.paint_regions.clear()
                if horizontal:self.canvas.horizontalScrollBar().setValue(self.canvas.horizontalScrollBar().value()+horizontal)
                if vertical:self.canvas.verticalScrollBar().setValue(self.canvas.verticalScrollBar().value()+vertical)
                self.assert_full_repaint()
                self.assertEqual(self.box.rect(),self.original);self.assertEqual(self.canvas._selected_id,7)
    def test_moving_selected_box_clears_old_foreground_handles(self):
        self.box.setRect(self.original.translated(25,15));self.assert_full_repaint()
    def test_alt_pan_changes_view_without_moving_annotations(self):
        initial=(self.canvas.horizontalScrollBar().value(),self.canvas.verticalScrollBar().value())
        start=QtCore.QPoint(300,200);end=QtCore.QPoint(350,225)
        QtTest.QTest.mousePress(self.canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.AltModifier,start)
        QtTest.QTest.mouseMove(self.canvas.viewport(),end)
        QtTest.QTest.mouseRelease(self.canvas.viewport(),QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.AltModifier,end)
        self.assert_full_repaint()
        self.assertNotEqual((self.canvas.horizontalScrollBar().value(),self.canvas.verticalScrollBar().value()),initial)
        self.assertEqual(self.box.rect(),self.original);self.assertIsNone(self.canvas._pan_start)
