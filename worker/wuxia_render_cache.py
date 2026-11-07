"""Release only newly generated Wuxia intermediate movies after verified conversion."""
import hashlib,json,os
from pathlib import Path


def release_temporary_movie(source,output,directory,*,verify=None):
    if os.getenv('AIR_WUXIA_RELEASE_NATIVE_TEMP')!='1':return
    source,output,directory=Path(source),Path(output),Path(directory).resolve()
    from motion_media_storage import media_directory
    own_media=media_directory(directory).resolve()
    if (source.is_symlink() or output.is_symlink() or not source.is_file() or not output.is_file()
            or source.resolve()==output.resolve()
            or source.resolve().parent not in (directory,own_media)
            or source.name not in ('native.avi','native.mov','native.mp4','native.mxf','base.mp4')
            or output.resolve().parent!=own_media
            or output.name not in ('base.mp4','voice-synced.mp4')):
        raise ValueError('Refusing to release a source or movie outside this render attempt')
    if verify is None:
        from ae_media_utils import run,ffmpeg
        from ae_scene_production import _video_info
        def verify(path):
            info=_video_info(path)
            run([ffmpeg(),'-v','error','-i',str(path),'-f','null','-'])
            return info
    before,after=verify(source),verify(output)
    if (any(before[k]!=after[k] for k in ('width','height'))
            or abs(before['duration']-after['duration'])>1/24+.01):
        raise ValueError('Converted movie failed native timing/canvas verification')
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb')as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    receipt={'temporary_file':str(source),'temporary_sha256':digest(source),'verified_output':str(output),'output_sha256':digest(output),'full_decode_verified':True,'video':after,'released':False}
    target=directory/(source.stem+'-temporary-receipt.json')
    target.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    source.unlink();receipt['released']=True
    target.write_text(json.dumps(receipt,indent=2),encoding='utf-8')


def capture_review_frame(movie,time,path,*,compact=False):
    """Full-resolution review evidence; final media is never recompressed here."""
    from ae_media_utils import run,ffmpeg
    path=Path(path).with_suffix('.jpg') if compact else Path(path)
    codec=['-c:v','mjpeg','-q:v','2','-pix_fmt','yuvj444p'] if compact else ['-c:v','png','-pix_fmt','rgb24']
    run([ffmpeg(),'-v','error','-y','-ss',str(time),'-i',str(movie),'-frames:v','1',*codec,'-threads','1',str(path)])
    return path


def release_review_evidence(paths,segment,directory,scene,master):
    """Keep hashes and the authoritative master, bound derived review cache to one scene."""
    if os.getenv('AIR_WUXIA_RELEASE_NATIVE_TEMP')!='1':return
    directory=Path(directory).resolve();master=Path(master).resolve();segment=Path(segment)
    from motion_media_storage import media_directory
    own_media=media_directory(directory).resolve()
    files=list(dict.fromkeys([Path(p)for p in paths]+[segment]));records=[]
    for p in files:
        if not p.is_file():continue
        name=p.name
        frame=(p.resolve().parent==directory and name.startswith(('final-','boundary-','caption-')) and p.suffix in ('.png','.jpg'))
        clip=(p.resolve().parent==own_media and name==f'review-{scene}.mp4')
        if p.is_symlink() or p.resolve()==master or not(frame or clip):raise ValueError('Refusing to release non-review media')
        records.append({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
    receipt=directory/f'review-evidence-{scene}.json'
    receipt.write_text(json.dumps({'master':str(master),'scene':scene,'files':records,'policy':'derived_evidence_reproducible_from_master'},indent=2),encoding='utf-8')
    for r in records:Path(r['file']).unlink()
