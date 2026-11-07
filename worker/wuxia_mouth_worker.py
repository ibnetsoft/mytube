"""Durable script-worker art and finalized-recording jobs; never invokes AE."""
import copy
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def process_one():
    import ae_highlight_worker as ae
    from worker.wuxia_mouth_preparation import ROOT, prepare_art, bind_timing
    from worker.workflow_roles import assert_project, PREPARATION
    base, headers = ae._supabase()
    def rpc(name, data):
        return ae._request('POST', base+'/rest/v1/rpc/'+name, headers, json=data).json()
    token = str(uuid.uuid4())
    job = rpc('claim_std_wuxia_mouth', {'p_token': token})
    if not job:
        return False
    meta = copy.deepcopy(job['metadata'])
    stop, lost = threading.Event(), threading.Event()
    guard = threading.Lock()
    def save(**changes):
        with guard:
            if lost.is_set():
                raise RuntimeError('Mouth preparation lease lost')
            updated = {**meta, **changes}
            rows = ae._request('PATCH', base+'/rest/v1/std_project_assets', {**headers, 'Prefer':'return=representation'},
                params={'id':'eq.'+job['id'], 'metadata->>worker_token':'eq.'+token, 'metadata->>state':'eq.processing'},
                json={'metadata': updated, 'updated_at': ae._now()}).json()
            if not rows:
                lost.set()
                raise RuntimeError('Mouth preparation lease lost')
            meta.update(updated)
    def heartbeat():
        while not stop.wait(15):
            try:
                save(heartbeat_at=ae._now())
            except Exception:
                lost.set()
                return
    ticker = threading.Thread(target=heartbeat, daemon=True)
    ticker.start()
    def check():
        if lost.is_set():
            raise RuntimeError('Mouth preparation lease lost')
        rows = ae._request('GET', base+'/rest/v1/std_projects', headers,
            params={'id':'eq.'+job['project_id'], 'select':'id,status,submitted_at', 'limit':1}).json()
        assert_project(rows[0] if rows else None, PREPARATION)
    def download(ref, path):
        check()
        ae._download_gcs_file(ae.GcsRef(ref.get('gcs_bucket') or ref.get('storage_bucket'), ref.get('gcs_path') or ref.get('storage_path')), path)
    def upload(path, sha):
        check()
        bucket, key, url = ae._upload_gcs_file(path, 'std/'+job['project_id']+'/wuxia-mouth/'+sha+'.png', 'image/png')
        return verified_upload(ae, path, sha, bucket, key, url, check)
    try:
        check()
        inp = meta['input']
        source = inp['source']
        structure = {'wuxia_ae_package': source['package'], 'wuxia_mouth_policy': source['policy'],
                     'main_character': source['cast'].get('main'), 'supporting_characters': source['cast'].get('supporting'),
                     'character_anchors': source['cast'].get('anchors')}
        # Source-keyed, visually reviewed local caches survive retries and lease recovery.
        prepared = {a['asset_id']: a['art'] for a in inp.get('prepared_art') or []}
        states = [(sc, st) for sc in source['package']['scenes'] for st in sc['states']]
        if inp['task'] == 'timing' and all(st['asset_id'] in prepared for _, st in states):
            patches = [{'scene_id':sc['scene_id'], 'asset_id':st['asset_id'], 'sha256':st['sha256'], 'art':prepared[st['asset_id']]} for sc,st in states]
            count = sum(len(p['art']) for p in patches)
            result = {'states':patches, 'report':{'state':'prepared' if count else 'not_required', 'selection_complete':True, 'eligible_count':count, 'zero_eligible_valid':True}}
        else:
            result = prepare_art(structure, job['id'], download, upload, check)
        if inp['task'] == 'timing':
            audio = inp['recording']
            directory = ROOT / ('audio-'+audio['metadata']['sha256'])
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / 'recording.audio'
            if not path.exists():
                download(audio['metadata'], path)
            result = bind_timing(structure, inp['rows'], audio, path, result)
            # Decode and verify the exact remote PNGs used by preview/native AE.
            from worker.wuxia_mouth import prepare as verify_mouths
            for patch in result['states']:
                if not patch['mouths']:
                    continue
                state = next(st for sc,st in states if sc['scene_id']==patch['scene_id'] and st['asset_id']==patch['asset_id'])
                image = directory / (state['sha256']+'.png')
                download(state, image)
                verify_mouths(image, patch['mouths'], directory/'verified', check, download, audio)
        check()
        stop.set()
        ticker.join(timeout=20)
        if lost.is_set():
            raise RuntimeError('Mouth preparation lease lost')
        rpc('finish_std_wuxia_mouth', {'p_job_id':job['id'], 'p_token':token, 'p_result':result})
    except Exception as exc:
        stop.set()
        ticker.join(timeout=20)
        if not lost.is_set():
            waiting = str(exc).startswith('waiting_images:')
            attempts = int(meta.get('attempts',0))+(0 if waiting else 1)
            save(state='queued', worker_token=None, attempts=attempts, error=None if waiting else str(exc)[:1000],
                 waiting_reason='waiting_images' if waiting else None,
                 retry_after=(datetime.now(timezone.utc)+timedelta(seconds=30 if waiting else min(1800,30*2**min(attempts,6)))).isoformat())
    finally:
        stop.set()
    return True


