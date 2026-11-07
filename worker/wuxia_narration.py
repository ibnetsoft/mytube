"""Separate planned visuals from speech; semantic review uses local Codex only."""
import copy
import hashlib
import json

from worker.generation_validation import validated_stage

PROFILE = 'wuxia_visual_narration/v1'
DIRECTIVE = '''WUXIA WEBTOON OVERRIDE: Images and dialogue carry the story together.
Store image-making action/pose/prop/continuity instructions ONLY in visual_action.
spoken_blocks contains ONLY audible narration or character dialogue; text is their concatenation,
never visual_action or speaker labels. Give every block a stable unique id and kind.
Use one complete sentence per narration block. A dialogue block also has a named speaker.
Do not narrate actions or emotions already clearly shown by the planned image.
Keep narration only for new facts, time transitions, unseen causes or essential meaning
that the image/dialogue cannot convey. Do not replace deleted action reports with lyrical
inner monologue, explanatory dialogue, synonyms or padding. A scene may have no speech:
spoken_blocks:[] and text:"". Preserve its visual action and planned duration for visual/SFX holds.
There is no minimum speech count or character quota per cut. Preserve injuries, object custody,
causality, cast and the ending across spoken AND visual channels. Never require audio-only
comprehension or prefer narration over dialogue. Do not claim actual artwork/audio was reviewed
when only a visual plan is supplied.'''


def applies(payload):
    values = [payload.get(k) for k in ('image_style', 'script_style', 'production_mode',
                                     'category', 'category_name', 'category_id')]
    values.append((payload.get('content_setting') or {}).get('image_style'))
    return any(str(v or '').replace(' ', '').lower() in
               ('18', 'wuxia_webtoon', '무협웹툰') for v in values)


def spoken_text(section):
    return '\n'.join(b['text'] for b in section['spoken_blocks'])


def validate_draft(raw, budgets):
    sections = raw.get('sections')
    if not isinstance(sections, list) or len(sections) != len(budgets):
        raise ValueError('Wuxia sections must preserve every planned scene')
    for n, (s, budget) in enumerate(zip(sections, budgets), 1):
        if not isinstance(s, dict) or type(s.get('scene_order')) is not int or s['scene_order'] != n:
            raise ValueError('Wuxia scene order changed')
        if not isinstance(s.get('visual_action'), str) or not s['visual_action'].strip():
            raise ValueError('Every cut needs separate image-making action instructions')
        if not isinstance(s.get('spoken_blocks'), list):
            raise ValueError('Missing spoken_blocks; use [] for silent visual cuts')
        ids = set()
        for b in s['spoken_blocks']:
            if (not isinstance(b, dict) or not isinstance(b.get('id'), str) or not b['id'].strip()
                    or b['id'] in ids or b.get('kind') not in ('narration', 'dialogue')
                    or not isinstance(b.get('text'), str) or not b['text'].strip() or b['text'] != b['text'].strip()):
                raise ValueError('Invalid or duplicate spoken block')
            ids.add(b['id'])
            if b['kind'] == 'dialogue' and (not isinstance(b.get('speaker'), str) or not b['speaker'].strip()):
                raise ValueError('Dialogue needs its actual named speaker')
        text = spoken_text(s)
        if s.get('text') != text:
            raise ValueError('text must contain exactly spoken_blocks; no visual instructions or speaker labels')
        if len(text) > max(budget['max_chars'] * 2, budget['max_chars'] + 30):
            raise ValueError('Spoken text exceeds scene capacity; do not pad silent cuts')
    if not any(s['spoken_blocks'] for s in sections):
        raise ValueError('Whole episode has no speech; do not silently switch to a nonverbal production')


