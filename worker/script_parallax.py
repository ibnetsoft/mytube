"""Bind script-selected still parallax to registered, reviewed layer packages."""
import copy

ROLES = ('background', 'character', 'foreground')
TASK = """For still-image scenes 19 onward, explicitly consider depth_parallax only when real depth separation supports the script beat. Do not select every still or use parallax as decoration. Scenes 1..18 are uploaded moving videos: never add depth_parallax there. When selected, make depth_parallax the primary effect, explain the script-grounded dramatic intent, and request exactly background, character, foreground layers. Each required_layers item must include role, purpose, source:'registered_scene', and image_prompt describing that exact depth plane. Background must be a clean full-canvas reconstruction behind removed subjects; character is a transparent middle-plane cutout; foreground is a transparent near-plane cutout. All share the final source image's camera, layout, canvas and lighting. No replacement compositions, copied flattened fake layers, invented foreground objects or depth mattes as substitutes. Do not combine with pose_change/prop_motion/shot_sequence. If real foreground and middle-plane content cannot be justified, choose hold or a restrained camera move instead. Layers must later pass actual image and composite review before submission; missing material requires repair."""


def selection(scene, direction):
    if 'depth_parallax' not in direction.get('ae_operations', []):
        return {'enabled': False, 'reason': 'No script-selected depth operation'}
    number = int(scene.get('scene_number') or scene.get('scene_order') or 0)
    if number < 19 or scene.get('visual_type') == 'video' or scene.get('video_generation_mode') == 'user_upload':
        raise ValueError('Parallax requires a still scene 19 onward; preserve uploaded video motion')
    if direction.get('primary_effect') != 'depth_parallax' or set(direction['ae_operations']) & {'pose_change','prop_motion','shot_sequence'}:
        raise ValueError('Parallax must be a distinct primary still-scene direction')
    specs = direction.get('layer_specs') or []
    if len(specs) != 3 or {s.get('role') for s in specs} != set(ROLES):
        raise ValueError('Script parallax requires exactly background, character and foreground layers')
    for layer in specs:
        if not layer.get('purpose') or not layer.get('image_prompt'):
            raise ValueError('Each parallax layer needs script purpose and generation instructions')
    return {'enabled':True, 'contract':'script_parallax/v1', 'selection_source':'scene_visual_director',
            'reason':direction['dramatic_intent'], 'source':'single_registered_scene_image',
            'layers':copy.deepcopy(specs), 'required_layers':list(ROLES),
            'review_required':True, 'failure_policy':'needs_repair',
            'max_move_ratio':min(.025, direction['effect_limits']['max_move_ratio'])}


def bind_packages(scenes):
    selected=[]
    for scene in scenes:
        direction=scene.get('scene_direction_plan') or scene.get('ae_directorial_plan') or {}
        plan=selection(scene,direction)
        scene['parallax_plan']=plan
        if not plan['enabled']:continue
        duration=float(scene.get('duration_seconds') or scene.get('target_duration') or 4)
        scene['ae_effect_plan']={**(scene.get('ae_effect_plan') or {}), 'enabled':True,
            'template':'parallax_layered_scene','template_source':'scene_visual_director',
            'duration_seconds':duration,'direction':plan['reason'],
            'asset_requirements':{'required_layers':list(ROLES),'optional_layers':[]},
            'scene_direction_plan':copy.deepcopy(direction), 'directorial_plan':copy.deepcopy(direction),
            'vfx':['approved_layer_parallax'],'fallback':'needs_repair'}
        selected.append(int(scene.get('scene_number') or scene.get('scene_order')))
    return selected
