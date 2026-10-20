"""Build pinned upstream binaries for the current host. Does not run tests or render media."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=int,default=2)
    args=parser.parse_args()
    pin=json.loads((ROOT/'auth-web/lib/effectcraftSource.json').read_text())
    source=ROOT/'.codex-temp/effectcraft-src'
    def run(command,**kw):subprocess.run(command,check=True,**kw)
    if not source.exists():
        source.parent.mkdir(parents=True,exist_ok=True)
        run(['git','clone','--depth','1',pin['repository'],str(source)])
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=pin['revision']:
        dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
        if dirty:raise RuntimeError('Upstream checkout has local changes; preserve it before rebuilding')
        run(['git','-C',str(source),'fetch','--depth','1','origin',pin['revision']])
        run(['git','-C',str(source),'checkout','--detach',pin['revision']])
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise RuntimeError('Build requires an unmodified upstream checkout')
    env=os.environ.copy()
    cargo=shutil.which('cargo')
    if not cargo:
        local=ROOT/'.codex-temp/cargo/bin'/('cargo.exe' if os.name=='nt' else 'cargo')
        if not local.exists():raise RuntimeError('Install Rust >=1.95 from https://rustup.rs, then run this build again')
        cargo=str(local);env.setdefault('CARGO_HOME',str(ROOT/'.codex-temp/cargo'));env.setdefault('RUSTUP_HOME',str(ROOT/'.codex-temp/rustup'))
    run([cargo,'build','--release','--locked','-p','effectcraft-cli','-p','effectcraft','--jobs',str(max(1,min(8,args.jobs)))],cwd=source,env=env)
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise RuntimeError('Build changed tracked upstream files; inspect before packaging')
    target=ROOT/'output/effectcraft'/(platform.system().lower()+'-'+platform.machine().lower())
    target.mkdir(parents=True,exist_ok=True)
    hashes={}
    for name in ('effectcraft-cli','effectcraft'):
        filename=name+('.exe' if os.name=='nt' else '')
        built=source/'target/release'/filename
        if not built.is_file():raise RuntimeError('Build artifact missing: '+str(built))
        shutil.copy2(built,target/filename)
        hashes[filename]=hashlib.sha256((target/filename).read_bytes()).hexdigest()
    # Unmodified upstream attribution and licenses travel with the binaries, including fonts/brand terms.
    for name in ('LICENSE-MIT','LICENSE-APACHE','NOTICE','ATTRIBUTION.md'):
        shutil.copy2(source/name,target/name)
    for parent in ('assets','docs/brand'):
        for file in (source/parent).rglob('*'):
            if file.is_file() and (file.name.startswith(('OFL','LICENSE')) or file.suffix=='.attribution'):
                destination=target/file.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,destination)
    manifest={**pin,'platform':platform.system(),'architecture':platform.machine(),'binaries':hashes,
              'functional_tests':'deferred_by_user','render_validation':'not_run'}
    (target/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(target),'manifest':manifest}),flush=True)

if __name__=='__main__':main()
