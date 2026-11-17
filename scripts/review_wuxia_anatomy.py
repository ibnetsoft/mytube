"""Read-only actual artwork audit; emit repair requests without changing episodes."""
import argparse
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scene',type=int,action='append',help='Audit only these original scenes')
    p.add_argument('--asset-id',action='append',help='Audit only these exact state assets')
    a=p.parse_args()
    from worker.wuxia_art_quality import audit_package
    from worker.codex_content_runner import CodexStagedContentRunner
    data=json.loads(a.package.read_text(encoding='utf-8'))
    payload=data.get('project_payload',data)
    structure=payload.get('structure',payload)
    pkg=structure.get('wuxia_ae_package',structure)
    if not isinstance(pkg.get('scenes'),list):raise ValueError('Missing actual artwork package')
    scenes=pkg['scenes']
    if a.scene:
        wanted={f'S{n:02d}' for n in a.scene}
        scenes=[s for s in scenes if str(s['scene_id']).split('_')[-1] in wanted]
        if len(scenes)!=len(wanted):raise ValueError('Requested scene is absent')
    if a.asset_id:
        wanted=set(a.asset_id)
        found={st['asset_id'] for sc in scenes for st in sc['states']}
        if not wanted <= found:raise ValueError('Requested state is absent')
        scenes=[{**sc,'states':[st for st in sc['states'] if st['asset_id'] in wanted]} for sc in scenes]
        scenes=[sc for sc in scenes if sc['states']]
    structure={**structure,'wuxia_ae_package':{**pkg,'scenes':scenes}}
    source_root=a.source_root.resolve()
    def download(state,target):
        source=(source_root/state['file']).resolve()
        if not source.is_relative_to(source_root):raise ValueError('Source outside root')
        shutil.copyfile(source,target)
    results=audit_package(structure,'manual-anatomy-audit',download,lambda:None,CodexStagedContentRunner())
    report={'contract':'wuxia_anatomy_audit/v1','scope':'actual saved source pixels; no production writes',
        'states':results,'repair_requests':[r['repair_request'] for r in results.values() if r['repair_request']],
        'all_sources_passed':all(r['passed'] for r in results.values()),'actual_repairs_performed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'states_reviewed':len(results),'repair_requests':len(report['repair_requests']),
        'all_sources_passed':report['all_sources_passed'],'report':str(a.output)},ensure_ascii=False))
if __name__=='__main__':main()
