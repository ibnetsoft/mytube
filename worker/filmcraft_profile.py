"""Legacy-compatible font outlines/metrics and the measured native delivery profile."""
import os
import hashlib
from pathlib import Path
from functools import lru_cache
from scripts.filmcraft import sha


def encoding_profile(contract,size,fps):
    from copy import deepcopy
    result=deepcopy(contract['encoding'])
    ratio=size[0]*size[1]*fps/(1920*1080*24)
    for key in ('bitrateKbps','maxBitrateKbps'):result[key]=max(100,round(result[key]*ratio))
    return {**result,'includeAudio':True,'burnCaptions':True}


@lru_cache(maxsize=32)
def caption_face(family):
    """Use the actual legacy font file, never a conflicting system family copy."""
    from fontTools.ttLib import TTFont,TTCollection
    from services.ffmpeg_slideshow_service import _prepare_fonts_dir,_ass_font_family
    root=Path(__file__).resolve().parents[1]
    cache=root/'output/filmcraft/font-profiles'/hashlib.sha256(family.encode('utf8')).hexdigest()[:20]
    cache.mkdir(parents=True,exist_ok=True)
    directory=Path(_prepare_fonts_dir(str(cache),{'subtitle_font_family':family}))
    canonical=_ass_font_family(family).casefold()
    fallback=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Microsoft/Windows/Fonts']
    chosen=None
    for folder in (directory,*fallback):
        if not folder.is_dir():continue
        for path in sorted(folder.glob('*')):
            if path.suffix.lower() not in ('.ttf','.otf','.ttc','.otc'):continue
            fonts=TTCollection(path,lazy=True).fonts if path.suffix.lower() in ('.ttc','.otc') else [TTFont(path,lazy=True)]
            for index,font in enumerate(fonts):
                names={n.toUnicode().casefold() for n in font['name'].names if n.nameID in (1,16)}
                if canonical in names or (folder==directory and directory.name=='fast_render_fonts' and len(list(directory.glob('*')))==1):
                    chosen=(path,index)
                font.close()
                if chosen:break
            if chosen:break
        if chosen:break
    if chosen is None:raise ValueError('Cannot resolve the selected legacy subtitle face: '+family)
    source,index=chosen;identity=sha(source)
    font=TTFont(source,fontNumber=index,recalcTimestamp=False)
    private='AIR Legacy '+identity[:16]+' '+str(index)
    units=font['head'].unitsPerEm;win=font['OS/2'].usWinAscent+font['OS/2'].usWinDescent
    metrics={'units':units,'win_height':win,'win_descent':font['OS/2'].usWinDescent,
        'ascent':font['hhea'].ascent,'descent':font['hhea'].descent}
    for record in font['name'].names:
        value=private if record.nameID in (1,16) else 'SemiBold' if record.nameID in (2,17) else private+' SemiBold' if record.nameID==4 else private.replace(' ','')+'-SemiBold' if record.nameID==6 else None
        if value is not None:record.string=value.encode(record.getEncoding(),errors='replace')
    font_dir=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Microsoft/Windows/Fonts'
    font_dir.mkdir(parents=True,exist_ok=True)
    target=font_dir/(private.replace(' ','')+('.otf' if 'CFF ' in font else '.ttf'))
    if not target.exists():
        temporary=target.with_suffix('.tmp');font.save(temporary);temporary.replace(target)
    font.close()
    return {'family':private,'source':str(source),'sha256':identity,'file':str(target),**metrics}


def caption_metrics(face,legacy_pixels,line_spacing,height):
    pixels=legacy_pixels*face['units']/face['win_height']
    offset=round(pixels*(face['win_descent']/face['units']-line_spacing/2+
        (face['ascent']+face['descent'])/(2*face['units'])))
    return pixels*1080/height,offset/height
