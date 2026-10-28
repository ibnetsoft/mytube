"""Explicitly authorized 3376/3377 source-bound mouth preview recovery."""
import argparse,copy,dataclasses,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
os.environ['CODEX_CONTENT_MODEL']='gpt-6.1-sol'
_original_popen=subprocess.Popen
def http_cli(command,*args,**kwargs):
    if isinstance(command,(list,tuple)) and Path(str(command[0])).name.lower() in ('codex','codex.exe','codex.cmd'):
        command=list(command)+['-c','mcp_servers.supabase.enabled=false','-c','features.apps=false','-c','features.plugins=false','-c','model_provider="openai_http"','-c','model_providers.openai_http.name="OpenAI HTTP"','-c','model_providers.openai_http.wire_api="responses"','-c','model_providers.openai_http.requires_openai_auth=true','-c','model_providers.openai_http.supports_websockets=false']
    return _original_popen(command,*args,**kwargs)
subprocess.Popen=http_cli
import generated_speaker_coordinates as geometry
import cowork_scene_assets as publisher
from ae_mouth import digest
from codex_content_runner import CodexStagedContentRunner
from worker_config import OUTPUT_DIR
class EvidenceRunner(CodexStagedContentRunner):
    feedback=[]
    def _stage(self,identity,name,context,task):
        if self.feedback and name in ('03_ae_mouth_crop_localization','03_ae_mouth_geometry_review'):
            context={**context,'previous_rejected_landmarks':self.feedback}
            task+=' For a partial or hidden mouth, return status=occluded and render_policy=preserve_original; never animate moustache-covered or turned-away lips. Confidence refers to the supported identity/visibility assessment. The lip_center must lie on the lip line between its endpoints, not on the lower lip or bottom of an open cavity. Correct the previously rejected landmarks against the actual attached pixels. Do not repeat a rejected nose/lip location. Independent review must still reject any remaining error.'
        return super()._stage(identity,name,context,task)

from prepared_mouth_layers import prepare_scene
from prepared_mouth_preview import prepare_preview
from manga_layer_generation import NativeCodexLayerGenerator
BASE=ROOT/'output/codex-local-console/two-topic-mouths'
def upload(file,path,mime):
    result=subprocess.run(['node',str(ROOT/'scripts/upload_two_topic_mouth_file.cjs'),str(file),path,mime],cwd=ROOT,capture_output=True,text=True,encoding='utf8',timeout=120,check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])
def preserved_preview(topic,number,image,geometry,folder):
    from ae_media_utils import ffmpeg,run
    from ae_mouth import digest
    file=folder/f'scene-{number:03d}-preserve-original-1080p.mp4'
    if not file.exists():
        run([ffmpeg(),'-y','-loop','1','-i',str(image),'-t','3','-r','24','-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1','-c:v','h264_nvenc','-preset','p4','-cq','18','-pix_fmt','yuv420p','-an',str(file)])
    artifact=upload(file,f'topics/{topic}/mouth-previews/{digest(image)}-preserve-original-1080p.mp4','video/mp4')
    return {'state':'ready','kind':'mouth_preview','timing_mode':'preview_cycle','voice_synced':False,
        'duration_seconds':3,'gcs_bucket':artifact['bucket'],'gcs_path':artifact['path'],'url':artifact['url'],
        'sha256':artifact['sha256'],'source_sha256':digest(image),'prepared_keys':[],
        'preserve_original':True,'reason':'Verified speaker is offscreen or lips are occluded; preserve original pixels.'}
def upload_adapter(file,path,mime):
    result=upload(file,path,mime)
    return result['bucket'],result['path'],result['url']

TARGETS={3376:[23,37,38,39,47,48,49,57,58,60],3377:[19,20,21,22,23,24,25,26,28,29]}
def write(file,value):
    file.parent.mkdir(parents=True,exist_ok=True)
    temp=file.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(file)
