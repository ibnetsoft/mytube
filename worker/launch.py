"""Portable entry point: independent script worker or local media supervisor."""
import argparse, os, runpy, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--role',choices=['script','local','coordinates'],required=True);parser.add_argument('--env-file');parser.add_argument('--check',action='store_true')
    args,extra=parser.parse_known_args()
    if args.env_file:
        from dotenv import load_dotenv
        target=Path(args.env_file).expanduser().resolve()
        if not target.is_file():raise SystemExit('Connection settings file does not exist')
        os.environ['AIR_WORKER_ENV_FILE']=str(target);load_dotenv(target,override=False)
    import worker_config
    os.environ['AIR_WORKER_ROLE']=args.role
    if args.role in ('script','coordinates'):
        if not (shutil.which('codex') or shutil.which('codex.cmd')):raise SystemExit('Install and authenticate Codex CLI before starting the script worker')
        if args.check:
            import worker.codex_content_runner
            if args.role == 'coordinates':
                import ae_speaker_coordinates, ae_highlight_worker
                ae_highlight_worker._supabase()
                print('Coordinate runtime and database settings are available. Run codex login status to verify authentication.')
            else:
                import fastapi, uvicorn
                print('Script runtime imports and Codex CLI are available. Run codex login status to verify authentication.')
            return
        module='worker.ae_speaker_coordinates' if args.role=='coordinates' else 'worker.codex_local_console'
    else:
        if sys.platform!='win32':raise SystemExit('Local AE/render worker requires Windows and installed After Effects')
        if args.check:
            from adobe_tools import find_aerender
            import imageio_ffmpeg
            import ae_mouth_worker, ae_video_tracking
            ae_mouth_worker.ae._supabase()
            if not (shutil.which("codex") or shutil.which("codex.cmd")):
                raise SystemExit("Install and authenticate Codex CLI for AE mouth layers before starting the local worker")
            if not find_aerender():raise SystemExit('After Effects aerender was not found')
            print('Local media prerequisites available; FFmpeg: '+imageio_ffmpeg.get_ffmpeg_exe());return
        module='worker.local_media_supervisor'
    sys.argv=[module,*extra];runpy.run_module(module,run_name='__main__')
if __name__=='__main__':main()
