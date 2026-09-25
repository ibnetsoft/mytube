"""Explicitly reviewed new everyday-family depiction, keeping ages and history."""
import sys
from flashback_3292 import DEST, STATE, recovery, read, write, capture, event

PROMPT='''Use case: historical-scene. One photorealistic16:9 film still, late Joseon rural Korea.
Reference image1: Geumrye, the38-year-old mother, black low bun, ochre-brown cotton jeogori and indigo skirt. Reference image2: her12-year-old daughter Sunduk, black braid, muted-blue cotton hanbok. Preserve each reference identity and their actual ages.
A quiet everyday moment in their modest family room, softly lit by a paper-lattice window. Sunduk sits comfortably near the window, hands resting loosely in her lap, looking outside with a neutral thoughtful expression. Geumrye sits a short distance away, also resting her hands in her lap, looking gently toward her daughter. Both are at ease, fully dressed in ordinary period clothing. They are not touching. Use the space between their seats and their different directions of gaze to compose the scene. Eye-level medium-wide view shows both people naturally, with realistic hands, cotton fabric and wood textures. No text, captions, watermark, collage or modern objects.'''

def prepare():
    backup=DEST/'scene24-alternative-before.json'
    assert not backup.exists(),'Do not repeat or reset this alternative'
    before=capture()
    assert [s['scene_number'] for s in before['project']['project_payload']['structure']['scenes'] if not s.get('image_url')]==[24]
    write(backup,before)
    review={'action':'review','job_id':'scene24','decision':'alternative',
      'review':{'reviewer':'Codex','reason':'Materially different neutral everyday composition; daughter looks out window with relaxed hands rather than covering ears during distress.',
        'source_fidelity':'Same mother and daughter, same room and historical period. Emotional distance conveyed by separate gaze; original narration unchanged. This is an indirect visual interpretation, not the literal ear-covering action.',
        'character_age_style_preserved':'Geumrye38 and Sunduk12; approved age-specific portraits; realistic Joseon style.',
        'safety_assessment':'allowed_alternative','user_approval':'2026-09-16 user explicitly requests changing child depiction and regenerating24 after reporting child-safety warning.'},
      'proposals':[{'scene_numbers':[24],'prompt':PROMPT}]}
    write(DEST/'scene24-alternative-review.json',review)
    event(review);state=event({'action':'start','job_id':'scene24-alt-1'})
    j=recovery.get_job(state,'scene24-alt-1')
    print(__import__('json').dumps({k:j[k] for k in ('id','prompt','references')},ensure_ascii=False))

if __name__=='__main__':prepare()
