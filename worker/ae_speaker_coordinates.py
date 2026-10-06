"""Prepare speaker geometry once before submission; do not generate new voices or mouth patches."""
import copy
from pathlib import Path

def process_one():
    import ae_highlight_worker as ae
    from ae_mouth import locate_speakers, digest
    from codex_content_runner import CodexStagedContentRunner
    from lipsync_video_worker import ref
    base, headers = ae._supabase()
    url = base + '/rest/v1/std_project_assets'
    jobs = ae._request('GET', url, headers, params={'select':'*','metadata->>kind':'eq.ae_speaker_coordinates','metadata->>state':'in.(queued,processing)','order':'created_at.asc','limit':'1'}).json()
    if not jobs: return False
    job = jobs[0]; meta = copy.deepcopy(job['metadata'])
    claimed = ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},json={'metadata':{**meta,'state':'processing'},'updated_at':ae._now()}).json()
    if not claimed: return False
    meta = claimed[0]['metadata']
    def save(**changes):
        meta.update(changes)
        ae._request('PATCH',url,headers,params={'id':'eq.'+job['id']},json={'metadata':meta,'updated_at':ae._now()})
    try:
        runner = CodexStagedContentRunner()
        directory = Path(ae.ROOT if hasattr(ae,'ROOT') else Path(__file__).resolve().parents[1]) / 'output' / 'speaker-coordinates' / meta['fingerprint']
        directory.mkdir(parents=True,exist_ok=True)
        results = {r['number']:r for r in meta.get('results',[])}
        previous = ae._request('GET',url,headers,params={'select':'metadata','project_id':'eq.'+job['project_id'],
            'metadata->>kind':'eq.ae_speaker_coordinates','metadata->>state':'eq.ready','order':'created_at.desc','limit':'100'}).json()
        reusable = [r for old in previous if old['metadata'].get('input',{}).get('cast_key')==meta['input']['cast_key'] for r in old['metadata'].get('results',[])]
        for scene in sorted(meta['input']['scenes'],key=lambda s:s['number']):
            if scene['number'] in results: continue
            bucket,path = ref(scene['image'])
            image = directory / f"scene-{scene['number']}.png"
            if not image.exists(): ae._download_gcs_file(ae.GcsRef(bucket,path),image)
            names = {r['speaker'] for r in scene['rows']}
            cached = next((r for r in reusable if r['image_id']==scene['image']['id'] and r['source_path']==path
                and r['source_sha256']==digest(image) and names.issubset({v['speaker'] for v in r['speakers']})),None)
            speakers = [r for r in cached['speakers'] if r['speaker'] in names] if cached else locate_speakers(runner,meta['fingerprint']+'-'+str(scene['number']),scene,image,scene['rows'],meta['input']['cast'])
            if any(r['status']=='visible' and not r.get('face_box') for r in speakers): raise ValueError('Face bounds are missing')
            results[scene['number']] = {'number':scene['number'],'image_id':scene['image']['id'],'source_path':path,'source_sha256':digest(image),'speakers':speakers}
            save(results=list(results.values()))
        save(state='ready',results=list(results.values()),reviewer='local-codex-visual-analysis')
    except Exception as exc: save(state='needs_review',error=str(exc)[:500])
    return True
