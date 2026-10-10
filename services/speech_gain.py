"""Match the subtitle preview's speech levels without moving audio on the timeline."""
import math
import subprocess
import sys
import wave
from array import array
from pathlib import Path


def subtitle_gain(subtitle):
    try:
        value = subtitle.get('volume')
        if value is None:
            ratio = subtitle.get('volume_ratio')
            value = 100 if ratio is None else float(ratio) * 100
        value = float(value) / 100
        return max(0, min(2, value)) if math.isfinite(value) else 1
    except (ValueError, TypeError):
        return 1


def speech_normalization(samples):
    peak, energy, count = 0, 0, 0
    for raw in samples:
        sample = abs(raw) / 32768
        peak = max(peak, sample)
        if sample > 0.00316227766:
            energy += sample * sample
            count += 1
    if not count or not peak:
        return 1
    return min(4, 10 ** (-23 / 20) / math.sqrt(energy / count), 10 ** (-7 / 20) / peak)


def balance_speech_wav(source, destination, subtitles):
    with wave.open(str(source), 'rb') as reader, wave.open(str(destination), 'wb') as writer:
        if reader.getsampwidth() != 2:
            raise ValueError('Speech balancing requires PCM16 audio')
        writer.setparams(reader.getparams())
        rate, total = reader.getframerate(), reader.getnframes()
        cursor = 0

        def copy_until(end):
            nonlocal cursor
            while cursor < end:
                size = min(rate, end - cursor)
                writer.writeframesraw(reader.readframes(size))
                cursor += size

        for subtitle in subtitles:
            start = max(0, min(total, int(float(subtitle['start']) * rate)))
            end = max(start, min(total, int(float(subtitle['end']) * rate)))
            if start < cursor:
                raise ValueError('Overlapping speech intervals cannot be balanced safely')
            copy_until(start)
            samples = array('h', reader.readframes(end - start))
            if sys.byteorder != 'little':
                samples.byteswap()
            gain = speech_normalization(samples) * subtitle_gain(subtitle)
            for i, sample in enumerate(samples):
                samples[i] = max(-32768, min(32767, round(sample * gain)))
            if sys.byteorder != 'little':
                samples.byteswap()
            writer.writeframesraw(samples.tobytes())
            cursor = end
        copy_until(total)
    return total / rate


def prepare_speech_audio(audio_path, temp_dir, ffmpeg_exe, subtitles):
    directory = Path(temp_dir) / 'audio'
    directory.mkdir(parents=True, exist_ok=True)
    decoded, balanced = directory / 'speech_source.wav', directory / 'speech_balanced.wav'
    result = subprocess.run([
        ffmpeg_exe, '-hide_banner', '-y', '-i', str(audio_path), '-vn',
        '-ar', '48000', '-c:a', 'pcm_s16le', str(decoded),
    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800)
    if result.returncode:
        raise RuntimeError(f'Speech volume preparation failed: {result.stderr[-500:]}')
    try:
        duration = balance_speech_wav(decoded, balanced, subtitles)
    finally:
        decoded.unlink(missing_ok=True)
    # No loudness normalization after manual gain: that would undo the editor.
    return str(balanced), duration
