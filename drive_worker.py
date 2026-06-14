import os
import time
import json
import shutil
import datetime
from pathlib import Path

# ==========================================
# Google Drive GPU Render Worker
# ==========================================

# 구글 드라이브 큐 폴더 경로 (본인 환경에 맞게 수정)
DRIVE_RENDER_QUEUE_PATH = os.getenv("DRIVE_RENDER_QUEUE_PATH", "G:/내 드라이브/Longform_Render_Queue")

REQUESTS_DIR = os.path.join(DRIVE_RENDER_QUEUE_PATH, "requests")
COMPLETED_DIR = os.path.join(DRIVE_RENDER_QUEUE_PATH, "completed")

os.makedirs(REQUESTS_DIR, exist_ok=True)
os.makedirs(COMPLETED_DIR, exist_ok=True)

# 롱폼생성기 로컬 모듈 로드 경로 추가 (동일 소스코드가 GPU PC에도 있다고 가정)
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from services.video_service import video_service
except ImportError:
    print("❌ 롱폼생성기 소스코드를 찾을 수 없습니다. (video_service.py)")
    sys.exit(1)


def process_job(job_dir):
    job_json_path = os.path.join(job_dir, "job.json")
    if not os.path.exists(job_json_path):
        return

    print(f"\n[{datetime.datetime.now()}] 🚀 새로운 렌더링 작업 감지: {os.path.basename(job_dir)}")
    
    with open(job_json_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    # 파라미터 복원
    project_id = job.get("project_id")
    output_filename = job.get("output_filename")
    
    # 절대 경로로 매핑
    def to_abs(name):
        return os.path.join(job_dir, name) if name else None

    images = [to_abs(img) if img else "" for img in job.get("images", [])]
    audio_path = to_abs(job.get("audio_path"))
    bg_video = to_abs(job.get("background_video_url"))
    thumb = to_abs(job.get("thumbnail_path"))
    template = to_abs(job.get("template_overlay_path"))
    intro = to_abs(job.get("intro_video_path"))
    
    # 해상도 복원
    resolution_list = job.get("resolution")
    resolution = tuple(resolution_list) if resolution_list else (1080, 1920)

    # 렌더링 결과 저장될 로컬 임시 폴더
    output_path = os.path.join(job_dir, output_filename)

    try:
        # GPU 렌더링 실행
        print(f"[{datetime.datetime.now()}] ⚙️ 렌더링 시작 (GPU 가속 권장)")
        final_video_path = video_service.create_slideshow(
            images=images,
            audio_path=audio_path,
            output_filename=output_path,
            resolution=resolution,
            subtitles=job.get("subtitles"),
            subtitle_settings=job.get("subtitle_settings"),
            background_video_url=bg_video,
            thumbnail_path=thumb,
            template_overlay_path=template,
            duration_per_image=job.get("duration_per_image"),
            fade_in_flags=job.get("fade_in_flags"),
            image_effects=job.get("image_effects"),
            intro_video_path=intro,
            project_id=project_id
        )
        
        if final_video_path and os.path.exists(final_video_path):
            print(f"[{datetime.datetime.now()}] ✅ 렌더링 성공: {final_video_path}")
            
            # completed 폴더로 결과물 전송
            dest_dir = os.path.join(COMPLETED_DIR, f"project_{project_id}")
            os.makedirs(dest_dir, exist_ok=True)
            
            dest_file = os.path.join(dest_dir, output_filename)
            shutil.copy2(final_video_path, dest_file)
            
            # job_info 저장 (메인 PC가 읽기 위함)
            with open(os.path.join(dest_dir, "result.json"), "w", encoding="utf-8") as f:
                json.dump({"project_id": project_id, "status": "completed", "file": output_filename}, f)
                
            # 완료 마커 (동기화 꼬임 방지)
            with open(os.path.join(dest_dir, "done.txt"), "w") as f:
                f.write("done")
                
            print(f"[{datetime.datetime.now()}] 📦 결과물 구글 드라이브 업로드 완료")
            
            # 원본 요청 폴더 삭제 (정리)
            try:
                shutil.rmtree(job_dir)
            except Exception as e:
                print(f"임시 폴더 삭제 실패: {e}")
                
        else:
            print("❌ 렌더링 결과 파일이 생성되지 않았습니다.")

    except Exception as e:
        import traceback
        print(f"❌ 렌더링 중 오류 발생: {e}")
        traceback.print_exc()

def main():
    print(f"==================================================")
    print(f" 🖥️ Google Drive GPU Render Worker 시작")
    print(f" 📂 감시 폴더: {REQUESTS_DIR}")
    print(f"==================================================\n")
    
    while True:
        try:
            # requests 폴더 내의 프로젝트 폴더들 확인
            for item in os.listdir(REQUESTS_DIR):
                job_dir = os.path.join(REQUESTS_DIR, item)
                if os.path.isdir(job_dir):
                    # ready.txt가 존재해야 패키징(동기화)이 완전히 끝난 것
                    if os.path.exists(os.path.join(job_dir, "ready.txt")):
                        process_job(job_dir)
            
        except Exception as e:
            print(f"워커 에러: {e}")
            
        time.sleep(5)  # 5초마다 폴더 확인

if __name__ == "__main__":
    main()
