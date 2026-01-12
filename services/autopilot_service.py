
import asyncio
import json
import os
import random
from datetime import datetime, timedelta
import httpx
from config import config
import database as db
from services.gemini_service import gemini_service
from services.prompts import prompts
from services.tts_service import tts_service
from services.video_service import video_service
from services.youtube_upload_service import youtube_upload_service

class AutoPilotService:
    def __init__(self):
        self.search_url = f"{config.YOUTUBE_BASE_URL}/search"

    async def run_workflow(self, keyword: str, project_id: int = None):
        """오토파일럿 전체 워크플로우 실행 (체크포인트 재개 지원)"""
        print(f"🚀 [Auto-Pilot] '{keyword}' 작업 시작 (ID: {project_id if project_id else 'New'})")
        
        try:
            # 1~2. 소재 발굴 및 프로젝트 생성
            if not project_id:
                print(f"🔍 [1/8] 소재 발굴 중: {keyword}")
                video = await self._find_best_material(keyword)
                if not video:
                    print("❌ 적절한 소재를 찾지 못했습니다.")
                    return

                project_name = f"[Auto] {keyword} - {video['snippet']['title'][:20]}"
                project_id = db.create_project(name=project_name, topic=keyword)
                print(f"✅ [2/8] 프로젝트 생성 완료: ID {project_id}")
                
                # 분석용 영상 데이터 보관 (status check를 위해 project object 가져오기 용도)
                current_status = "created"
            else:
                project = db.get_project(project_id)
                if not project:
                    print(f"❌ ID {project_id} 프로젝트를 찾을 수 없습니다.")
                    return
                current_status = project.get('status', 'created')
                print(f"🔄 [Resume] 기존 프로젝트 재개 (상태: {current_status})")

            # 3. AI 분석
            if current_status in ["created", None]:
                print(f"🧠 [3/8] AI 분석 중 (Deep Analysis)...")
                # project_id로 재개 시 video_id를 다시 찾아야 할 수도 있으나, 
                # 보통 created 단계면 _find_best_material을 거쳐온 상태임.
                # project_id로만 재개하는 경우를 위해 analysis 존재 여부 확인 가능.
                analysis = db.get_analysis(project_id)
                if not analysis:
                    # video 데이터를 가져올 방법이 없으면 중단 (또는 재검색)
                    # 여기서는 run_workflow가 처음 호출될 때 video를 찾는다고 가정.
                    # 만약 project_id만 있고 video 정보가 소실되었다면 재검색 수행
                    video = await self._find_best_material(keyword)
                    analysis_result = await self._analyze_video(video['id']['videoId'])
                    db.save_analysis(project_id, video, analysis_result)
                
                db.update_project(project_id, status="analyzed")
                current_status = "analyzed"

            # 4. 기획 및 대본 작성
            if current_status == "analyzed":
                print(f"📝 [4/8] 기획 및 대본 작성 중...")
                analysis = db.get_analysis(project_id)
                script = await self._generate_script(project_id, analysis.get("analysis_result", {}))
                db.update_project_setting(project_id, "script", script)
                db.update_project(project_id, status="scripted")
                current_status = "scripted"

            # 5. 에셋 생성 (이미지 & 오디오)
            if current_status == "scripted":
                print(f"🎨 [5/8] 이미지 및 오디오 생성 중...")
                script_data = db.get_script(project_id)
                await self._generate_assets(project_id, script_data["full_script"])
                db.update_project(project_id, status="tts_done")
                current_status = "tts_done"

            # 6. 영상 렌더링
            if current_status == "tts_done":
                print(f"🎬 [6/8] 최종 영상 렌더링 중...")
                video_path = await self._render_video(project_id)
                # _render_video 내부에서 이미 status="rendered"로 업데이트함
                current_status = "rendered"

            # 7. 업로드
            if current_status == "rendered":
                print(f"📤 [7/8] 유튜브 업로드 (예약) 중...")
                settings = db.get_project_settings(project_id)
                video_path = settings.get("video_path")
                if video_path:
                    # 웹 경로 -> 절대 경로 변환
                    abs_video_path = os.path.join(config.OUTPUT_DIR, video_path.replace("/output/", ""))
                    await self._upload_video(project_id, abs_video_path)
                    db.update_project(project_id, status="uploaded")
            
            print(f"✨ [Auto-Pilot] 작업 완료! (Project ID: {project_id})")

        except Exception as e:
            print(f"❌ [Auto-Pilot] 오류 발생 (Project ID: {project_id}): {e}")
            import traceback
            traceback.print_exc()

    async def _find_best_material(self, keyword: str):
        """유튜브 검색 및 1위 영상 선정"""
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 5, # 상위 5개 중 분석
            "order": "viewCount", # 조회수 순
            "videoDuration": "short", # 쇼츠만
            "key": config.YOUTUBE_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.search_url, params=params)
            data = response.json()
            
            if "items" not in data or not data["items"]:
                return None
                
            # 가장 첫번째(조회수 1등) 영상 선택
            return data["items"][0]

    async def _analyze_video(self, video_id: str):
        """Gemini를 이용한 영상/댓글 분석"""
        # 실제 댓글 가져오기는 복잡하므로, 여기서는 Gemini에게 가상 분석을 맡기거나
        # 기존 analyze_comments 로직을 가져와야 함. 
        # 간소화를 위해 Gemini에게 "이 주제로 떡상각 잡아줘"라고 요청.
        
        prompt = prompts.AUTOPILOT_ANALYZE_VIDEO.format(video_id=video_id)
        request = type('obj', (object,), {"prompt": prompt, "temperature": 0.7})
        result = await gemini_service.generate_content(request)
        
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result["text"])
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        return {"summary": result["text"]}

    async def _generate_script(self, project_id: int, analysis: dict):
        """대본 완전 자동 생성"""
        # 1. 구조 잡기 (생략하고 바로 대본 생성)
        # 2. 대본 생성
        prompt = prompts.AUTOPILOT_GENERATE_SCRIPT.format(
            analysis_json=json.dumps(analysis, ensure_ascii=False)
        )
        request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
        result = await gemini_service.generate_content(request)
        
        script = result["text"]
        # DB 저장
        db.save_script(project_id, script, len(script), 50)
        return script

    async def _generate_assets(self, project_id: int, script: str):
        """이미지 프롬프트 -> 이미지 생성(병렬/재개 지원) -> TTS 생성(재개 지원)"""
        
        # 1. 이미지 프롬프트 확인 및 생성
        prompts = db.get_image_prompts(project_id)
        if not prompts:
            print(f"🎨 [5/8] 이미지 프롬프트 생성 중...")
            prompts = await gemini_service.generate_image_prompts_from_script(script, 50)
            db.save_image_prompts(project_id, prompts)
            # 다시 로드하여 ID와 scene_number 등이 일관되게 보장
            prompts = db.get_image_prompts(project_id)
        else:
            print(f"🔄 [Resume] 기존 이미지 프롬프트 {len(prompts)}개를 재사용합니다.")

        # 2. 이미지 생성 (병렬 처리, 이미 있는 이미지는 스킵)
        async def process_prompt(p):
            scene_num = p.get("scene_number")
            existing_url = p.get("image_url")
            
            # 이미 파일이 있고 URL이 등록되어 있는지 확인
            if existing_url:
                fname = existing_url.split("/")[-1]
                fpath = os.path.join(config.OUTPUT_DIR, fname)
                if os.path.exists(fpath):
                    # print(f"⏭️ [Skip] 이미 생성된 이미지: Scene {scene_num}")
                    return True

            try:
                # print(f"🖼️ [Generating] 이미지 생성 중: Scene {scene_num}")
                images = await gemini_service.generate_image(p.get("prompt_en", "view"), aspect_ratio="9:16")
                if images:
                    now_kst = config.get_kst_time()
                    filename = f"auto_{project_id}_{scene_num}_{now_kst.strftime('%Y%m%d_%H%M%S')}.png"
                    output_path = os.path.join(config.OUTPUT_DIR, filename)
                    
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(images[0]))
                    image.save(output_path)
                    
                    new_url = f"/output/{filename}"
                    db.update_image_prompt_url(project_id, scene_num, new_url)
                    p['image_url'] = new_url
                    return True
            except Exception as e:
                print(f"❌ [Auto-Pilot] 이미지 생성 실패 (Scene {scene_num}): {e}")
            return False

        print(f"🎨 [5/8] 이미지 생성 상태 확인 및 작업 중...")
        # 모든 프롬프트에 대해 병렬 실행 (이미 완료된 것은 내부에서 즉시 리턴)
        tasks = [process_prompt(p) for p in prompts]
        await asyncio.gather(*tasks)

        # 3. TTS 생성
        existing_tts = db.get_tts(project_id)
        if existing_tts:
            tpath = existing_tts.get("audio_path")
            if tpath and os.path.exists(tpath):
                print(f"⏭️ [Skip] 이미 생성된 TTS 파일을 재사용합니다.")
                return

        print(f"🎙️ [5/8] TTS(Google Cloud) 생성 중...")
        filename = f"auto_tts_{project_id}.mp3"
        output_path = await tts_service.generate_google_cloud(
            text=script,
            voice_name="ko-KR-Neural2-A", # 기본 보이스
            filename=filename
        )
        
        # 길이 측정
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(output_path)
        duration = clip.duration
        clip.close()
        
        db.save_tts(project_id, "google_cloud", "auto-voice", output_path, duration)

    async def _render_video(self, project_id: int):
        """영상 렌더링 및 자막 합성 (정밀 싱크 및 단일 패스 렌더링 적용)"""
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        
        # 이미지 경로 변환
        images = []
        for img in images_data:
            if not img.get("image_url"): continue
            fname = img["image_url"].split("/")[-1]
            fpath = os.path.join(config.OUTPUT_DIR, fname)
            if os.path.exists(fpath):
                images.append(fpath)
                
        audio_path = tts_data["audio_path"]
        now_kst = config.get_kst_time()
        output_filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"

        # 1. 정밀 자막(AI Alignment) 생성
        print(f"🎙️ [6/8] AI 자막 정렬(Whisper) 진행 중...")
        subs = video_service.generate_aligned_subtitles(audio_path, script_data["full_script"])
        if not subs:
            print("⚠️ 정밀 자막 생성 실패, 기본 자막으로 전환합니다.")
            subs = video_service.generate_simple_subtitles(script_data["full_script"], tts_data["duration"])

        # 2. 이미지 듀레이션 계산 (자막 싱크에 맞춰 가변 적용)
        image_durations = []
        if subs and len(images) > 0:
            total_subs = len(subs)
            subs_per_image = max(1, total_subs // len(images))
            
            last_timestamp = 0.0
            for i in range(len(images)):
                if i == len(images) - 1:
                    dur = max(0.5, tts_data["duration"] - last_timestamp)
                else:
                    next_sub_idx = min((i + 1) * subs_per_image, total_subs - 1)
                    next_start = subs[next_sub_idx]["start"]
                    dur = max(0.5, next_start - last_timestamp)
                
                image_durations.append(dur)
                last_timestamp += dur
        else:
            image_durations = tts_data["duration"] / len(images) if len(images) > 0 else 5.0

        # 3. 통합 렌더링 (단일 패스)
        print(f"🎬 [6/8] 최종 영상 합성 및 자막 오버레이 시작...")
        final_path = video_service.create_slideshow(
            images=images,
            audio_path=audio_path,
            output_filename=output_filename,
            duration_per_image=image_durations,
            subtitles=subs,
            project_id=project_id
        )
        
        # DB 저장
        db.update_project_setting(project_id, "video_path", f"/output/{output_filename}")
        db.update_project(project_id, status="rendered")
        
        return final_path

    async def _upload_video(self, project_id: int, video_path: str):
        """유튜브 업로드 (내일 아침 8시 예약)"""
        # 예약 시간 설정 (다음날 아침 8시)
        now = config.get_kst_time()
        publish_time = now + timedelta(days=1)
        publish_time = publish_time.replace(hour=8, minute=0, second=0, microsecond=0)
        publish_at_str = publish_time.isoformat() # ISO 8601
        
        try:
            youtube_upload_service.upload_video(
                file_path=video_path,
                title=f"New Shorts Video {now.strftime('%Y-%m-%d')}",
                description="#Shorts #Auto",
                tags=["shorts", "auto"],
                privacy_status="private",
                publish_at=publish_at_str
            )
            db.update_project_setting(project_id, "is_uploaded", 1)
        except Exception as e:
            print(f"⚠️ 업로드 실패 (인증 필요 가능성): {e}")

autopilot_service = AutoPilotService()
