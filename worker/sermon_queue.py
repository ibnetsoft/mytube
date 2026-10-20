"""Compatibility guard: sermon output follows the same user-web submission pipeline.

Approved script records and already-produced chapter files are retained. This
module no longer owns a second TTS/video queue alongside the submitted renderer.
"""
MESSAGE='대본 승인만으로 음성·영상 제작을 시작하지 않습니다. 유저웹에서 영상·화자·음성을 확인하고 제출하면 통합워커가 제작합니다.'

def enqueue(*args, **kwargs):
    raise ValueError(MESSAGE)

def process(*args, **kwargs):
    raise ValueError(MESSAGE)

def start_media_loop(*args, **kwargs):
    raise ValueError(MESSAGE)