def validate_review(raw, sections):
    if raw.get('mode') != 'planned_visuals_and_speech':
        raise ValueError('Review must distinguish planned visuals from actual artwork')
    checks = raw.get('checks')
    if not isinstance(checks, dict) or set(checks) != {'continuity', 'story_clarity', 'no_padding'}:
        raise ValueError('Missing whole-episode audiovisual checks')
    for check in checks.values():
        if (not isinstance(check, dict) or type(check.get('passed')) is not bool
                or not isinstance(check.get('reason'), str) or not check['reason'].strip()):
            raise ValueError('Audiovisual checks need explicit findings')
        evidence = check.get('evidence') or {}
        n = evidence.get('scene_order')
        channel, quote = evidence.get('channel'), evidence.get('quote')
        if type(n) is not int or not 1 <= n <= len(sections) or channel not in ('visual_action', 'text'):
            raise ValueError('Audiovisual findings need same-source evidence')
        if not isinstance(quote, str) or not quote.strip() or quote not in sections[n-1][channel]:
            raise ValueError('Audiovisual findings contain fabricated evidence')
    expected = {(s['scene_order'], b['id']): (s, b) for s in sections
                for b in s['spoken_blocks'] if b['kind'] == 'narration'}
    decisions = raw.get('narration_decisions')
    if not isinstance(decisions, list) or len(decisions) != len(expected):
        raise ValueError('Review every narration block, including retained sentences')
    seen = set()
    for d in decisions:
        if not isinstance(d, dict):
            raise ValueError('Invalid narration decision')
        if type(d.get('scene_order')) is not int or not isinstance(d.get('block_id'), str):
            raise ValueError('Narration decisions require an integer scene and string block id')
        key = (d.get('scene_order'), d.get('block_id'))
        if key not in expected or key in seen:
            raise ValueError('Unknown, duplicate, or dialogue deletion request')
        seen.add(key)
        s, b = expected[key]
        if d.get('quote') != b['text'] or not str(d.get('reason') or '').strip():
            raise ValueError('Narration review must quote the exact block')
        if d.get('decision') == 'remove_visible_repeat':
            evidence = d.get('visual_evidence')
            if not isinstance(evidence, str) or not evidence.strip() or evidence not in s['visual_action']:
                raise ValueError('Removal requires exact evidence from the same cut visual_action')
        elif d.get('decision') == 'keep':
            if d.get('adds') not in ('new_fact', 'time_transition', 'unseen_cause', 'essential_meaning'):
                raise ValueError('Retained narration must add information beyond the image')
        else:
            raise ValueError('Unknown narration review decision')


def produce_sections(stage, context, scenes, budgets):
    """AI judges semantic redundancy; code only applies grounded whole-block removals."""
    context = {**context, 'scenes': copy.deepcopy(scenes), 'scene_budgets': budgets,
               'wuxia_narration_contract': DIRECTIVE}
    draft = validated_stage(stage, '02w_wuxia_script', context, DIRECTIVE + '''
Write the complete episode. Return {sections:[{scene_order:1,visual_action:"detailed image-only instructions",
spoken_blocks:[{id:"s1n1",kind:"narration",text:"one audible sentence"},
{id:"s1d1",kind:"dialogue",speaker:"name",text:"quoted audible words"}],text:"exact joined block texts"}]}.
Use newlines to join block texts. Silent scenes are allowed; never fill min_chars.''',
                            lambda raw: validate_draft(raw, budgets))
    sections = copy.deepcopy(draft['sections'])
    rounds, removed = [], []
    for attempt in range(3):
        report = validated_stage(stage, f'02w_wuxia_visual_review_{attempt + 1}',
            {'sections': sections, 'title': context.get('topic'), 'contract': DIRECTIVE},
            DIRECTIVE + '''
Independently review every narration sentence alongside its SAME CUT planned visual_action and
neighboring cuts. Never infer actual image/audio inspection. Keep essential unseen information;
remove only redundant descriptions of visible action/emotion, not genuine new facts.
Do not rewrite dialogue or invent dialogue to explain actions. Review the entire episode for
causality, injuries, object custody, comprehension from visuals+speech and padding.
Return {mode:"planned_visuals_and_speech",checks:{continuity:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
story_clarity:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
no_padding:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}}},
narration_decisions:[{scene_order:1,block_id:"id",quote:"exact block text",decision:"keep",
adds:"new_fact|time_transition|unseen_cause|essential_meaning",reason:"specific added information"},
{scene_order:1,block_id:"id",quote:"exact block text",decision:"remove_visible_repeat",
visual_evidence:"exact substring of SAME scene visual_action",reason:"why image already conveys it"}]}.
One decision for EVERY narration block. Zero narration blocks means narration_decisions:[].''',
            lambda raw: validate_review(raw, sections))
        rounds.append(report)
        deletions = {(d['scene_order'], d['block_id']) for d in report['narration_decisions']
                     if d['decision'] == 'remove_visible_repeat'}
        if not deletions:
            if not all(c['passed'] for c in report['checks'].values()):
                raise ValueError('Wuxia audiovisual review rejected continuity/clarity/padding; checkpoints preserved')
            return sections, {'profile': PROFILE, 'verdict': 'pass', 'mode': report['mode'],
                'actual_artwork_reviewed': False, 'rounds': rounds, 'removed': removed,
                'script_sha256': hashlib.sha256(json.dumps(sections, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        for s in sections:
            kept = []
            for b in s['spoken_blocks']:
                if (s['scene_order'], b['id']) in deletions:
                    # Preserve the staging information for images, never in TTS text.
                    removed.append({'scene_order': s['scene_order'], **copy.deepcopy(b)})
                    s['visual_action'] += '\n' + b['text']
                else:
                    kept.append(b)
            s['spoken_blocks'] = kept
            s['text'] = spoken_text(s)
        validate_draft({'sections': sections}, budgets)
    raise ValueError('Wuxia narration review did not converge after three rounds; checkpoints preserved')
