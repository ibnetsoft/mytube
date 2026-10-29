"""Sample every recorded caption, including its actual display boundaries."""
import math


def caption_samples(subtitles, scene, fps, total):
    samples=[]
    for index,row in enumerate(subtitles):
        if int(row.get('scene_number') or 0)!=scene['number']:
            continue
        start,end=float(row['start']),float(row['end'])
        if not all(math.isfinite(t) for t in (start,end)) or end<=start:
            raise ValueError('Invalid recorded caption interval')
        # Keep inside samples away from ASS centisecond and video-frame rounding.
        guard=min(2/float(fps),(end-start)/4)
        times=(('before_start',start-guard),('after_start',start+guard),
               ('middle',(start+end)/2),('before_end',end-guard),('after_end',end+guard))
        for phase,time in times:
            if 0<=time<total-1/float(fps):
                # Seek to an actual presentation timestamp. FFmpeg may otherwise return
                # success with no image when the seek lands after the last frame.
                frame_index=min(math.floor(time*float(fps)+1e-8),max(0,math.floor(total*float(fps)+1e-8)-1))
                frame_time=frame_index/float(fps)
                samples.append({'subtitle_index':index,'phase':phase,'time':frame_time,'requested_time':time,
                                'start':start,'end':end})
    return samples
