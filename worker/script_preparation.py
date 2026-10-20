"""Pre-submit asset preparation, serialized with the script worker's CLI jobs."""
import threading
from worker.workflow_roles import PREPARATION, asset_query, belongs

def process_one():
    import ae_highlight_worker as ae
    base, headers = ae._supabase()
    rows = ae._request('GET',base+'/rest/v1/std_project_assets',headers,params=asset_query(PREPARATION,{
        'select':'*','metadata->>kind':'in.(ae_scene_preparation,ae_speaker_coordinates,region_layer_package,motion_preview)',
        'metadata->>state':'in.(queued,processing)','order':'created_at.asc','limit':'100'})).json()
    for row in rows:
        if not belongs(row,PREPARATION):continue
        meta=row.get('metadata') or {}
        if meta.get('state') not in ('queued','processing'):continue
        kind=meta['kind']
        if kind=='ae_scene_preparation':
            from worker.ae_scene_preparation import process_one as run
        elif kind=='ae_speaker_coordinates':
            from worker.ae_speaker_coordinates import process_one as run
        elif kind=='region_layer_package':
            from worker.ae_region_motion_worker import process_one as run
        else:
            from worker.motion_preview_worker import process_one as run
        return run(stage=PREPARATION)
    return False

def start_preparation_loop(jobs):
    stop=threading.Event()
    def poll():
        while not stop.is_set():
            try:
                if not jobs.inflight:
                    jobs.pool.submit(process_one).result()
            except Exception:
                import logging
                logging.getLogger(__name__).warning('Pre-submission asset preparation unavailable; existing assets preserved')
            stop.wait(5)
    threading.Thread(target=poll,name='script-asset-preparation',daemon=True).start()
    return stop
