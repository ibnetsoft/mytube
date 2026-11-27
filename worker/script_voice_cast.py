"""Preserve settings-only speaker bindings without changing finalized script text."""
import copy

def attach_voice_cast(candidate):
    profile=(candidate.get('manual_workflow') or {}).get('voice_cast')
    if not isinstance(profile,dict) or profile.get('contract')!='manual_voice_cast/v1':return candidate
    structure=candidate.setdefault('structure',{})
    public={k:copy.deepcopy(profile[k]) for k in ('contract','scope','source_episode','target_episode','source_project_id','source_mode','source_updated_at','applied_cast','narrator','voice_map','tts_settings','bindings','unassigned','generation_requested') if k in profile}
    structure['voice_cast']=public
    structure['voice_id']=profile['narrator']['voice_id'];structure['voice_name']=profile['narrator']['voice_name'];structure['voice_map']=copy.deepcopy(profile['voice_map'])
    structure.update(copy.deepcopy(profile.get('tts_settings',{})))
    candidate['voice_cast']=public
    return candidate
