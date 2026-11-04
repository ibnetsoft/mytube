"""Persistent supervised episode checkpoint; exits only at the authorized endpoint."""
import argparse,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from worker.wuxia_delivery_state import delivery_state

def checkpoint(root):
    state=delivery_state(root)
    if not state['complete'] and state['next_stage']=='continue_package_then_register':
        stages=[('script-final.json','script_and_review'),('image-generation-jobs.json','art_and_direction'),
                ('direction/source-verification.json','verify_art_and_direction'),
                ('packaging/review-translation-th.json','review_translation'),('packaging/publish-metadata.json','title_description_thumbnail'),
                ('packaging/thumbnail-final.png','save_editable_thumbnail'),('packaging/asset-upload-receipts.json','upload_and_verify_assets'),
                ('packaging/web-readiness.json','web_contract_check'),('packaging/registration-receipt.json','register_and_read_back')]
        state['next_stage']=next((stage for file,stage in stages if not (root/file).is_file()),'verify_registered_topic_readback')
        jobs_path=root/'image-generation-jobs.json'
        if jobs_path.is_file():
            jobs=json.loads(jobs_path.read_text(encoding='utf-8'))
            missing=[j['asset_id'] for j in jobs if not (root/'images'/(j['asset_id']+'.png')).is_file()]
            state.update(expected_images=len(jobs),saved_images=len(jobs)-len(missing),missing_asset_ids=missing)
            if missing and (root/'script-final.json').is_file():state['next_stage']='art_and_direction'
    state['authorized_endpoint']='user_web_registration_and_exact_readback'
    state['requires_final_audio_or_ae_render']=False
    path=root/'workflow-state.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
    return state

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--episode-dir',type=Path,required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    if args.preflight:
        missing=[m for m in ['PIL','psd_tools','requests','dotenv','google.auth'] if importlib.util.find_spec(m) is None]
        if missing:raise SystemExit('Install worker/requirements-script.txt before production; missing: '+','.join(missing))
    print(json.dumps(checkpoint(args.episode_dir),ensure_ascii=False))
