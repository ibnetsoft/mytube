"""Submission is the ownership boundary, shared by schedulers and queue claimers."""
PREPARATION = 'preparation'
POSTPRODUCTION = 'postproduction'
CLOSED = frozenset(('approved', 'canceled', 'cancelled', 'completed', 'paid'))

def project_stage(project):
    if not isinstance(project, dict) or project.get('status') in CLOSED:
        return None
    return POSTPRODUCTION if project.get('submitted_at') else PREPARATION

def asset_stage(row):
    meta = row.get('metadata') or {}
    kind = meta.get('kind')
    if kind in ('ae_scene_preparation', 'ae_speaker_coordinates', 'region_layer_package'):
        return PREPARATION
    if kind == 'motion_preview':
        return PREPARATION if (meta.get('input') or {}).get('task') == 'direction' else POSTPRODUCTION
    if kind == 'ae_mouth_job' and meta.get('preview_sync'):
        return None  # Retired pre-submit AE queue, never a final-submission job.
    return POSTPRODUCTION if kind in ('ae_mouth_job','motion_automation','effectcraft_automation','horizontal_webtoon_automation','region_motion_plan') else None

def asset_query(stage, params):
    if stage not in (PREPARATION, POSTPRODUCTION):
        raise ValueError('Unknown workflow owner')
    result = dict(params)
    result['select'] = result.get('select','*') + ',workflow_project:std_projects!inner(id,submitted_at,status)'
    result['workflow_project.submitted_at'] = 'is.null' if stage == PREPARATION else 'not.is.null'
    result['workflow_project.status'] = 'not.in.(' + ','.join(sorted(CLOSED)) + ')'
    if result.get('metadata->>kind') == 'eq.ae_mouth_job':
        result['and'] = '(or(metadata->>preview_sync.is.null,metadata->>preview_sync.eq.false))'
    return result

def belongs(row, stage):
    project = row.get('workflow_project')
    return asset_stage(row) == stage and project_stage(project) == stage

def assert_project(project, stage):
    if project_stage(project) != stage:
        raise ValueError('제출 전 준비는 대본워커, 제출 후 제작은 통합워커에서 처리합니다. 프로젝트 제출 상태를 확인하세요.')
