"""Cycle explicit page-turn recordings without changing narration timing."""
from moviepy import AudioFileClip, afx


def recorded_page_turns(paths, pages, turn_duration, volume=.55):
    tracks=[];resources=[]
    try:
        for path in paths:
            resources.append(AudioFileClip(str(path)))
        if not resources:
            return tracks,resources
        for index,page in enumerate(pages[:-1]):
            source=resources[index % len(resources)]
            # Keep the original speed; prevent a long recording from covering dialogue.
            length=min(source.duration,turn_duration)
            track=source.subclipped(0,length).with_effects([
                afx.AudioFadeIn(min(.01,length/4)),afx.AudioFadeOut(min(.04,length/4))
            ]).with_volume_scaled(volume).with_start(page['end'])
            tracks.append(track)
        return tracks,resources
    except Exception:
        for resource in resources:resource.close()
        raise
