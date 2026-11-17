"""Isolated Ultralytics process; no UI imports."""
from __future__ import annotations
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--level', choices=['L1','L2','L3'], required=True)
    parser.add_argument('--model', default='yolov8n.pt')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=4)
    parser.add_argument('--mode', choices=['train','val','test'], default='train')
    args = parser.parse_args()
    root = Path(args.root)
    from .yolo_export import validate_cascade_dataset
    validate_cascade_dataset(root, args.level)
    try:
        from ultralytics import YOLO
    except ImportError:
        parser.exit(1, 'Install requirements-ml.txt to train or evaluate YOLO.\n')
    model_path = Path(args.model)
    if not model_path.is_file():
        parser.exit(1, 'Choose a local YOLO weights file. No model is downloaded automatically.\n')
    model = YOLO(str(model_path))
    data = str(root/'results'/'yolo'/args.level/'data.yaml')
    if args.mode == 'train':
        model.train(data=data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                    project=str(root/'runs'/'detect'), name=args.level, seed=42, amp=False)
    else:
        model.val(data=data, split=args.mode, imgsz=args.imgsz, batch=args.batch,
                  project=str(root/'runs'/'evaluate'), name=args.level+'_'+args.mode)

if __name__ == '__main__':
    main()
