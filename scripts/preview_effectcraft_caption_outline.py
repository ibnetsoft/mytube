import json,subprocess,sys
from pathlib import Path
import imageio_ffmpeg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.ffmpeg_slideshow_service import _write_ass_file,_prepare_fonts_dir,_filter_path
D=Path(__file__).resolve().parents[1]/'output/effectcraft/project-3376-final-20261021'
c=json.loads((D/'final-config.json').read_text(encoding='utf8'))
settings={**c['render_settings'],'subtitle_stroke_width':'4','subtitle_stroke_color':'#000000'}
fonts=_prepare_fonts_dir(str(D),settings);ass=D/'outline-preview.ass'
_write_ass_file(str(ass),c['subtitles'],settings,(1920,1080),fonts)
video=Path.home()/'AppData/Local/Temp/air-render-checkpoints/e8820d13-5cb0-4971-aa9e-08d01f10c7fe/motion-visual.mp4'
t=110
graph=f"setpts=PTS+{t}/TB,subtitles=filename='{_filter_path(str(ass))}':fontsdir='{_filter_path(fonts)}'"
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-ss',str(t),'-i',str(video),'-vf',graph,'-frames:v','1',str(D/'caption-outline-preview.png')],check=True)
