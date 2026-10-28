import sys,json
from pathlib import Path
from PIL import Image
root=Path.cwd();wt=Path('C:/Users/kimse/.codex/worktrees/ae-submitted-video-postwork/LongformGenerator');sys.path[:0]=[str(wt/'worker'),str(wt)]
from dotenv import load_dotenv
load_dotenv(root/'.env',override=False)
from codex_content_runner import CodexContentConfig
from worker.character_face_distinctness import FaceDistinctnessReviewer
out=root/'_dev/artifacts/face-distinctness-user-examples';out.mkdir(parents=True,exist_ok=True)
source=Image.open('C:/Users/kimse/AppData/Local/Temp/codex-clipboard-551e57ed-3c88-4121-acd6-32478c4b153a.png');source.crop((0,0,260,source.height)).save(out/'man-a.png');source.crop((270,0,source.width,source.height)).save(out/'man-b.png')
r=FaceDistinctnessReviewer(CodexContentConfig.from_environment(),out/'reviews').review({'character_key':'man-a','name':'left character'},out/'man-a.png',[({'character_key':'man-b','name':'right character'},out/'man-b.png')]);(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=True))