def status(**row):
    row['updated_at']=time.time();write(BASE/'progress.json',row);print(json.dumps(row,ensure_ascii=False),flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['geometry','images','publish'],required=True);parser.add_argument('--topic',type=int);parser.add_argument('--scene',type=int);parser.add_argument('--wait-geometry',action='store_true');args=parser.parse_args()
    runner=EvidenceRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
    generator=NativeCodexLayerGenerator(model='gpt-6.1-sol',timeout_seconds=600)
    for topic,numbers in TARGETS.items():
        if args.topic and topic!=args.topic:continue
        folder=BASE/str(topic);folder.mkdir(parents=True,exist_ok=True)
        row,structure,base,headers=publisher._topic(str(topic))
        write(folder/'current-source.json',{'topic':topic,'structure':structure})
        for number in numbers:
            if args.scene and number!=args.scene:continue
            try:
                scene=next(s for s in structure['scenes'] if int(s.get('scene_number') or s.get('scene_order'))==number)
                asset=scene['metadata']['cowork_image_asset'];image=folder/f'scene-{number:03d}.png'
                audit=json.loads((ROOT/f'output/two-topic-mouth-audit/{topic}.json').read_text(encoding='utf8'))
                original=next(s for s in audit['structure']['scenes'] if int(s.get('scene_number') or s.get('scene_order'))==number)['metadata']['cowork_image_asset']
                if (asset.get('gcs_bucket'),asset.get('gcs_path'))!=(original.get('gcs_bucket'),original.get('gcs_path')):
                    raise ValueError('User/source image changed since recovery started; do not attach old geometry')
                if not image.exists():image.write_bytes(publisher._download_gcs_bytes(asset['gcs_bucket'],asset['gcs_path']))
                receipt=folder/f'scene-{number:03d}-speaker-coordinates.json'
                saved=json.loads(receipt.read_text(encoding='utf8')) if receipt.exists() else None
                if args.wait_geometry and args.phase!='geometry':
                    deadline=time.monotonic()+1800
                    while (not saved or saved.get('state')!='ready') and time.monotonic()<deadline:
                        time.sleep(5)
                        saved=json.loads(receipt.read_text(encoding='utf8')) if receipt.exists() else None
                selection={'policy':{'enabled':True,'start_scene':19,'max_dialogue_scenes':10},'scene_numbers':numbers}
                status(topic=topic,scene=number,phase=args.phase,state='processing')
                if args.phase=='geometry':
                    if saved and saved.get('state')=='ready' and saved.get('source_sha256')==digest(image):
                        status(topic=topic,scene=number,phase=args.phase,state='reused');continue
                    runner.feedback=[]
                    if saved and saved.get('error'):
                        runner.feedback.append({'error':saved['error'],'correction':'Use original pixels for partial/hidden lips; correct inconsistent landmarks against the actual crop.'})
                    if saved and saved.get('state')=='needs_review':
                        for old_review in (OUTPUT_DIR/'codex_stage_requests').glob('*'+saved['fingerprint']+'*geometry_review*.response.json'):
                            try:
                                runner.feedback.extend(r for r in json.loads(old_review.read_text(encoding='utf8')).get('speakers',[]) if r.get('passed') is False)
                            except (OSError,ValueError): pass
                    result=geometry.analyze_scene(structure,scene,image,asset['gcs_bucket'],asset['gcs_path'],None,runner)
                    result['mouth_work_selection']=selection;write(receipt,result)
                    status(topic=topic,scene=number,phase=args.phase,state=result['state'],error=result.get('error'),speakers=[{'name':s['speaker'],'status':s['status'],'geometry':{k:(s.get('mouth_geometry') or {}).get(k) for k in ['orientation','pitch','mouth_visibility','render_policy']}} for s in result.get('speakers',[])])
                elif args.phase=='images':
                    if not saved or saved.get('state')!='ready' or saved.get('source_sha256')!=digest(image):raise ValueError('Verified current geometry is required')
                    saved['mouth_preparation']=prepare_scene(image,saved,runner=runner,generator=generator)
                    write(receipt,saved)
                    status(topic=topic,scene=number,phase=args.phase,state=saved['mouth_preparation']['state'])
                else:
                    if not saved or saved.get('state')!='ready' or saved.get('source_sha256')!=digest(image):raise ValueError('Verified current geometry is required')
                    prepared=saved.get('mouth_preparation') or {}
                    if prepared.get('state') not in ('ready','not_required'):raise ValueError('Reviewed mouth patches required')
                    from prepared_mouth_layers import ROOT as LAYERS
                    for entry in prepared.get('entries',[]):
                        entry.setdefault('assets',{})
                        for pose in ('closed','half','open'):
                            pose_file=LAYERS/entry['key']/(pose+'.png')
                            if entry['assets'].get(pose,{}).get('sha256')!=digest(pose_file):
                                entry['assets'][pose]=upload(pose_file,f'topics/{topic}/mouth-layers/{entry["key"]}/{pose}.png','image/png')
                    write(receipt,saved)
                    import ae_highlight_worker as ae
                    ae._upload_gcs_file=upload_adapter
                    preview=prepare_preview(topic,number,image,saved,prepared) if prepared.get('state')=='ready' else preserved_preview(topic,number,image,saved,folder)
                    if preview.get('state')!='ready':raise ValueError('No animated preview; preserve-original clip must be prepared explicitly')
                    saved['mouth_preview']=preview;write(receipt,saved)
                    expected=publisher._scene_asset_snapshot(scene);updated=copy.deepcopy(scene);updated['metadata']['cowork_image_asset']['speaker_geometry']=saved
                    publisher._patch_topic_scene_assets(str(topic),[{'scene_number':number,'expected_source':publisher._publish_source_snapshot(scene,number),'expected_assets':expected,'asset_patch':{'image_url':updated['image_url'],'asset_status':'ready','metadata':{'cowork_image_asset':updated['metadata']['cowork_image_asset']}}}],base,headers)
                    status(topic=topic,scene=number,phase=args.phase,state='published',gcs_path=preview['gcs_path'])
            except Exception as exc:
                status(topic=topic,scene=number,phase=args.phase,state='failed',error=str(exc)[:700])
    status(phase=args.phase,state='pass_completed')
if __name__=='__main__':main()
