"""Silent video can still show a character speaking visually."""

import re

VIDEO_AUDIO_GUARDS = (
    "no narration", "no subtitles", "no captions", "no music", "no sound effects", "no audio",
)

VISIBLE_SPEECH_DIRECTION = (
    "For scenes 1-18, inspect the final scene_text and scene_cast for actual character dialogue. "
    "When dialogue is present and its speaker is visible, identify that speaker by name and visible "
    "appearance or screen position in the English video_prompt. Describe natural repeated lip opening "
    "and closing with subtle jaw movement as the character silently speaks, short closed-mouth pauses, "
    "and a closed-mouth end pose. Preserve the scene's emotion and original action. Only the current "
    "speaker moves their mouth; listening characters keep their mouths closed. For multiple speakers, "
    "describe their speaking turns in script order with no simultaneous talking. Keep the speaking "
    "mouth visible where the original composition allows; do not add an absent speaker or alter the "
    "scene to show offscreen speech. Narration-only scenes, inner thoughts, and non-speaking reaction "
    "shots must keep characters' mouths closed. Do not mistake a quoted letter, title, or remembered "
    "phrase for a visible speaking turn. These are visual speaking motions, not guaranteed audio "
    "synchronization: do not claim exact lip sync or invent timestamps. The video remains silent; "
    "the finalized TTS is added separately. Use 'no audible dialogue' instead of 'no dialogue', "
    "and never prohibit lip movement on a visible dialogue shot."
)


def has_dialogue_audio_guard(text: str) -> bool:
    # Existing approved packages remain valid; new prompts use the unambiguous guard.
    return bool(re.search(r"\bno (?:audible )?dialogue\b", text, re.I))


def silent_video_prompt(text: str) -> str:
    return re.sub(r"\bno dialogue\b", "no audible dialogue", text, flags=re.I)
