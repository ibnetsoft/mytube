"""Local, visually reviewed mouth patches prepared when script images publish."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'output' / 'codex-local-console' / 'prepared-mouths'


def cache_key(image, speaker):
    from ae_mouth import digest
    from mouth_geometry import fingerprint
    request = {'version': 2, 'geometry':fingerprint(speaker),'source': digest(image), 'speaker': speaker['speaker'],
               'mouth_box': speaker['mouth_box'], 'coverage_version': speaker.get('coverage_version')}
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


def reuse_prepared(image, speaker):
    from ae_mouth import digest, POSES
    from mouth_geometry import animatable, fingerprint
    try:
        if not animatable(speaker,digest(image)):return False
    except ValueError:return False
    directory = ROOT / cache_key(image, speaker)
    try:
        alias = directory / 'artifact-reference.json'
        if alias.exists():
            reference = json.loads(alias.read_text(encoding='utf8'))
            key = reference['key']
            if len(key) != 64 or any(c not in '0123456789abcdef' for c in key): return False
            if reference.get('speaker') != speaker['speaker'] or reference.get('source') != digest(image): return False
            directory = ROOT / key
        receipt_path = directory / 'reviewed.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['key'] != directory.name or receipt['source'] != digest(image) or receipt.get('geometry') != fingerprint(speaker):
            return False
        for pose in POSES:
            if digest(directory / f'{pose}.png') != receipt['hashes'][pose]:
                return False
        speaker['mouth_box'] = receipt['mouth_box']
        speaker['coverage_version'] = 2
        speaker['layers'] = {pose: str((directory / f'{pose}.png').resolve()) for pose in POSES}
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def is_excluded(image, speaker):
    """Honor source/geometry-specific user exclusions on this render host."""
    key = cache_key(image, speaker)
    try:
        receipt = json.loads((ROOT / key / 'excluded.json').read_text(encoding='utf-8'))
        return receipt.get('key') == key and receipt.get('reason') == 'user_excluded'
    except (OSError, ValueError, TypeError):
        return False


def prepare_scene(image, geometry, runner=None, generator=None, *, technical=False):
    from ae_mouth import digest, mouth_layers, review_layers, POSES
    from codex_content_runner import CodexStagedContentRunner
    from manga_layer_generation import NativeCodexLayerGenerator
    if geometry.get('state') != 'ready' or geometry.get('source_sha256') != digest(image):
        return {'state': 'not_required'}
    from mouth_geometry import animatable, fingerprint
    visible = [s for s in geometry['speakers'] if animatable(s,digest(image))]
    prepared, entries = [], []
    for original in visible:
        if is_excluded(image, original):
            continue
        speaker = copy.deepcopy(original)
        key = cache_key(image, speaker)
        directory = ROOT / key
        if not reuse_prepared(image, speaker):
            # CLI attachments must stay in output/codex-local-console. Inputs
            # from a topic preparation folder may be outside that boundary.
            directory.mkdir(parents=True, exist_ok=True)
            reference = directory / 'source-reference.png'
            pixels = image.read_bytes()
            if hashlib.sha256(pixels).hexdigest() != geometry['source_sha256']:
                raise ValueError('Source changed before mouth preparation')
            reference.write_bytes(pixels)
            speaker['layers'] = mouth_layers(generator or NativeCodexLayerGenerator(), image, speaker, directory)
            review_layers(runner or CodexStagedContentRunner(), 'prepared-mouth-' + key, reference, [speaker], directory)
            receipt = {'key': key, 'geometry':fingerprint(speaker),'source': digest(image), 'mouth_box': speaker['mouth_box'],
                       'hashes': {p: digest(Path(speaker['layers'][p])) for p in POSES}}
            temporary = directory / 'reviewed.tmp'
            temporary.write_text(json.dumps(receipt), encoding='utf-8')
            temporary.replace(directory / 'reviewed.json')
        prepared.append(key)
        effective = {**speaker, 'coverage_version': 2}
        effective_key = cache_key(image, effective)
        if effective_key != key:
            alias_dir = ROOT / effective_key
            alias_dir.mkdir(parents=True, exist_ok=True)
            (alias_dir / 'artifact-reference.json').write_text(json.dumps({
                'key': key, 'speaker': speaker['speaker'], 'source': digest(image)}), encoding='utf8')
        entries.append({'speaker': speaker['speaker'], 'key': key,
                        'mouth_box': speaker['mouth_box'], 'coverage_version': speaker.get('coverage_version')})
    return {'state': 'ready' if prepared else 'not_required', 'keys': prepared, 'entries': entries}
