"""Build explicit source-bound scene updates for incremental web delivery.

This module only prepares data; it does not mutate projects or approve artwork.
"""
from worker.script_manual_workflow import digest


def image_prompt_updates(workflow):
    stages = workflow.get('stages') or []
    if not stages or stages[0].get('status') not in ('review', 'approved'):
        raise ValueError('등록할 대본이 필요합니다.')
    scenes = stages[0].get('output', {}).get('scenes', [])
    by_id = {scene['scene_id']: scene for scene in scenes}
    if len(by_id) != len(scenes):
        raise ValueError('대본 씬 ID가 중복되었습니다.')
    updates = {}
    drafts = workflow.get('scene_image_prompts') or {}
    for scene_id, entry in drafts.items():
        scene = by_id.get(scene_id)
        if not scene or entry.get('status') not in ('review', 'approved'):
            continue
        if entry.get('source_hash') != digest(scene):
            continue
        text = str(entry.get('image_prompt') or '').strip()
        if text:
            updates[scene_id] = {'scene_id': scene_id, 'image_prompt': text}
    if len(stages) > 1 and stages[1].get('status') == 'approved':
        cuts = stages[1].get('output', {}).get('cuts') or []
        seen = set()
        for cut in cuts:
            scene_id = cut.get('scene_id')
            if scene_id not in by_id or scene_id in seen:
                raise ValueError('컷과 씬의 일대일 연결을 확인하세요. 여러 컷은 명시적인 컷 등록이 필요합니다.')
            seen.add(scene_id)
            prompt = str(cut.get('image_prompt') or '').strip()
            if not prompt or not cut.get('cut_id'):
                raise ValueError('확정된 컷 ID와 이미지 프롬프트가 필요합니다.')
            updates[scene_id] = {'scene_id': scene_id, 'cut_id': cut['cut_id'], 'image_prompt': prompt}
    return [updates[scene['scene_id']] for scene in scenes if scene['scene_id'] in updates]


def plan_prompt_patch(existing_scenes, updates, previous):
    """Prepare patches only where worker-owned text has not been edited in web.

    previous maps scene IDs to the last successfully delivered prompt. Empty web
    fields are writable on first delivery; all other divergent values conflict.
    No changes are made when any scene is ambiguous or conflicting.
    """
    index = {}
    for row in existing_scenes:
        scene_id = (row.get('metadata') or {}).get('scene_id')
        if scene_id:
            index.setdefault(scene_id, []).append(row)
    patches = []
    for update in updates:
        scene_id = update['scene_id']
        rows = index.get(scene_id, [])
        if len(rows) != 1:
            raise ValueError(f'{scene_id}: 웹 씬 연결이 없거나 중복되었습니다.')
        row = rows[0]
        current = str(row.get('image_prompt') or '')
        desired = update['image_prompt']
        if current == desired:
            continue
        if current and current != previous.get(scene_id):
            raise ValueError(f'{scene_id}: 유저웹 프롬프트가 변경되어 덮어쓰지 않았습니다.')
        patches.append({'id': row['id'], 'scene_id': scene_id,
                        'expected_image_prompt': current, 'image_prompt': desired,
                        'cut_id': update.get('cut_id')})
    return patches


def approved_fields(workflow):
    stages = workflow.get('stages') or []
    fields = {}
    for index, key in [(1, 'manual_image_prompts'), (2, 'manual_video_directions'), (3, 'manual_ae_directions')]:
        if len(stages) > index and stages[index].get('status') == 'approved':
            fields[key] = stages[index]['output']
    if len(stages) > 4 and stages[4].get('status') == 'approved':
        fields['sfx_generation_plan'] = {**stages[4]['output'], 'contract': 'elevenlabs_sfx_plan/v1', 'status': 'approved'}
    from worker.script_transition_export import transition_display_plan
    transition = transition_display_plan(workflow)
    if transition:
        fields['cut_transition_plan'] = transition
    return fields


def register(app, jobs):
    from fastapi import HTTPException
    from pydantic import BaseModel, Field
    from worker.script_worker_store import StoreUnavailable
    class DeliveryRequest(BaseModel):
        expected_hash: str = Field(min_length=64, max_length=64)
    globals()['DeliveryRequest'] = DeliveryRequest

    @app.post('/api/jobs/{identity}/web-delivery')
    def deliver(identity: str, body: DeliveryRequest):
        try:
            with jobs.lock:
                bundle = jobs.load(identity)
                job = bundle['job']
                candidate = bundle.get('candidate') or {}
                if job.get('worker_id') != jobs.worker_id or job.get('status') in ('queued', 'running', 'canceled', 'cancelled') or identity in jobs.inflight:
                    raise ValueError('이 컴퓨터의 실행 중이 아닌 작업을 선택하세요.')
                if digest(candidate) != body.expected_hash:
                    raise ValueError('작업 버전이 변경되었습니다. 다시 열어 주세요.')
                if not jobs.store or job.get('sync_status') != 'synced':
                    raise ValueError('먼저 대본 작업을 데이터베이스에 동기화하세요.')
                workflow = candidate.get('manual_workflow') or {}
                updates = image_prompt_updates(workflow)
                fields = approved_fields(workflow)
                remote = jobs.store.get(identity)
                if digest(remote['candidate']) != body.expected_hash:
                    raise ValueError('데이터베이스의 작업 버전이 다릅니다. 다시 동기화하세요.')
                revision = remote['job']['storage_revision']
                result, _ = jobs.store.request('POST', 'rpc/std_script_worker_deliver', body={
                    'p_job_id': identity, 'p_revision': revision, 'p_updates': updates, 'p_fields': fields})
                if not isinstance(result, dict) or not result.get('project_id'):
                    raise ValueError('등록 응답을 확인하지 못했습니다. 다시 요청해 확인하세요.')
                project, _ = jobs.store.request('GET', 'std_projects', params={
                    'id': 'eq.' + result['project_id'], 'employee_email': 'eq.supapitmusic@gmail.com',
                    'select': 'id,topic_queue_id,progress_payload', 'limit': 1})
                if len(project) != 1 or project[0]['topic_queue_id'] != result['topic_id']:
                    raise ValueError('프로젝트 재조회를 확인하지 못했습니다. 다시 요청해 확인하세요.')
                receipt = project[0].get('progress_payload', {}).get('script_worker_delivery', {})
                if receipt.get('job_revision') != revision:
                    raise ValueError('등록 버전 재조회가 일치하지 않습니다.')
                for update in updates:
                    if receipt.get('prompts', {}).get(update['scene_id']) != update['image_prompt']:
                        raise ValueError('이미지 프롬프트 등록 기록이 일치하지 않습니다.')
                if updates:
                    rows, _ = jobs.store.request('GET', 'std_project_scenes', params={
                        'project_id': 'eq.' + result['project_id'],
                        'select': 'scene_number,image_prompt,metadata->>scene_id', 'limit': 1000})
                    by_id = {r.get('scene_id'): r.get('image_prompt') for r in rows}
                    if any(by_id.get(u['scene_id']) != u['image_prompt'] for u in updates):
                        raise ValueError('이미지 프롬프트의 씬 재조회가 일치하지 않습니다.')
                jobs.update(identity, registered_topic_id=result['topic_id'], registered_project_id=result['project_id'],
                            web_delivery_summary={'prompt_count':result['prompt_count'], 'scene_count':result['scene_count']})
                return result
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except StoreUnavailable as exc:
            raise HTTPException(502, str(exc)) from exc
