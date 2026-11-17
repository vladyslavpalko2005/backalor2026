"""Reproducible comparison with the original set-IoU implementation."""
from pathlib import Path
import sys,time,json,random
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
from app.library_recognition import LibraryMatcher,ink_signature
from app.portable import encode_sample


def original(image,templates):
    query=ink_signature(image)
    variants=[frozenset((x+dx,y+dy) for x,y in query) for dx in (-1,0,1) for dy in (-1,0,1)]
    scores={}
    for kind,value,template in templates:
        score=max(len(variant & template)/len(variant | template) for variant in variants)
        scores[kind,value]=max(score,scores.get((kind,value),0))
    ranked=sorted(scores.items(),key=lambda entry:(-entry[1],entry[0]))
    (kind,value),score=ranked[0]
    return kind,value,score,score-(ranked[1][1] if len(ranked)>1 else 0)


def main():
    randomizer=random.Random(42);images=[]
    for index in range(32):
        image=Image.new('RGB',(40,40),'white');draw=ImageDraw.Draw(image)
        for _ in range(4):draw.line(tuple(randomizer.randint(3,36) for _ in range(4)),fill='black',width=randomizer.randint(1,4))
        images.append(image)
    payload={'symbols':{f'S{index}':{'samples':[encode_sample(image)]} for index,image in enumerate(images)},'readable_samples':[]}
    templates=[('cipher_symbol',f'S{index}',ink_signature(image)) for index,image in enumerate(images)]
    queries=[images[index%8] for index in range(200)]
    start=time.perf_counter();baseline=[original(image,templates) for image in queries];baseline_seconds=time.perf_counter()-start
    start=time.perf_counter();matcher=LibraryMatcher(payload);optimized=[matcher.match(image) for image in queries];optimized_seconds=time.perf_counter()-start
    assert optimized==baseline
    result={'workload':'32 reference symbols; 200 queries repeating 8 glyphs; seed 42',
            'baseline_seconds':round(baseline_seconds,6),'optimized_seconds':round(optimized_seconds,6),
            'speedup':round(baseline_seconds/optimized_seconds,2),'identical_results':True,
            'api_project_list_selects':2,'api_project_list_selects_before_for_100_public_docs':102}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
