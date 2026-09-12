"""All Codex thumbnails are editable drafts; only the user's Save flattens them."""
from copy import deepcopy

CONTRACT = 'editable-background-v1'

def can_sync_background(project, source_script=None):
    if project.get('status') not in ('claimed','in_progress') or project.get('submitted_at'): return False
    editor=project.get('project_payload') or {}; progress=project.get('progress_payload') or {}
    design=editor.get('thumbnail_design') or progress.get('thumbnail_design') or {}
    if editor.get('thumbnail_completed') or progress.get('thumbnail_completed') or design.get('saved_at'): return False
    if design and design.get('source') != 'codex': return False
    if source_script and editor.get('script') and editor['script'] != source_script: return False
    return True

def thumbnail_draft(hooks, layers=None, title=''):
    cleaned=[]
    for i,layer in enumerate(layers if isinstance(layers,list) else []):
        if not isinstance(layer,dict) or not str(layer.get('text') or '').strip(): continue
        cleaned.append({'id':f'codex-thumbnail-{i+1}','text':str(layer['text']).strip()[:40],
            'fontSize':34 if i==0 else 26,'fontFamily':'GmarketSansBold',
            'color':'#ffeb3b' if i==0 else '#ffffff','strokeColor':'#000000','strokeWidth':3,
            'x':50,'y':60 if i==0 else 86})
        if len(cleaned)==2: break
    if not cleaned:
        text=next((str(t).strip() for t in (hooks or []) if str(t).strip()),'')
        if text: return thumbnail_draft(hooks,[{'text':text}],title)
    return {'contract':CONTRACT,'source':'codex','title':title,'layout':'face','style':'realistic',
        'step':3,'coordinate_width':480,'bg_url':None,'editor_bg_url':None,
        'thumbnail_url':None,'text_layers':cleaned,'render_status':'awaiting_background'}

def background_ready(progress, url):
    result=deepcopy(progress)
    design=deepcopy(progress.get('thumbnail_design') or thumbnail_draft(progress.get('thumbnail_hook_texts')))
    design.update(contract=CONTRACT,coordinate_width=480,bg_url=url,editor_bg_url=url,
        thumbnail_url=None,render_status='awaiting_user_save')
    design.pop('saved_at',None)
    result.update(thumbnail_design=design,thumbnail_bg_url=url,thumbnail_url=None,
        thumbnail_completed=False,thumbnail_confirmed_at=None,thumbnail_generation_status='completed',
        thumbnail_render_status='awaiting_user_save')
    return result
