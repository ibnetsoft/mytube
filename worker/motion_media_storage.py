"""Keep large render intermediates on the available media drive, images in the review sandbox."""
import os,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def media_directory(directory):
    directory=Path(directory).resolve()
    scope=(ROOT/'output/codex-local-console/motion-automation').resolve()
    configured=os.getenv('AIR_MOTION_MEDIA_ROOT','').strip()
    drive=Path('D:/')
    if not directory.is_relative_to(scope):return directory
    if configured:
        target=Path(configured).expanduser().resolve()
    elif os.name=='nt' and drive.is_dir() and shutil.disk_usage(ROOT).free<15*1024**3:
        target=drive/'AIRStudio'/'motion-render-media'
    else:return directory
    target=target/directory.relative_to(scope)
    target.mkdir(parents=True,exist_ok=True)
    return target
