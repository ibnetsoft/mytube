import ast,os,sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv;load_dotenv(ROOT/'.env')
import remote_drive_worker;remote_drive_worker._configure_ffmpeg_for_worker()
from services import ffmpeg_slideshow_service as ff
from services.remote_render_service import remote_render_executor_func
RUN=ROOT/'output/project-recovery-e9233112/reviewed-final-local'
original=ff._run_command;original_render=ff.render_ffmpeg_slideshow
source=ast.parse((ROOT/'scripts/repair_3373_template_render.py').read_text(encoding='utf8'));nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('limited','batched_render')];exec(compile(ast.Module(body=nodes,type_ignores=[]),'<bounded-encoder>','exec'));ff._run_command=limited;ff.render_ffmpeg_slideshow=batched_render
remote_render_executor_func('3373-reviewed-final-v10',str(RUN),use_gpu=True)
print('LOCAL_RENDER_COMPLETED',str(RUN/'output.mp4'),flush=True)
