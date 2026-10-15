"""Measure source playback against the actual encoded tail output."""
import subprocess
import numpy as np

def compare_video_playback(ffmpeg, source, output, source_seconds):
    def frames(path):
        result = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-t', str(max(0, source_seconds - .15)), '-vf', 'fps=24,scale=320:180', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True)
        return np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1,180,320,3)
    a,b = frames(source),frames(output)
    n=min(len(a),len(b))
    if n < 2: raise RuntimeError('Playback comparison has insufficient decoded frames')
    # Codec/interpolation differences are tolerated; every timestamp is compared.
    diff=np.abs(a[:n].astype(np.float32)-b[:n].astype(np.float32)).mean(axis=(1,2,3))
    return {'comparison_fps':24,'compared_frames':n,'mean_absolute_rgb_error':round(float(diff.mean()),3),'max_frame_mean_error':round(float(diff.max()),3),'same_timestamp_source_playback_passed':bool(diff.max()<12),'output_frame_tolerance_seconds':1/24,'audio_scope':'Visual tail clip only. Finalized narration is assembled separately and must be verified in final output.'}


def compare_tail_frames(ffmpeg, source, output, source_seconds, output_seconds):
    import cv2
    def frames(path):
        raw=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-vf','fps=24,scale=320:180','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        return np.frombuffer(raw,dtype=np.uint8).reshape(-1,180,320,3)
    a,b=frames(source),frames(output)
    last=a[-1];errors=[];scale_errors=[]
    for i in range(int(np.ceil(source_seconds*24)),len(b)):
        t=i/24;scale=1+.06*min(1,max(0,(t-source_seconds)/(output_seconds-source_seconds)))
        transform=np.array([[scale,0,160*(1-scale)],[0,scale,90*(1-scale)]],dtype=np.float32)
        expected=cv2.warpAffine(last,transform,(320,180),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        errors.append(float(np.abs(expected.astype(float)-b[i].astype(float)).mean()))
    return {'source_last_decoded_frame_used_for_comparison':True,'all_tail_frames_compared':len(errors),'expected_tail_transform':'centered linear scale 1.00 at source EOF to 1.06 at target duration','tail_frame_mean_rgb_error':round(float(np.mean(errors)),3) if errors else None,'tail_frame_max_rgb_error':round(max(errors),3) if errors else None,'tail_freeze_and_linear_zoom_passed':bool(errors and max(errors)<12),'last_encoded_frame_time_seconds':round((len(b)-1)/24,6)}
