"""Style-aware model sheets derived from an approved character, never new identities."""
import hashlib
import json

VERSION = 'style-model-sheet-v1'


def sheet_profile(payload):
    style = str(payload.get('image_style') or (payload.get('content_setting') or {}).get('image_style') or 'realistic').lower()
    selection = str(payload.get('image_style_selection') or '').lower()
    detailed = any(token in style + ' ' + selection for token in ('실사', '디테일', '고밀도', 'realistic', 'photoreal', 'detailed', 'high detail', 'cinematic'))
    animated = any(token in style for token in ('ghibli', '지브리', 'anime', 'animation', '애니', 'cel', 'cartoon', 'illustration', '일러스트', 'watercolor', '수채', '웹툰', '2d', 'ukiyo', 'sumi'))
    return 'turnaround' if animated and not detailed else 'detailed_board'


def sheet_instruction(profile):
    common = ('Use the supplied approved character as the mandatory identity reference. Preserve the exact face, '
              'age, hairstyle, body proportions, species, markings, costume and palette in every view. '
              'For animals or mythical creatures use their correct anatomy and species-appropriate neutral stance; '
              'never add human limbs, clothing or transformations absent from the story. '
              'Do not import names, people or costumes from layout examples. No captions, labels, letters, numbers, '
              'biography panels, watermark or logo. Keep all figures fully inside the canvas with clear spacing. ')
    if profile == 'turnaround':
        return common + ('Create ONE clean 16:9 animation character turnaround sheet on a plain light neutral background. '
            'Top row: four full-body views, front, true left profile, true right profile and back, at the same scale. '
            'Bottom row: three large head close-ups, front, left three-quarter and right three-quarter. '
            'Use the selected hand-drawn/illustrated style, clean lines and restrained shading. '
            'Keep both side views genuinely different orientations; preserve asymmetric markings on their correct sides.')
    return common + ('Create ONE richly detailed 2:3 character design board, keeping the selected photorealistic or '
        'detailed illustration style rather than converting it to animation. Use an orderly visual-only layout: '
        'large identity portrait; six facial expressions (neutral, restrained smile, concern, sadness, anger, surprise); '
        'front/profile/back full-body views; several story-supported poses; close-ups of clothing construction, '
        'materials, hair/fur/scales and signature accessories or props; and small palette swatches. '
        'Use only outfits, props and forms supported by the approved character and story. If no variants are defined, '
        'show details of the base outfit instead of inventing new ones. Where explicitly established, include a small '
        'form/state progression, signature ability study and relative scale cue; otherwise omit them instead of inventing '
        'powers, biography or personal statistics. Preserve physical surface detail and consistent lighting.')


def sheet_fingerprint(character, payload, portrait_sha):
    profile = sheet_profile(payload)
    return hashlib.sha256(json.dumps([VERSION, profile, portrait_sha, payload.get('image_style'),
        payload.get('image_style_selection'), character.get('visual_dna_en'), character.get('wardrobe_en'),
        sheet_instruction(profile)], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def has_model_sheet(character, payload):
    if character.get('character_sheet_status') != 'ready' or character.get('character_sheet_version') != VERSION:
        return False
    if character.get('character_sheet_profile') != sheet_profile(payload) or not character.get('image_sha256'):
        return False
    expected = sheet_fingerprint(character, payload, character['image_sha256'])
    return any(sheet.get('type') == 'model_sheet' and sheet.get('status') == 'ready'
               and sheet.get('image_url') and sheet.get('fingerprint') == expected
               for sheet in character.get('character_sheet_assets') or [])


def ensure_model_sheet(character, payload, portrait, generator, store, topic_id, fingerprint):
    # Minimal stores used by older integrations may only support portraits.
    if not hasattr(store, 'publish_sheet'):
        return character
    portrait_sha = hashlib.sha256(portrait.read_bytes()).hexdigest()
    character['image_sha256'] = portrait_sha
    if has_model_sheet(character, payload):
        return character
    profile = sheet_profile(payload)
    version = sheet_fingerprint(character, payload, portrait_sha)
    prompt = (character['image_prompt'] + '\nMODEL SHEET LAYOUT OVERRIDE: ' + sheet_instruction(profile)
              + '\nApproved source SHA-256: ' + portrait_sha + '\nSheet contract: ' + version)
    path = generator.generate(prompt, reference_path=portrait)
    sheet = store.publish_sheet(topic_id, character, 'model_sheet', path)
    sheet.update(profile=profile, fingerprint=version, status='ready')
    # Retain older expression/mouth/wardrobe sheets and older completed boards.
    previous = list(character.get('character_sheet_assets') or [])
    character.update(character_sheet_assets=[sheet, *previous], character_sheet_profile=profile,
                     character_sheet_version=VERSION, character_sheet_status='ready')
    store.save_design(topic_id, character, fingerprint, payload)
    return character
