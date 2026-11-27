"""Shared audiovisual writing contract for manual and staged script workers."""
CONTRACT = 'wuxia_three_channel/v1'
DIRECTIVE = '''For WUXIA WEBTOON scripts apply wuxia_three_channel/v1:
VISUAL: concrete framing, visible movement/contact and motivated energy/debris cues in
visual_action; understandable without speech. One focal event per cut, not a compulsory
multi-shot list. Use fixed camera unless movement is motivated; never slow whole-scene zoom.
NARRATION: only unseen causality, history, stakes or meaningful inner context. Independently
compare EVERY narration sentence with its SAME cut's visual_action; remove visible-action
reporting and repeated information without replacing it with explanatory dialogue or padding.
DIALOGUE: short character-specific exchanges, threats, choices and emotional turns. Aim for
one brief sentence that fits two subtitle lines; actual wrapping depends on the final layout.
Do not force archaic speech on every character or move all explanations into narration.
RHYTHM: silent action, visual+narration and visual+dialogue as motivated; both speech types
are allowed when needed. 3-5 seconds is a planning reference, not a fixed duration or quota.
Store optional sfx as a list of nonspoken sound descriptions, separate from spoken_blocks.
Store optional screen_text as a list of screen-only strings; never voice it automatically.
Spoken_blocks contain audible narration/dialogue in playback order, named dialogue speakers.
Do not put SFX tags, camera commands, screen-only lettering or acting directions in TTS text.
Review these channel boundaries, individual voices, causal clarity and scene rhythm explicitly.
No actual sound generation, timed audio measurement or rendered-output verification is implied.'''
