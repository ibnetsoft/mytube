# Selective manga dialogue lip sync

Lip sync is opt-in for a deliberately selected `dialogue_closeup` AE highlight.
Ordinary scenes, narration, unseen speakers, and the other manga templates keep
their existing render path. Set `scene.ae_template = "dialogue_closeup"` to select
the close-up; the planner never infers it from the mere presence of dialogue.
The older project-wide `use_lipsync` setting does not select these AE scenes;
use the per-scene `ae_lip_sync` plan only when the final voice is available.
The highlight selection cap remains in effect, but an explicitly prepared
lip-sync scene is reserved before other highlights (at most eight per story).

Prepare the lip plan **after final TTS is fixed** and before generating or
approving the PSD. The `audio_path` must be the final dialogue audio available
to the local AE worker. Word times are seconds relative to the start of this
AE clip, with one verified `speaker_key` on every word. If the word alignment is
in project-global time, subtract the clip's actual timeline start first. Do
not animate narration, off-screen voices, or guessed speakers. For example:

```python
from pathlib import Path
from worker.manga_lip_sync import prepare_lip_sync

scene["ae_template"] = "dialogue_closeup"
scene["ae_lip_sync"] = prepare_lip_sync(
    audio_path=Path("output/final-approved-dialogue.wav"),
    speaker_key="hero",
    duration=4,
    mouth_box=[0.43, 0.30, 0.57, 0.38],
    words=[
        {"text": "당장", "start_seconds": 0.8, "end_seconds": 1.2, "speaker_key": "hero"},
        {"text": "부탁드립니다", "start_seconds": 1.3, "end_seconds": 2.1, "speaker_key": "hero"},
    ],
)
```

The approved character key in `ae_effect_plan.character_role_keys.character`
must equal `speaker_key`. The planner carries `ae_lip_sync` into the selected
AE plan. A mismatched speaker, missing/changed audio file, overlapping or
out-of-clip word times, altered cues, or missing mouth art stops generation or
render preflight. Cues are stepped at 24 fps through `closed`, `half`, and
`open`; this produces an intentionally stylized rhythm, not phoneme-accurate
Korean visemes. Pauses remain closed. The audio hash protects against reusing
cues after a voice retake. Rebuild the plan and PSD review on a new revision
when TTS or artwork changes.

The PSD needs full-canvas, transparent `mouth_closed`, `mouth_half`, and
`mouth_open` layers aligned to the same `mouth_box` over the independently
authored `character` layer. Each mouth asset is generated with the final
character layer as its visual reference; a provided artist PNG may be used
instead. The PNG validator rejects patches outside the box or poses whose
centers jump. The approved PSD receipt binds hashes of all inputs. The
reviewer must inspect each individual pose for complete coverage of the baked
mouth, skin/ink continuity, teeth and jaw consistency, transparency seams,
and identical placement during the camera push. A single flattened screenshot
is insufficient as a PSD mouth package until those patches are authored.

AE uses hold interpolation to switch one mouth layer at a time. Plan QA checks
speaker/audio/word/cue consistency and the required PSD roles. Render QA
samples a closed and spoken frame in the mouth region and fails when it sees
no change. This pixel check cannot prove timing or visual quality. The scene
still enters `review_pending`; the reviewer listens to the **final** dialogue
while checking the first word, pauses, last word, seams, and facial identity.
Premiere receives the clip only after visual approval.

Local verification: `python experiments/manga_ae_smoke.py --template
dialogue_closeup --force` rendered a four-second 1920×1080 AE MP4, then
created `scene-with-audio.mp4` using a synthetic timing tone for preview.
Both plan and render QA passed, and inspection of
frames at 0.4, 1.1, and 1.7 seconds showed closed/open/closed mouth poses.
The synthetic smoke proves AE compositing and cue switching; it does not prove
the appearance or speech sync of a production character. The database must
also have `20260927001946_enable_dialogue_closeup_review.sql` applied before
this new template can enter the existing approval path.