def prepare_topic(topic_id, structure, store):
    """Image publication before user assignment. Missing originals wait for publication."""
    from worker.wuxia_mouth_preparation import prepare_art
    policy = structure.get('wuxia_mouth_policy') or {}
    if policy.get('auto_prepare') is not True or policy.get('enabled') is False:
        return {'state':'disabled'}
    import ae_highlight_worker as ae
    package = structure.get('wuxia_ae_package') or {}
    if package.get('contract') != 'wuxia_still_ae_episode/v1' or not package.get('scenes') or any(not sc.get('states') for sc in package['scenes']):
        return {'state':'waiting_images'}
    required = [s for sc in package.get('scenes',[]) for s in sc.get('states',[]) if any(
        g.get('kind')=='speech_bubble' and g.get('state_asset_id')==s.get('asset_id') for g in sc.get('graphics',[]))]
    if any(not all(s.get(k) for k in ('sha256','gcs_bucket','gcs_path')) for s in required):
        return {'state':'waiting_images'}
    def check():
        rows,_ = store.request('GET','topics_queue',params={'id':'eq.'+str(topic_id),'select':'id,status,assigned_at','limit':1})
        if not rows or rows[0].get('status') != 'pending' or rows[0].get('assigned_at'):
            raise RuntimeError('Topic ownership changed during mouth preparation')
    def download(ref,path):
        check()
        ae._download_gcs_file(ae.GcsRef(ref['gcs_bucket'],ref['gcs_path']),path)
    def upload(path,sha):
        check()
        bucket,key,url = ae._upload_gcs_file(path,'topics/'+str(topic_id)+'/wuxia-mouth/'+sha+'.png','image/png')
        return verified_upload(ae, path, sha, bucket, key, url, check)
    result = prepare_art(structure,'topic-'+str(topic_id),download,upload,check)
    saved,_ = store.request('POST','rpc/publish_wuxia_topic_mouth_art',body={
        'p_topic_id':topic_id,'p_expected_package':package,'p_result':result})
    if not saved.get('applied'):
        raise RuntimeError('Topic mouth source changed before publication')
    return result['report']


def verified_upload(ae, path, sha, bucket, key, url, check):
    from ae_mouth import digest
    check()
    downloaded = path.with_suffix('.remote.png')
    ae._download_gcs_file(ae.GcsRef(bucket,key),downloaded)
    if digest(downloaded) != sha:
        raise ValueError('Uploaded mouth PNG checksum mismatch')
    return {'sha256':sha,'gcs_bucket':bucket,'gcs_path':key,'media_url':url}
