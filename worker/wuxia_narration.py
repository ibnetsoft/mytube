"""Separate planned visuals from speech; semantic review uses local Codex only."""
import copy
import hashlib
import json

from worker.generation_validation import validated_stage

PROFILE = 'wuxia_visual_narration/v1'
REVIEW_CHECKS = {'continuity','story_clarity','no_padding','narrator_conductor','narration_rhythm','character_agency'}
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

DIRECTIVE += '''\nConsider sparse popup close-up panels in visual_action for a motivated gaze,
mouth-corner reaction, or hand on a sword hilt. Keep the base shot and name the
detail, narrative reason and brief appearance moment. At most one popup per six
scenes and five per episode, with two intervening scenes and at least 20 seconds
between popup windows; zero is valid. Use 1.8-3.2 seconds total (default 2.2) and a 0.12-second
snap entrance followed by a readable still hold. Select a 0.24-second fade or
a 0.32-second left/down exit toward a nearby edge when motivated; never a slow whole-scene zoom. These are
planned candidates, not approved coordinates: later inspect actual source art,
protect all base faces and lettering, and prepare via worker.wuxia_popup using
docs/wuxia-webtoon-production-defaults.md. Do not put these instructions in speech.
For every visible hand, visual_action specifies the CHARACTER'S anatomical left
or right, palm/back visibility, wrist rotation and contacted/gripped object.
Never attach a right hand to a left arm or vice versa. Actual artwork review must
trace shoulder, elbow, forearm, wrist and thumb base for each hand independently;
screen-left/right or finger count alone cannot establish anatomical correctness.
Record source-SHA-bound anatomy review; repair swapped hands and review again
without mirroring the whole picture or hiding errors beneath popup panels.'''


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
    if not isinstance(checks, dict) or set(checks) != REVIEW_CHECKS:
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
            if d.get('adds') not in ('new_fact', 'time_transition', 'unseen_cause', 'essential_meaning', 'scene_bridge', 'contrast', 'information_release', 'stakes'):
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
    from worker.wuxia_narration_audit import diagnose
    rounds, removed = [], []
    for attempt in range(3):
        report = validated_stage(stage, f'02w_wuxia_visual_review_{attempt + 1}',
            {'sections': sections, 'title': context.get('topic'), 'contract': DIRECTIVE, 'narration_diagnostics': diagnose(sections)},
            DIRECTIVE + '''
Independently review every narration sentence alongside its SAME CUT planned visual_action and
neighboring cuts. Never infer actual image/audio inspection. Keep essential unseen information;
remove only redundant descriptions of visible action/emotion, not genuine new facts.
Do not rewrite dialogue or invent dialogue to explain actions. Review the entire episode for
causality, injuries, object custody, comprehension from visuals+speech and padding.
Return {mode:"planned_visuals_and_speech",checks:{continuity:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
story_clarity:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
no_padding:{passed:true,reason:"specific finding",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
narrator_conductor:{passed:true,reason:"how narration controls the neighboring scene flow and information release",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
narration_rhythm:{passed:true,reason:"assess repetitive report-like endings AND whether narration earns its airtime; suffix swapping is not a repair",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}},
character_agency:{passed:true,reason:"important choices, warnings, refusals and relationship turns use motivated character speech or justified silence, not exposition filler",evidence:{scene_order:1,channel:"visual_action|text",quote:"exact substring"}}},
narration_decisions:[{scene_order:1,block_id:"id",quote:"exact block text",decision:"keep",
adds:"new_fact|time_transition|unseen_cause|essential_meaning|scene_bridge|contrast|information_release|stakes",reason:"specific added information"},
{scene_order:1,block_id:"id",quote:"exact block text",decision:"remove_visible_repeat",
visual_evidence:"exact substring of SAME scene visual_action",reason:"why image already conveys it"}]}.
One decision for EVERY narration block. Zero narration blocks means narration_decisions:[].''',
            lambda raw: validate_review(raw, sections))
        rounds.append(report)
        deletions = {(d['scene_order'], d['block_id']) for d in report['narration_decisions']
                     if d['decision'] == 'remove_visible_repeat'}
        if not deletions:
            if not all(c['passed'] for c in report['checks'].values()):
                if attempt >= 2:
                    raise ValueError('Wuxia audiovisual review rejected continuity/clarity/padding; checkpoints preserved')
                revised = validated_stage(stage, f'02w_wuxia_repair_{attempt + 1}',
                    {**context, 'sections': sections, 'actual_review_feedback': report},
                    DIRECTIVE + '''
Repair the rejected draft from the independent audiovisual findings. Return {sections:[{scene_order,
visual_action,spoken_blocks,text}]} with the same ordered scene identifiers. Preserve the episode's
canonical events, essential information, character agency, injuries and object custody. Do not invent
new events, weapons or dialogue to fill duration. Repair the actual cited defects: compress redundant
reaction shots, repeated empty-space confirmation and mechanically identical cut patterns. Shorten
planned display durations when needed instead of padding to a target. Keep meaningful silent cuts.
Maintain distinct motivated viewpoints and full-screen cuts <=3 seconds with exact speech anchors.
Text must be exactly joined spoken_blocks. Do not claim actual artwork or audio was reviewed.''',
                    lambda raw: validate_draft(raw, budgets))
                sections = copy.deepcopy(revised['sections'])
                continue
            return sections, {'profile': PROFILE, 'verdict': 'pass', 'mode': report['mode'],
                'actual_artwork_reviewed': False, 'actual_audio_auditioned': False, 'review_checks': sorted(REVIEW_CHECKS), 'narration_diagnostics': diagnose(sections), 'rounds': rounds, 'removed': removed,
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

DIRECTIVE += """
When artwork clearly shows a clenched hand, omit redundant narration such as
'손을 꾹 쥐었습니다'. Preserve hand anatomy/action in visual_action and optionally
plan context-appropriate editable action typography (not TTS): a tilted, heavy ink accent,
restrained outline, brief settle entrance and readable 1.5-2.2s hold in safe space.
Use the existing cloud-shaped bubble_style:'thought' for solitary inner thoughts,
separating screen-only thoughts from audible speech; never lip-sync screen-only thought.
Optional stationary diagonal hatching can emphasize tension without any body or
camera movement. Blink only the restrained local lines at 180-400ms on/off intervals
for 0.8-2.4s, avoiding all faces, hands and lettering; not every cut. Prepare source-
reviewed patches using worker.wuxia_hatch and the production defaults. No invented
motion or redundant audible action reports just to explain visible artwork.
"""

DIRECTIVE += """
Typography examples are NEVER defaults to copy. Inspect the actual depicted event,
contact versus scraping versus gripping, both materials, intensity and duration
before selecting an onomatopoeia or mimetic word. '꾸욱' is only an example for
sustained squeezing/pressing, not a stone blade striking the floor. For a brief
stone-on-stone contact, '탁!' may fit; sustained scraping may call for '카각',
a heavy impact for '쿵'. These are examples, not fixed mappings or automatic substitutions.
Record event, materials and word_reason with the reviewed state ID/SHA and timing
anchor. Put impact typography at actual contact and sustained mimetics only during
their matching state. Reject mismatched event/material/timing; omit an uncertain
accent rather than blindly copy an example or narrate the visible action again.
"""

DIRECTIVE += """
Select impact debris only for motivated collisions, never every scene or contact.
Bind the effect to the actual reviewed source contact point and impact time.
After contact, fragments originate THERE and travel OUTWARD; never send an external
light beam inward to represent a blade striking the ground. Distinguish actual
weapon travel from post-impact fragment emission; invent no weapon motion for a still.
Choose stone chips/dust, wood splinters, soil dust or justified metal sparks from
actual materials. Scale count, size, spread and distance to impact strength, with
varied outward velocities/rotation and natural falling/fading. A single yellow line
or crossed flare does not replace debris. No arbitrary explosions or magical energy.
Preview counts/colors are examples, not defaults. Record contact position, source
ID/SHA, timing anchor, materials, strength rationale, emission directions/range and
aftermath duration. Review early/middle/late composite frames for outward travel,
correct occlusion and protected faces/hands/text, respecting supported effect timing.
"""

DIRECTIVE += """
PRIORITY: NARRATIVE PROGRESSION, not merely fewer spoken descriptions.
Use docs/WUXIA_SERIES_PLAN_03_50.md revised 1-50 v2 for its named series; preserve
finalized episodes and carry their actual ending into new episodes.
Before drafting, state the episode goal, obstacle, character choice, realized
consequence and changed end state (episode_turn). Record only applicable new
information, relationship or martial changes, never force all categories per episode.
Resolve a consequential event WITHIN the episode, not only a promise in its ending.
Each sequence must change information, goal, relationship, advantage, location or
agency, or be necessary setup for a specific consequence. If removal leaves later
causality AND emotion unchanged, merge or cut it. Avoid injury checks, breathing,
vigilance and repeated resolves as substitutes for events, even in silent visuals.
Preserve real injury limits but compress recovery/training through elapsed time;
never pad time with reopening the same wound or heal instantly. Flashbacks must
change a present decision/action/result. Supporting characters pursue their own
goals and affect outcomes, not just explain the protagonist. Reward growth through
newly successful combat/rescue/leadership actions; failures change the next attempt,
not reset to the same question. Discovery must open a concrete next action. Maintain
causal transitions, prop custody and earned abilities; no random encounters, new
technique names or severe injuries solely to fill a checklist. Duration is a target,
not a quota to fill with visible-action narration, repeated monologue or still holds.
"""

DIRECTIVE += """
For motivated action accents, plan the CAUSE before the impact result:
visible swing/downstroke/throw or incoming object -> actual contact -> optional
flash/outward material-appropriate debris/shake -> aftermath. Do not substitute
an impact effect on an already planted still for the missing motion. Misses and
non-contact actions do not automatically trigger collision effects. Choose only
needed accents, never apply the entire effect bundle to every scene or attack.
Store movement start, contact anchor and effect windows on the same editor clock.
Use prepared pose states when the arm/body changes; simple extracted-object layer
motion requires a restored background with no original object left behind. Preserve
grip, anatomy, prop identity and occlusion. The preview's 0.16s descent is an example,
not a universal speed. Flash/debris cannot precede contact; outgoing debris begins
at contact. Optional shake follows impact using the established timing/delay, 10Hz,
axis, amplitude and protection rules. Inspect pre-motion, pre-contact, contact and
post-impact frames for duplicates, timing and direction. Camera shake never replaces
object motion. Keep all action directions in visual_action, not audible narration.
The approved local preview is not proof of an implemented web/AE production path.
"""


# User correction 2026-11-08: applies to newly generated Wuxia directions only.
DIRECTIVE += '''\nFULL-SCREEN SHOT RHYTHM: A narrative/voice scene is not a single screen cut.
Plan multiple story-motivated full-screen shots inside a scene when necessary.
No new Wuxia full-screen shot may dwell longer than 3.0 seconds. Start with
0.3-1.2s action connectors and 1-2.5s normal/reaction shots; vary the rhythm,
never make all shots exactly 3s or split on an arbitrary metronome. Preserve
continuous finalized dialogue/narration; cut the picture to a motivated listener
reaction, hand/prop insert, reverse/rear view or environment instead of speeding
up, truncating or padding speech. Keep text readable on its actual audio clock.
A fixed camera means fixed WITHIN a shot, not the same angle across every shot.
Avoid repeating medium-distance eye-level group tableaux showing 3-4 people.
Choose distance, viewpoint, visible cast and subject size from the depicted event:
establishing wide, single/two-person shot, face/eyes close-up, hands/weapon/contact
detail, people-free environment or prop, rear, over-shoulder reverse, low angle,
high angle/overhead or POV. Do not rotate through this list as a quota. Preserve
spatial axis, gaze/action direction, identity, injuries and prop custody.
A new viewpoint requires matching new artwork; rotating/zooming an old flat image
is not a new camera angle. Reuse a crop only for a readable story-relevant detail
actually present at sufficient resolution. Tiny motion and popup overlays do not
replace full-screen shot changes. Use short impact-only shake AFTER actual contact
in the contact-detail shot, not a whole-scene shake across faces/backgrounds.
In visual_action record each cut_id, distance, angle, subject/visible cast, purpose,
planned dwell <=3s, required artwork or justified crop, and event/audio timing anchor.
Never send this shot list into spoken_blocks or TTS. After final audio, add and
prepare needed real reaction/detail/environment cuts instead of extending a still.
This is a planned shot contract, not actual artwork, preview or AE approval.
Preserve finalized episodes and existing running-job settings.'''


# New Wuxia generation only: semantic directing, not a blanket change to other genres.
DIRECTIVE += '''\nNARRATOR AS CONDUCTOR, NOT A SHOT-BY-SHOT REPORTER:
Compose and review the entire event sequence, including previous and next cuts.
Narration earns airtime by orienting a change in time/place, connecting cause and
consequence, creating grounded contrast/stakes or controlling information release.
Do not read out visible gestures, blows, movement, wounds, facial expressions and
prop positions. Leave action/impact beats silent when the picture and sound carry them.
Avoid chains of Korean report-like past endings such as '~했습니다/~었습니다/~였습니다'
and equivalent monotonous reporting in the target language. Fix the information
and dramatic function first; swapping endings, sprinkling rhetorical questions,
adding '그때/하지만/아직 몰랐다' everywhere, or randomly switching politeness is not a repair.
Keep one coherent storytelling voice and vary phrase length, pauses and emphasis.
Let a character speak when a warning, demand, refusal, decision, discovery or
relationship turn actually changes what happens. Their speech must be in character,
not narration disguised as explanatory dialogue and not a mandatory dialogue quota.
Do not remove their decisive utterance and let the narrator report it instead.
Do not reveal a later discovery before its intended character/action reveal,
invent motives or stakes, or add a new plot fact solely to justify narration.
Use narration_diagnostics as a review signal, never as an automatic suffix-based
rewrite. Review narrator_conductor, narration_rhythm and character_agency explicitly
with exact-source evidence as well as continuity, clarity and no padding.
These are script-stage text/planned-visual checks. Actual artwork comparison and
final audio audition are separate; do not label them complete from this report.'''


from worker.wuxia_script_style import DIRECTIVE as THREE_CHANNEL_DIRECTIVE
DIRECTIVE += "\n" + THREE_CHANNEL_DIRECTIVE
