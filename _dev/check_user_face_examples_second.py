import sys,json
from pathlib import Path
from PIL import Image
root=Path.cwd();wt=Path('C:/Users/kimse/.codex/worktrees/ae-submitted-video-postwork/LongformGenerator');sys.path[:0]=[str(wt/'worker'),str(wt)]
from dotenv import load_dotenv
load_dotenv(root/'.env',override=False)
from codex_content_runner import CodexContentConfig
from worker.character_face_distinctness import FaceDistinctnessReviewer
out=root/'_dev/artifacts/face-distinctness-user-examples';out.mkdir(parents=True,exist_ok=True)
source=Image.open('C:/Users/kimse/AppData/Local/Temp/codex-clipboard-3b86a907-7824-476c-a44f-1129d7253265.png');source.crop((0,0,145,source.height)).save(out/'older-a.png');source.crop((155,0,source.width,source.height)).save(out/'older-b.png')
r=FaceDistinctnessReviewer(CodexContentConfig.from_environment(),out/'reviews').review({'character_key':'older-a','name':'left character'},out/'older-a.png',[({'character_key':'older-b','name':'right character'},out/'older-b.png')]);(out/'second-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=True))
