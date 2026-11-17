from pathlib import Path
import random
import unittest
from PIL import Image,ImageDraw
from app.library_recognition import LibraryMatcher,ink_signature,sample_signature
from app.portable import encode_sample


def reference_match(image,templates,kind=''):
    query=ink_signature(image)
    if not query:return None
    variants=[frozenset((x+dx,y+dy) for x,y in query) for dx in (-1,0,1) for dy in (-1,0,1)]
    scores={}
    for candidate,value,template in templates:
        if kind and candidate!=kind:continue
        score=max(len(variant & template)/len(variant | template) for variant in variants)
        scores[candidate,value]=max(score,scores.get((candidate,value),0))
    ranked=sorted(scores.items(),key=lambda entry:(-entry[1],entry[0]))
    if not ranked:return None
    (candidate,value),score=ranked[0]
    return candidate,value,score,score-(ranked[1][1] if len(ranked)>1 else 0)


class MatchingOptimizationTests(unittest.TestCase):
    def fixtures(self):
        generator=random.Random(42);images=[]
        for index in range(16):
            image=Image.new('RGB',(40,40),'white');draw=ImageDraw.Draw(image)
            for _ in range(4):draw.line(tuple(generator.randint(3,36) for _ in range(4)),fill='black',width=generator.randint(1,4))
            images.append(image)
        payload={'symbols':{f'S{index}':{'samples':[encode_sample(image)]} for index,image in enumerate(images[:8])},'readable_samples':[{'transcription':str(index),'png':encode_sample(image)} for index,image in enumerate(images[8:])]}
        templates=[('cipher_symbol',f'S{index}',ink_signature(image)) for index,image in enumerate(images[:8])]+[('readable',str(index),ink_signature(image)) for index,image in enumerate(images[8:])]
        return images,payload,templates
    def test_packed_matching_equals_original_set_algorithm(self):
        images,payload,templates=self.fixtures();matcher=LibraryMatcher(payload)
        for image in images:
            for kind in ('','readable','cipher_symbol'):
                with self.subTest(kind=kind):self.assertEqual(matcher.match(image,kind),reference_match(image,templates,kind))
    def test_cache_does_not_change_results_or_collapse_ambiguity(self):
        images,payload,templates=self.fixtures();payload['symbols']['DUPLICATE']=payload['symbols']['S0']
        matcher=LibraryMatcher(payload)
        first=matcher.match(images[0]);second=matcher.match(images[0])
        self.assertEqual(first,second);self.assertEqual(first[3],0)
        self.assertEqual(len(matcher._matches),1)
    def test_duplicate_samples_do_not_duplicate_templates(self):
        images,payload,templates=self.fixtures();payload['symbols']['S0']['samples']*=3
        matcher=LibraryMatcher(payload);self.assertEqual(len(matcher.templates),16)
