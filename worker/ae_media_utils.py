"""Media helpers used by the web AE worker, independent of retired lip-sync workers."""
import os
import shutil
import subprocess


def ref(asset):
    metadata = asset.get('metadata') or {}
    bucket = metadata.get('gcs_bucket') or metadata.get('storage_bucket') or os.getenv('GCS_BUCKET_NAME', 'air-studio-prod')
    path = metadata.get('gcs_path') or metadata.get('storage_path')
    if not isinstance(path, str) or not path.strip():
        raise ValueError('Source media has no storage path')
    return bucket, path


def ffmpeg():
    executable = os.getenv('FFMPEG_PATH') or shutil.which('ffmpeg')
    if executable: return executable
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError('Media conversion failed: ' + result.stderr[-1200:])
    return result
