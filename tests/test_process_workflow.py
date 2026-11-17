"""Exercise the Qt subprocess lifecycle independently of slow model training."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
from pathlib import Path
from time import monotonic
import unittest
from PyQt6 import QtCore, QtWidgets
from app.workspace import WorkspaceWindow
APP=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TrainingProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.window=WorkspaceWindow(self.root);self.errors=[];self.window._error=self.errors.append
    def tearDown(self):
        if self.window._process is not None:
            self.window._process.kill();self.window._process.waitForFinished(3000);APP.processEvents()
        self.window.close();APP.processEvents();self.temp.cleanup()
    def launch(self,code,program=None):
        process=QtCore.QProcess(self.window);self.window._process=process
        self.window._training_output='';self.window._training_mode='train';self.window._training_level='L1'
        process.setProgram(program or sys.executable);process.setArguments(['-u','-c',code])
        process.setWorkingDirectory(str(self.root));process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.window._read_training_output)
        process.finished.connect(self.window._training_finished);process.errorOccurred.connect(self.window._training_error)
        self.window._set_busy(True);process.start()
        return process
    def wait(self,predicate):
        deadline=monotonic()+5
        while not predicate() and monotonic()<deadline:APP.processEvents();QtCore.QThread.msleep(2)
        APP.processEvents();self.assertTrue(predicate())
    def test_running_training_blocks_close_then_stop_restores_controls(self):
        self.window.show();self.launch("import time; print('started',flush=True); time.sleep(60)")
        self.wait(lambda:'started' in self.window._training_output)
        self.assertFalse(self.window.train_button.isEnabled());self.assertTrue(self.window.stop_button.isEnabled())
        self.assertFalse(self.window.close());self.assertTrue(self.errors)
        self.window.stop_training();self.wait(lambda:self.window._process is None)
        self.assertTrue(self.window.train_button.isEnabled());self.assertFalse(self.window.stop_button.isEnabled())
        self.assertIn('started',(self.root/'results/training.log').read_text())
    def test_successful_process_selects_saved_weights_and_keeps_log(self):
        self.launch("from pathlib import Path; p=Path('runs/detect/L1/weights/best.pt'); p.parent.mkdir(parents=True); p.write_bytes(b'test-only'); print('finished')")
        self.wait(lambda:self.window._process is None)
        target=self.root/'runs/detect/L1/weights/best.pt'
        self.assertEqual(self.window.weight_fields['L1'].text(),str(target.resolve()))
        self.assertIn('finished',(self.root/'results/training.log').read_text())
        self.assertIn('Exit: 0',self.window.job_log.toPlainText())
    def test_failed_process_start_releases_busy_state(self):
        before=self.window.weight_fields['L1'].text()
        self.launch('',str(self.root/'nonexistent-python'))
        self.wait(lambda:self.window._process is None)
        self.assertTrue(self.window.train_button.isEnabled())
        self.assertEqual(self.window.weight_fields['L1'].text(),before)
        self.assertIn('Exit: -1',self.window.job_log.toPlainText())
