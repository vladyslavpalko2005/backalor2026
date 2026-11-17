from __future__ import annotations
from PyQt6 import QtCore

class Task(QtCore.QThread):
    succeeded = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.operation())
        except Exception as exc:
            self.failed.emit(str(exc))


class LocalTextRecognizer:
    def __init__(self, model_directory):
        from pathlib import Path
        if not Path(model_directory).is_dir():
            raise ValueError('Select an existing local TrOCR model directory')
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            import torch
        except ImportError as exc:
            raise RuntimeError('Install requirements-ocr.txt to use local text recognition') from exc
        self.torch = torch
        self.processor = TrOCRProcessor.from_pretrained(str(model_directory), local_files_only=True)
        self.model = VisionEncoderDecoderModel.from_pretrained(str(model_directory), local_files_only=True)
        self.model.eval()

    def __call__(self, image):
        values = self.processor(images=image.convert('RGB'), return_tensors='pt').pixel_values
        with self.torch.no_grad():
            tokens = self.model.generate(values, max_new_tokens=128)
        return self.processor.batch_decode(tokens, skip_special_tokens=True)[0]


def recognize_text(image, model_directory):
    return LocalTextRecognizer(model_directory)(image)
