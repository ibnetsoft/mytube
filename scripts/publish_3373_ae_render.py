"""Register and save this authorized render in AIR Studio's render history."""
import sys, json, uuid, datetime, os, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from render_3373_ae_final import RUN, signed
import requests
from concurrent.futures import ThreadPoolExecutor
BASE=os.environ['NEXT_PUBLIC_SUPABASE_URL']+'/rest/v1/'
HEAD={'apikey':os.environ['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SERVICE_ROLE_KEY'],'Prefer':'return=representation'}
PID='e9233112-f0d7-4b35-91bf-2f892844eb30'
VERSION=int(os.environ.get('AIR_RENDER_VERSION','2'))
def api(method,table,payload=None,params=None):
    r=requests.request(method,BASE+table,headers=HEAD,json=payload,params=params,timeout=40);r.raise_for_status();return r.json() if r.content else None
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def upload(path,object_path,mime):
    with path.open('rb') as f:
        r=requests.put(signed('air-studio-prod',object_path,'PUT',mime),data=f,headers={'Content-Type':mime},timeout=(15,600));r.raise_for_status()
    return signed('air-studio-prod',object_path)
def main():
    receipt=RUN/'queue_receipt.json'
    if sys.argv[1]=='start':
        if receipt.exists():return
        old=api('GET','remote_render_queue',params={'metadata->>std_web_project_id':'eq.'+PID,'order':'created_at.desc','limit':'1'})[0]
        task=str(uuid.uuid4());meta={**old['metadata'],'render_version':VERSION,'previous_render_queue_id':old['id'],'job_stage':'rendering','admin_publish_ready':False,'admin_publish_status':'render_pending','ae_scene_numbers':list(range(1,26)),'ae_project_local_path':str(RUN.parent/'ae_3373_run/v1/scenes_01_25.aep')}
        for k in ['gcs_path','gcs_public_url','result_public_url','storage_path','gcs_thumbnail_url']:meta.pop(k,None)
        row={'id':task,'project_id':old['project_id'],'project_name':old['project_name'],'email':old['email'],'status':'rendering','progress':5,'message':'AE scenes 1–25 applied; final rendering on local PC','render_mode':'gcs_api','worker_id':'local-ae-final-3373','claimed_at':now(),'updated_at':now(),'metadata':meta}
        result=api('POST','remote_render_queue',row)[0];receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('REGISTERED',task)
        return
    row=json.loads(receipt.read_text(encoding='utf-8'));task=row['id']
    if sys.argv[1]=='progress':
        p=RUN/'progress.txt'
        if p.exists():
            state=json.loads(p.read_text(encoding='utf-8'));api('PATCH','remote_render_queue',{'progress':state['progress'],'message':state['message'],'updated_at':now()},{'id':'eq.'+task});print(state)
        return
    out=RUN/'output.mp4'
    config=json.loads((RUN/'config.json').read_text(encoding='utf-8'))
    overlay=RUN/'overlays/std_template_overlay.png'
    if config.get('render_settings',{}).get('std_template_contract') == 'transparent-text-v1' and overlay.exists():
        overlay_path=f'std-projects/{PID}/render-packages/{task}/overlays/std_template_overlay.png'
        overlay_url=upload(overlay,overlay_path,'image/png')
        config['template_overlay_filename']='std_template_overlay.png'
        config['asset_manifest']['files'].append({'asset_type':'template_overlay','path':'overlays/std_template_overlay.png',
            'file_name':'std_template_overlay.png','mime_type':'image/png','size':overlay.stat().st_size,
            'storage_provider':'gcs','gcs_bucket':'air-studio-prod','gcs_path':overlay_path,'storage_bucket':'air-studio-prod',
            'storage_path':overlay_path,'gcs_signed_url':overlay_url})
    # Archive the exact AE inputs and package for reproducible re-renders.
    def archive_ae(entry):
        n=entry.get('scene_number',0)
        if 1<=n<=25:
            local=RUN/'images'/f'scene_{n:03d}.mp4'
            if entry.get('reuse_verified_from_render_version') and hashlib.sha256(local.read_bytes()).hexdigest()==entry.get('sha256'):
                entry['gcs_signed_url']=signed(entry['gcs_bucket'],entry['gcs_path']);return
            path=f'std-projects/{PID}/render-packages/{task}/ae/scene_{n:03d}.mp4'
            url=upload(RUN/'images'/f'scene_{n:03d}.mp4',path,'video/mp4')
            entry.update(path=f'images/scene_{n:03d}.mp4',file_name=f'scene_{n:03d}.mp4',asset_type='video',mime_type='video/mp4',gcs_bucket='air-studio-prod',gcs_path=path,storage_bucket='air-studio-prod',storage_path=path,gcs_signed_url=url,size=(RUN/'images'/f'scene_{n:03d}.mp4').stat().st_size)
        elif entry.get('gcs_bucket') and entry.get('gcs_path'):
            entry['gcs_signed_url']=signed(entry['gcs_bucket'],entry['gcs_path'])
    package=RUN/'archived_config.json'
    if package.exists():config=json.loads(package.read_text(encoding='utf-8'))
    else:
        with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(archive_ae,config['asset_manifest']['files']))
        package.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    config_path=f'std-projects/{PID}/render-packages/{task}/config.json';config_url=upload(package,config_path,'application/json')
    if sys.argv[1]=='archive':
        print('AE_INPUTS_ARCHIVED',flush=True);return
    assert out.exists() and (RUN/'final_qa.json').exists()
    name=f'3373_AE_final_v{VERSION}.mp4';path=f'std-renders/{task}/{name}'
    print('UPLOADING_FINAL',out.stat().st_size,flush=True);url=upload(out,path,'video/mp4')
    thumb=config.get('thumbnail_filename');thumburl=None
    if thumb and (RUN/thumb).exists():thumburl=upload(RUN/thumb,f'std-renders/{task}/{thumb}','image/png' if thumb.endswith('.png') else 'image/jpeg')
    metadata={**config.get('project_upload_metadata',{}),'gcs_video_path':path,'gcs_video_url':url,'gcs_thumbnail_url':thumburl,'video_file':name,'thumbnail_file':thumb,'render_mode':'gcs_api','ae_scene_numbers':list(range(1,26))}
    mf=RUN/'metadata.json';mf.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8');upload(mf,f'std-renders/{task}/metadata.json','application/json')
    meta={**row['metadata'],'job_stage':'completed','admin_publish_ready':True,'admin_publish_status':'pending_review','admin_action_required':'review_and_upload','gcs_bucket':'air-studio-prod','gcs_path':path,'storage_provider':'gcs','storage_bucket':'air-studio-prod','storage_path':path,'result_public_url':url,'gcs_public_url':url,'gcs_thumbnail_url':thumburl,'gcs_config':{'bucket':'air-studio-prod','path':config_path,'signed_url':config_url},'config_web_link':config_url,'asset_web_link':config_url,'asset_file_id':task,'config_file_id':task}
    meta.update(manifest_file_count=len(config['asset_manifest']['files']),asset_file_size=package.stat().st_size,config_file_size=package.stat().st_size,
        template_contract=config.get('render_settings',{}).get('std_template_contract'))
    completed=api('PATCH','remote_render_queue',{'status':'completed','progress':100,'message':'AE scenes applied; transparent template corrected; final rendering complete','asset_file_id':task,'asset_file_name':'config.json','result_file_id':url,'result_file_name':name,'completed_at':now(),'updated_at':now(),'metadata':meta},{'id':'eq.'+task})[0]
    project=api('GET','std_projects',params={'id':'eq.'+PID,'select':'progress_payload'})[0]
    progress={**(project.get('progress_payload') or {}),'remote_task_id':task,'remote_render_queue_id':task,'remote_render_mode':'gcs_api','remote_asset_file_id':task,'remote_asset_file_name':'config.json','remote_asset_web_link':config_url,'remote_render_queue_payload':completed,'latest_render_version':VERSION,'editing_render_version':None,'rerender_draft':False,'admin_publish_status':'pending_review'}
    api('PATCH','std_projects',{'progress_payload':progress,'updated_at':now()},{'id':'eq.'+PID})
    assert api('GET','remote_render_queue',params={'id':'eq.'+task,'select':'status,result_file_name'})[0]['status']=='completed'
    (RUN/'published_receipt.json').write_text(json.dumps(completed,ensure_ascii=False,indent=2),encoding='utf-8');print('SAVED_FINAL',task,flush=True)
if __name__=='__main__':main()
