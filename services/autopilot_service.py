
import asyncio
import json
import os
import random
from datetime import datetime, timedelta
import httpx
from config import config
import database as db
from services.gemini_service import gemini_service
from services.tts_service import tts_service
from services.video_service import video_service
from services.youtube_upload_service import youtube_upload_service

class AutoPilotService:
    def __init__(self):
        self.search_url = f"{config.YOUTUBE_BASE_URL}/search"

    async def run_workflow(self, keyword: str):
        """오토파일럿 전체 워크플로우 실행"""
        print(f"🚀 [Auto-Pilot] '{keyword}' 주제로 작업 시작!")
        
        try:
            # 1. 소재 발굴 (Shorts 검색 & 선정)
            print(f"🔍 [1/8] 소재 발굴 중: {keyword}")
            video = await self._find_best_material(keyword)
            if not video:
                print("❌ 적절한 소재를 찾지 못했습니다.")
                return

            # 2. 프로젝트 생성
            project_name = f"[Auto] {keyword} - {video['snippet']['title'][:20]}"
            project_id = db.create_project(name=project_name, topic=keyword)
            print(f"✅ [2/8] 프로젝트 생성 완료: ID {project_id}")

            # 3. AI 분석 (댓글/반응)
            print(f"🧠 [3/8] AI 분석 중 (Deep Analysis)...")
            analysis_result = await self._analyze_video(video['id']['videoId'])
            db.save_analysis(project_id, video, analysis_result)
            
            # 4. 기획 및 대본 작성
            print(f"📝 [4/8] 기획 및 대본 작성 중...")
            script = await self._generate_script(project_id, analysis_result)
            db.update_project_setting(project_id, "script", script)
            
            # 5. 에셋 생성 (이미지 & 오디오)
            print(f"🎨 [5/8] 이미지 및 오디오 생성 중...")
            await self._generate_assets(project_id, script)
            
            # 6. 영상 렌더링 (자막 포함)
            print(f"🎬 [6/8] 최종 영상 렌더링 중...")
            video_path = await self._render_video(project_id)
            
            # 7. 업로드 (예약)
            print(f"📤 [7/8] 유튜브 업로드 (예약) 중...")
            await self._upload_video(project_id, video_path)
            
            print(f"✨ [Auto-Pilot] 모든 작업 완료! (Project ID: {project_id})")

        except Exception as e:
            print(f"❌ [Auto-Pilot] 오류 발생: {e}")
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
        
        prompt = f"""
        유튜브 쇼츠 영상(ID: {video_id})을 벤치마킹하여 새로운 영상을 만들려 합니다.
        대중들이 좋아할만한 '반전 매력'이나 '공감 포인트'를 3가지만 분석해서 JSON으로 주세요.
        
        JSON 포맷:
        {{
            "sentiment": "positive",
            "topics": ["topic1", "topic2"],
            "viewer_needs": "viewers want..."
        }}
        """
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
        prompt = f"""
        분석 내용: {json.dumps(analysis, ensure_ascii=False)}
        
        위 분석을 바탕으로 1분 이내의 유튜브 쇼츠 대본을 작성해줘.
        - 초반 5초에 강력한 후킹 멘트 필수
        - 구어체 사용
        - 문장은 짧게
        - 전체 길이는 300자 내외
        
        오직 대본 내용만 출력해. 설명 제외.
        """
        request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
        result = await gemini_service.generate_content(request)
        
        script = result["text"]
        # DB 저장
        db.save_script(project_id, script, len(script), 50)
        return script

    async def _generate_assets(self, project_id: int, script: str):
        """이미지 프롬프트 -> 이미지 생성 -> TTS 생성"""
        # 1. 이미지 프롬프트 생성
        prompts = await gemini_service.generate_image_prompts_from_script(script, 50)
        
        # 2. 이미지 생성 (병렬 처리 가능하지만 순차 처리)
        for p in prompts:
            # 이미지 생성
            images = await gemini_service.generate_image(p.get("prompt_en", "view"), aspect_ratio="9:16")
            if images:
                # 저장
                now_kst = config.get_kst_time()
                filename = f"auto_{project_id}_{p['scene_number']}_{now_kst.strftime('%Y%m%d_%H%M%S')}.png"
                output_path = os.path.join(config.OUTPUT_DIR, filename)
                
                # 이미지 파일 저장
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(images[0]))
                image.save(output_path)
                
                p['image_url'] = f"/output/{filename}"
                
        db.save_image_prompts(project_id, prompts)

        # 3. TTS 생성
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
        """영상 렌더링 및 자막 합성"""
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        
        # 이미지 경로 변환
        images = []
        for img in images_data:
            fname = img["image_url"].split("/")[-1]
            fpath = os.path.join(config.OUTPUT_DIR, fname)
            if os.path.exists(fpath):
                images.append(fpath)
                
        audio_path = tts_data["audio_path"]
        
        # 1. 기본 렌더링
        now_kst = config.get_kst_time()
        output_filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"
        
        video_path = video_service.create_slideshow(
            images=images,
            audio_path=audio_path,
            output_filename=f"temp_{output_filename}",
            duration_per_image=tts_data["duration"] / len(images)
        )
        
        # 2. 자막 합성
        final_path = video_path
        if script_data["full_script"]:
            subs = video_service.generate_simple_subtitles(script_data["full_script"], tts_data["duration"])
            if subs:
                final_path = video_service.add_subtitles(
                    video_path=video_path,
                    subtitles=subs,
                    output_filename=output_filename
                )
                try: os.remove(video_path)
                except: pass
        
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
