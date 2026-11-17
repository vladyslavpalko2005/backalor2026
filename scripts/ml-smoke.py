"""Local YOLO integration smoke test; temporary datasets and existing weights only.

Version checks and font downloads are disabled in this test process. This tests
execution and persistence, not research accuracy. No application data is edited.
"""
import sys,os,json,tempfile,time,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--report-dir",type=Path,default=ROOT/"reports/ml-smoke")
    args=parser.parse_args();report_dir=args.report_dir;report_dir.mkdir(parents=True,exist_ok=True)
    os.environ['YOLO_CONFIG_DIR']='/private/tmp/backalor-yolo-validation'
    os.environ['MPLCONFIGDIR']='/private/tmp/backalor-mpl-validation'
    os.environ['YOLO_AUTOINSTALL']='false'
    os.environ['YOLO_OFFLINE']='true'
    Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)
    Path(os.environ['MPLCONFIGDIR']).mkdir(parents=True,exist_ok=True)
    from PIL import Image,ImageDraw
    from app.yolo_infer import cascade_detect
    from app.annotations import AnnotationFile,AnnotationItem,save_annotations
    from app.project import ensure_project_structure
    from app.yolo_export import export_all_levels
    from app import train_worker
    from ultralytics import settings
    settings.update({key:False for key in ('sync','wandb','mlflow','comet','clearml','neptune','tensorboard','dvc') if key in settings})
    from ultralytics.utils import checks
    import ultralytics.data.utils as data_utils
    import ultralytics.utils.plotting as plotting
    font=Path('/System/Library/Fonts/Supplemental/Arial.ttf')
    checks.check_pip_update_available=lambda:None
    checks.check_font=lambda *args,**kwargs:font
    data_utils.check_font=checks.check_font;plotting.check_font=checks.check_font
    result={'source':'images_raw/img1.png','inference':{},'training':{},'evaluation':{}}
    started=time.monotonic()
    with Image.open(ROOT/'images_raw/img1.png') as scan:
     boxes=cascade_detect(scan.convert('RGB'),*[ROOT/f'runs/detect/train{i}/weights/best.pt' for i in (4,5,6)])
     result['inference']={level:len(entries) for level,entries in zip(('L1','L2','L3'),boxes)}
     print('REAL_CASCADE',result['inference'],flush=True)
    with tempfile.TemporaryDirectory(prefix='backalor-ml-') as temporary:
     project=Path(temporary);ensure_project_structure(project)
     for index in range(3):
      image=Image.new('RGB',(128,128),'white');draw=ImageDraw.Draw(image)
      draw.rectangle((10+index,10,115,115),outline='black',width=2)
      draw.line((15,40,110,40),fill='black',width=2);draw.line((20,20,30,30),fill='black',width=3)
      name=f'doc{index}.png';image.save(project/'images_raw'/name)
      items=[AnnotationItem(1,'L1',None,[5,5,118,118]),AnnotationItem(2,'L2',1,[10,10,105,45]),AnnotationItem(3,'L3',2,[15,15,20,20])]
      save_annotations(project/'annotations'/f'doc{index}.json',AnnotationFile(name,items,4))
     export_all_levels(project)
     for level in ('L1','L2','L3'):
      for mode in ('train','test'):
       weights=ROOT/'yolov8n.pt' if mode=='train' else project/'runs/detect'/level/'weights/best.pt'
       sys.argv=['train_worker','--root',str(project),'--level',level,'--model',str(weights),'--epochs','1','--imgsz','64','--batch','1','--mode',mode]
       print('START',level,mode,flush=True);tick=time.monotonic();train_worker.main()
       result['training' if mode=='train' else 'evaluation'][level]={'status':'passed','seconds':round(time.monotonic()-tick,2)}
       print('PASS',level,mode,flush=True)
    result['seconds']=round(time.monotonic()-started,2)
    (report_dir/'ml-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

if __name__=="__main__":main()
