"""Project-safe, display-only transition metadata; no filesystem paths or render commands."""
import copy

def transition_display_plan(workflow):
    plan=(workflow.get('artwork_collection') or {}).get('transition_plan')
    if not isinstance(plan,dict) or plan.get('contract')!='manual_cut_transition_plan/v1':return None
    keys=('transition_id','from_cut_id','to_cut_id','effect','effect_label','duration_seconds','direction','reason','readiness','blocked_cut_ids','execution_owner','video_group_id')
    rows=[{k:copy.deepcopy(row[k]) for k in keys if k in row} for row in plan.get('transitions',[]) if isinstance(row,dict)]
    return {'contract':plan['contract'],'scope':'subtitle_display_only','transition_count':len(rows),'transitions':rows}

def attach_transition_display(candidate):
    plan=transition_display_plan(candidate.get('manual_workflow') or {})
    if plan:candidate.setdefault('structure',{})['cut_transition_plan']=plan
    return candidate
