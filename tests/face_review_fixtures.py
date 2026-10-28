"""Explicit image/reviewer dependency fakes for pre-existing storage/census unit tests.
Production face review has separate real-file, rejection and retry tests.
"""
import hashlib
from pathlib import Path
from PIL import Image

def install(monkeypatch,tmp_path):
    import worker.codex_character_assets as package
    import codex_character_assets as plain
    from worker.character_face_distinctness import POLICY
    original=package.generate_character_references
    class Reviewer:
        def review(self,c,path,refs):
            def sh(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
            return {'policy':POLICY,'source_sha256':sh(path),'passed':True,'pairs':[{'candidate_key':c['character_key'],'candidate_sha256':sh(path),'other_key':o['character_key'],'other_sha256':sh(p),'result':{'passed':True,'similarity':'low','differences':[{'axis':a,'evidence':'Distinct fixture '+a} for a in ('eyes','nose','jaw')],'reason':'Fixture only'}} for o,p in refs]}
    def wrapped(*args,**kwargs):
        generator=kwargs.get('generator');store=kwargs.get('store')
        if generator:
            class Generator:
                def generate(self,*a,**k):
                    path=Path(generator.generate(*a,**k))
                    if not path.is_absolute():path=tmp_path/path.name
                    if not path.exists():Image.new('RGB',(512,512),'blue').save(path)
                    return path
            kwargs['generator']=Generator()
        if store and not hasattr(store,'load_portrait'):
            def load(c,d):
                d.mkdir(parents=True,exist_ok=True);p=d/(c['character_key']+'.png');Image.new('RGB',(512,512),'blue').save(p);return p
            monkeypatch.setattr(store,'load_portrait',load,raising=False)
        kwargs['reviewer']=Reviewer()
        return original(*args,**kwargs)
    monkeypatch.setattr(package,'generate_character_references',wrapped)
    monkeypatch.setattr(plain,'generate_character_references',wrapped)
