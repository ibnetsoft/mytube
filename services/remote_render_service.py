import os
import json
import shutil
import zipfile
import tempfile
import time
import uuid
import datetime
from config import config
import database as db
from app.modes import is_shorts_mode

def package_project_assets(project_id: int, use_subtitles: bool = True, resolution: str = "1080p") -> str:
    """
    베트남 클라이언트용: 프로젝트의 모든 이미지, 오디오, 자막 및 설정을 취합하여
    의존성 없는 ZIP 패키지를 생성하고 그 경로를 반환합니다.
    """
    temp_dir = tempfile.mkdtemp(prefix=f"render_pkg_{project_id}_")
    try:
        # 1. 대상 디렉토리 생성
        images_dir = os.path.join(temp_dir, "images")
        audio_dir = os.path.join(temp_dir, "audio")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(audio_dir, exist_ok=True)

        # 2. 데이터 수집
        images_data = db.get_image_prompts(project_id) or []
        tts_data = db.get_tts(project_id) or {}
        p_settings = db.get_project_settings(project_id) or {}
        global_settings = db.get_global_setting("app_mode", "longform")
        
        proj_mode = p_settings.get("app_mode", global_settings)
        is_shorts_project = (is_shorts_mode(proj_mode) or p_settings.get("is_shorts") == True)
        project_aspect = "9:16" if is_shorts_project else "16:9"

        # 3. 오디오 복사
        audio_path = tts_data.get("audio_path")
        audio_filename = None
        if audio_path and os.path.exists(audio_path):
            audio_filename = os.path.basename(audio_path)
            shutil.copy2(audio_path, os.path.join(audio_dir, audio_filename))

        # 4. 이미지/비디오 에셋 복사 및 타임라인 추적
        # 렌더링에 사용할 파일 경로 리스트 구하기 (기존 video.py 로직 모방)
        images = []
        timeline_path = p_settings.get('timeline_images_path')
        loaded_from_timeline = False
        
        if timeline_path and os.path.exists(timeline_path):
            try:
                with open(timeline_path, "r", encoding="utf-8") as f:
                    urls = json.load(f)
                for url in urls:
                    if not url:
                        images.append("")
                        continue
                    fpath = None
                    if url.startswith("/static/"):
                        fpath = os.path.join(config.STATIC_DIR, url.replace("/static/", "", 1).replace("/", os.sep))
                    elif url.startswith("/output/"):
                        fpath = os.path.join(config.OUTPUT_DIR, url.replace("/output/", "", 1).replace("/", os.sep))
                    if fpath and os.path.exists(fpath):
                        images.append(fpath)
                    else:
                        images.append("")
                if images:
                    loaded_from_timeline = True
            except Exception:
                pass
                
        if not loaded_from_timeline:
            for img in images_data:
                target_url = img.get("image_url") or img.get("video_url")
                fpath = None
                if target_url:
                    if target_url.startswith("/static/"):
                        fpath = os.path.join(config.STATIC_DIR, target_url.replace("/static/", "", 1).replace("/", os.sep))
                    elif target_url.startswith("/output/"):
                        fpath = os.path.join(config.OUTPUT_DIR, target_url.replace("/output/", "", 1).replace("/", os.sep))
                if fpath and os.path.exists(fpath):
                    images.append(fpath)
                else:
                    images.append("")

        # 비디오 업그레이드 패치 패키징
        img_to_video = {}
        for p in images_data:
            v_url = p.get('video_url')
            i_url = p.get('image_url')
            if i_url and v_url:
                img_to_video[os.path.basename(i_url)] = v_url

        final_images_filenames = []
        for img_path in images:
            if not img_path:
                final_images_filenames.append(None)
                continue
                
            base_name = os.path.basename(img_path)
            # 비디오 에셋 적용 여부 확인
            if base_name in img_to_video:
                v_url = img_to_video[base_name]
                v_path = None
                if v_url.startswith("/static/"):
                    v_path = os.path.join(config.STATIC_DIR, v_url.replace("/static/", "", 1).replace("/", os.sep))
                elif v_url.startswith("/output/"):
                    v_path = os.path.join(config.OUTPUT_DIR, v_url.replace("/output/", "", 1).replace("/", os.sep))
                if v_path and os.path.exists(v_path):
                    img_path = v_path
                    base_name = os.path.basename(img_path)

            # 대상 패키지 디렉토리에 복사
            dest_path = os.path.join(images_dir, base_name)
            shutil.copy2(img_path, dest_path)
            final_images_filenames.append(base_name)

        # 5. 자막 데이터 및 타이밍 설정
        subs = []
        if use_subtitles:
            db_sub_path = p_settings.get('subtitle_path')
            if db_sub_path and os.path.exists(db_sub_path):
                try:
                    with open(db_sub_path, "r", encoding="utf-8") as f:
                        subs = json.load(f)
                except Exception:
                    pass
            if not subs:
                output_dir_local, _ = db.get_project_output_dir(project_id) if hasattr(db, 'get_project_output_dir') else (os.path.join(config.OUTPUT_DIR, f"project_{project_id}"), "")
                saved_sub_path = os.path.join(output_dir_local, f"subtitles_{project_id}.json")
                if os.path.exists(saved_sub_path):
                    try:
                        with open(saved_sub_path, "r", encoding="utf-8") as f:
                            subs = json.load(f)
                    except Exception:
                        pass

        # 자막 스타일 설정 준비
        s_settings = {
            "font_color": p_settings.get("subtitle_base_color", "white"),
            "style_name": p_settings.get("subtitle_style_enum", "Basic_White"),
            "font_size": float(p_settings.get("subtitle_font_size", 5.4)),
            "stroke_color": p_settings.get("subtitle_stroke_color", "black"),
            "stroke_width": float(p_settings.get("subtitle_stroke_width") or 0.0),
            "subtitle_stroke_enabled": 1 if str(p_settings.get("subtitle_stroke_enabled", 0)).lower() in ['true', '1'] else 0, 
            "subtitle_pos_y": p_settings.get("subtitle_pos_y"),
            "bg_enabled": 1 if str(p_settings.get("subtitle_bg_enabled", 1)).lower() in ['true', '1'] else 0,
            "line_spacing": float(p_settings.get("subtitle_line_spacing", 0.1)),
            "bg_color": p_settings.get("subtitle_bg_color", "#000000"),
            "bg_opacity": float(p_settings.get("subtitle_bg_opacity", 0.5))
        }

        # 이미지 개별 시간(forced_timings) 로드
        forced_timings = None
        tm_path = p_settings.get('image_timings_path')
        if tm_path and os.path.exists(tm_path):
            try:
                with open(tm_path, "r", encoding="utf-8") as f_tm:
                    forced_timings = json.load(f_tm)
            except Exception:
                pass

        # 백그라운드 영상 (BGM/동영상 백그라운드) 및 인트로 설정 복사
        bg_video_url = p_settings.get('bg_video_url')
        intro_video_path = p_settings.get('intro_video_path')
        intro_filename = None
        if intro_video_path and os.path.exists(intro_video_path):
            intro_filename = os.path.basename(intro_video_path)
            shutil.copy2(intro_video_path, os.path.join(temp_dir, intro_filename))

        # 6. 메타데이터 구성 (config.json)
        from services.auth_service import auth_service
        project_obj = db.get_project(project_id) or {}
        project_name = project_obj.get("name", f"Project {project_id}")

        metadata = {
            "project_id": project_id,
            "project_name": project_name,
            "email": auth_service.get_user_email() or "unknown",
            "use_subtitles": use_subtitles,
            "resolution": resolution,
            "aspect_ratio": project_aspect,
            "audio_filename": audio_filename,
            "images": final_images_filenames,
            "subtitles": subs,
            "subtitle_settings": s_settings,
            "forced_timings": forced_timings,
            "bg_video_url": bg_video_url,
            "intro_filename": intro_filename,
            "app_mode": proj_mode
        }

        with open(os.path.join(temp_dir, "config.json"), "w", encoding="utf-8") as f_conf:
            json.dump(metadata, f_conf, ensure_ascii=False, indent=4)

        # 7. ZIP 패키징
        zip_output_dir = os.path.join(config.OUTPUT_DIR, f"project_{project_id}")
        os.makedirs(zip_output_dir, exist_ok=True)
        zip_path = os.path.join(zip_output_dir, f"remote_render_pkg_{project_id}.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, rel_path)

        return zip_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def remote_render_executor_func(task_id: str, temp_dir: str, use_gpu: bool = False):
    """
    한국 원격 서버용: 압축 풀린 임시 폴더(temp_dir) 내 리소스들을 로드하여 
    MoviePy/FFmpeg를 통해 고속 영상 빌드를 수행하고 output.mp4 파일로 저장합니다.
    """
    progress_file = os.path.join(temp_dir, "progress.txt")
    
    def update_progress(percent: int, message: str):
        with open(progress_file, "w", encoding="utf-8") as f_prog:
            f_prog.write(json.dumps({"progress": percent, "message": message, "timestamp": time.time()}))

    try:
        update_progress(5, "설정 로드 중...")
        config_path = os.path.join(temp_dir, "config.json")
        with open(config_path, "r", encoding="utf-8") as f_conf:
            metadata = json.load(f_conf)

        aspect_ratio = metadata.get("aspect_ratio", "16:9")
        resolution = metadata.get("resolution", "1080p")
        audio_filename = metadata.get("audio_filename")
        images_filenames = metadata.get("images", [])
        subs = metadata.get("subtitles", [])
        s_settings = metadata.get("subtitle_settings", {})
        forced_timings = metadata.get("forced_timings")
        bg_video_url = metadata.get("bg_video_url")
        intro_filename = metadata.get("intro_filename")
        
        # 해상도 값 산출
        if aspect_ratio == "9:16":
            target_resolution = (1080, 1920) if resolution == "1080p" else (720, 1280)
        else:
            target_resolution = (1920, 1080) if resolution == "1080p" else (1280, 720)

        audio_path = os.path.join(temp_dir, "audio", audio_filename) if audio_filename else None
        if not audio_path or not os.path.exists(audio_path):
            raise Exception("TTS 오디오 파일을 찾을 수 없습니다.")

        # MoviePy 동적 모듈 임포트
        try:
            from moviepy import AudioFileClip, ImageClip, VideoFileClip, CompositeVideoClip, TextClip
        except ImportError:
            from moviepy.editor import AudioFileClip, ImageClip, VideoFileClip, CompositeVideoClip, TextClip

        update_progress(15, "오디오 정보 파싱 중...")
        # 오디오 및 재생 시간 산출
        with AudioFileClip(audio_path) as audio_clip:
            audio_duration = audio_clip.duration

        # 이미지 리스트 재구성
        images = []
        for fname in images_filenames:
            if fname:
                path = os.path.join(temp_dir, "images", fname)
                images.append(path if os.path.exists(path) else "")
            else:
                images.append("")

        update_progress(30, "이미지 배치 및 타임라인 생성 중...")
        # 이미지 배치 시간 계산 (기존 video_service logic 참고)
        num_images = len([img for img in images if img])
        if num_images == 0:
            raise Exception("렌더링할 이미지 리소스가 없습니다.")

        durations = []
        if forced_timings and len(forced_timings) >= num_images:
            durations = [float(t) for t in forced_timings[:num_images]]
            # 총 합계가 오디오보다 모자라면 마지막 이미지 조절
            total_dur = sum(durations)
            if total_dur < audio_duration:
                durations[-1] += (audio_duration - total_dur)
        else:
            avg_dur = audio_duration / num_images
            durations = [avg_dur] * num_images

        # 클립 생성
        clips = []
        current_time = 0.0
        
        valid_img_idx = 0
        for img_path in images:
            if not img_path:
                continue
            
            dur = durations[valid_img_idx]
            valid_img_idx += 1
            
            if img_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                # 비디오 클립인 경우
                with VideoFileClip(img_path) as v_clip:
                    # 루핑 혹은 트림 처리
                    if v_clip.duration < dur:
                        # 비디오가 짧으면 속도를 늦추거나 반복
                        v_looped = v_clip.with_duration(dur) if hasattr(v_clip, 'with_duration') else v_clip.set_duration(dur)
                        clips.append(v_looped.with_position("center").with_start(current_time))
                    else:
                        v_trimmed = v_clip.subclipped(0, dur) if hasattr(v_clip, 'subclipped') else v_clip.subclip(0, dur)
                        clips.append(v_trimmed.with_position("center").with_start(current_time))
            else:
                # 일반 이미지인 경우
                with ImageClip(img_path) as i_clip:
                    i_clip = i_clip.with_duration(dur) if hasattr(i_clip, 'with_duration') else i_clip.set_duration(dur)
                    clips.append(i_clip.with_position("center").with_start(current_time))
            
            current_time += dur

        update_progress(50, "비디오 컴포지팅 작업 중...")
        # 1차 비디오 제작 (이미지/비디오 에셋 합성)
        video = CompositeVideoClip(clips, size=target_resolution).with_audio(audio_clip)

        # 자막 추가 (원격용 초간단 자막 합성 또는 MoviePy TextClip)
        # 렌더링 서버 폰트 문제 예방을 위해 기본 Arial 또는 System 폰트 사용
        if metadata.get("use_subtitles") and subs:
            update_progress(70, "자막 오버레이 합성 중...")
            text_clips = []
            font_size_px = int(target_resolution[1] * (s_settings.get("font_size", 5.4) / 100))
            
            # Simple TextClip composition
            for sub in subs:
                start = float(sub.get('start', 0))
                end = float(sub.get('end', 0))
                text = sub.get('text', '')
                if not text:
                    continue
                
                try:
                    txt_clip = TextClip(
                        text=text,
                        font="Arial",
                        font_size=font_size_px,
                        color=s_settings.get("font_color", "white"),
                        stroke_color=s_settings.get("stroke_color", "black"),
                        stroke_width=s_settings.get("stroke_width", 2.0),
                        size=(int(target_resolution[0] * 0.9), None),
                        method="caption"
                    )
                    txt_clip = txt_clip.with_start(start).with_duration(end - start)
                    
                    # 위치 조정
                    pos_y = target_resolution[1] * 0.8
                    txt_clip = txt_clip.with_position(("center", pos_y))
                    text_clips.append(txt_clip)
                except Exception as e_txt:
                    print(f"Warning: Failed to create TextClip for '{text}': {e_txt}")

            if text_clips:
                video = CompositeVideoClip([video] + text_clips, size=target_resolution)

        # 아웃풋 비디오 작성
        output_file_path = os.path.join(temp_dir, "output.mp4")
        update_progress(80, "최종 영상 인코딩 중 (GPU 가속 적용)...")
        
        # GPU 가속 코덱 자동 감지 또는 수동 설정
        write_params = {
            "fps": 24,
            "temp_audiofile": os.path.join(temp_dir, "temp-audio.m4a"),
            "remove_temp": True,
            "audio_codec": "aac"
        }
        
        if use_gpu:
            write_params["codec"] = "h264_nvenc"
            write_params["ffmpeg_params"] = ["-preset", "fast", "-cq", "23"]
        else:
            write_params["codec"] = "libx264"
            write_params["preset"] = "medium"

        video.write_videofile(output_file_path, **write_params)
        
        update_progress(100, "완료")
    except Exception as err:
        update_progress(-1, f"오류 발생: {str(err)}")
        raise err


def trigger_remote_render_flow(project_id: int, remote_url: str, use_subtitles: bool = True, resolution: str = "1080p") -> str:
    """
    클라이언트에서 원격 렌더링 서버로 프로젝트 패키지 ZIP 파일을 전송하고 작업 ID(task_id)를 받습니다.
    """
    import requests
    zip_path = package_project_assets(project_id, use_subtitles, resolution)
    if not zip_path or not os.path.exists(zip_path):
        raise Exception("프로젝트 패키지 ZIP 파일 생성 실패")
        
    url = f"{remote_url.rstrip('/')}/api/remote/render"
    try:
        with open(zip_path, 'rb') as f:
            files = {'file': (os.path.basename(zip_path), f, 'application/zip')}
            response = requests.post(url, files=files, timeout=60)
            
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("status") == "ok":
                task_id = res_data.get("task_id")
                # Save task_id to project settings
                db.update_project_setting(project_id, "remote_task_id", task_id)
                db.update_project_setting(project_id, "remote_render_url", remote_url)
                return task_id
            else:
                raise Exception(res_data.get("error", "원격 서버 오류"))
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
    finally:
        # ZIP 파일은 전송 후 삭제해 용량 확보
        try:
            os.remove(zip_path)
        except Exception:
            pass


def poll_remote_render_status(remote_url: str, task_id: str) -> dict:
    """
    원격 서버에 작업 상태 및 진행률을 질의합니다.
    """
    import requests
    url = f"{remote_url.rstrip('/')}/api/remote/status/{task_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "progress": -1, "message": f"서버 응답 오류 (HTTP {response.status_code})"}
    except Exception as e:
        return {"status": "error", "progress": -1, "message": f"연결 실패: {str(e)}"}


def download_remote_render_result(remote_url: str, task_id: str, project_id: int) -> str:
    """
    인코딩 완료된 원격 비디오 파일을 가져와 로컬 프로젝트 디렉토리에 저장합니다.
    """
    import requests
    from config import config
    
    url = f"{remote_url.rstrip('/')}/api/remote/download/{task_id}"
    
    output_dir, web_dir = db.get_project_output_dir(project_id) if hasattr(db, 'get_project_output_dir') else (os.path.join(config.OUTPUT_DIR, f"project_{project_id}"), f"/output/project_{project_id}")
    now_kst = config.get_kst_time()
    filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"
    local_path = os.path.join(output_dir, filename)
    
    os.makedirs(output_dir, exist_ok=True)
    
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                
    web_video_path = f"{web_dir}/{filename}"
    db.update_project_setting(project_id, "video_path", web_video_path)
    db.update_project(project_id, status="rendered")
    
    # [NEW] 구글 드라이브 업로드 및 Supabase 동기화 백그라운드 구동
    try:
        from services.sync_service import start_upload_and_sync_background
        start_upload_and_sync_background(project_id, local_path)
    except Exception as se:
        print(f"[Sync] Failed to start background sync for remote render: {se}")
        
    return web_video_path
