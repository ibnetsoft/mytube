"""Defaults for newly reserved scripts only; saved jobs never migrate implicitly."""
PROFILE = 'efficient_v1'
DEFAULTS = {
    'generation_defaults_profile': PROFILE,
    'required_video_scene_count': 0,
    'concentrated_scene_effects': False,
    'image_layer_scene_start': None,
    'image_layer_scene_end': None,
    'parallax_mode': 'selective',
    'image_layer_mode': 'hybrid',
    'direction_profile': 'auto',
    'reuse_check_policy': 'compatible_first_v3',
    'generate_publish_package': True,
}
DIRECTION = ('Keep the selected language, country, era and image style consistent throughout this work. '
             'Prefer a fixed camera. Never add slow, subtle or whole-scene zooms. '
             'Only when motivated, use a clearly visible medium-speed camera move over a short window with holds. '
             'Preserve camera movement already baked into uploaded footage. '
             'Select effects only for motivated actions, reveals or emotional turns; no mandatory effect range. '
             'Prepare basic still images before submission; prepare/review AE layers after submission. '
             'Check compatible background and character reuse in every still scene, without a reuse quota.')
