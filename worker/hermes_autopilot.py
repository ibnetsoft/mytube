import sys
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from worker_config import ensure_project_root_on_path
ensure_project_root_on_path()

import asyncio
import json
import os
import time
import httpx
import traceback
from datetime import datetime

import job_store
from worker_config import STATE_DIR, OUTPUT_DIR
import logging
from services import ai_router

logger = logging.getLogger("hermes_autopilot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

STATE_FILE = STATE_DIR / "hermes_autopilot_state.json"
RESULTS_DIR = OUTPUT_DIR / "hermes_autopilot_results"

CATEGORIES = [
    "탈북사연",
    "해외감동",
    "노후금융",
    "황혼19금",
    "옛날이야기",
    "한국사연",
    "무협",
    "경제"
]

class HermesAutopilotManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(HermesAutopilotManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.is_running = False
        self.current_step = "idle"
        self.current_category = ""
        self.current_topic = ""
        self.logs = []
        self.loop_task = None
        
        # 신규 설정 및 통계 기본값
        self.settings = {
            "mode": "infinite",
            "target_limit": 10,
            "min_buffer_per_category": 5,
            "active_categories": CATEGORIES.copy()
        }
        self.session_stats = {
            "generated_count": 0
        }
        
        self.initialized = True
        self._load_state()

    def _load_state(self):
        """Loads state from local JSON storage if exists."""
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.is_running = data.get("is_running", False)
                self.current_step = data.get("current_step", "idle")
                self.current_category = data.get("current_category", "")
                self.current_topic = data.get("current_topic", "")
                self.logs = data.get("logs", [])
                
                # settings 로드
                loaded_settings = data.get("settings", {})
                if loaded_settings:
                    # 리스트 인스턴스 복사 누락 보완
                    for k, v in loaded_settings.items():
                        if k in self.settings:
                            self.settings[k] = v
                
                # stats 로드
                loaded_stats = data.get("session_stats", {})
                if loaded_stats:
                    self.session_stats.update(loaded_stats)
                
                # If it crashed/restarted while running, reset running flag gracefully
                if self.is_running:
                    self.is_running = False
                    self.add_log("시스템 재시작으로 인해 오토파일럿이 중단되었습니다. 대기 상태로 전환합니다.")
                    self._save_state()
            except Exception as e:
                logger.warning(f"Failed to load autopilot state: {e}")

    def _save_state(self):
        """Saves current state to local JSON storage."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "is_running": self.is_running,
                "current_step": self.current_step,
                "current_category": self.current_category,
                "current_topic": self.current_topic,
                "logs": self.logs[-200:],  # keep last 200 logs
                "settings": self.settings,
                "session_stats": self.session_stats,
                "updated_at": time.time()
            }
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save autopilot state: {e}")

    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 300:
            self.logs = self.logs[-200:]
        logger.info(message)
        self._save_state()

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "current_step": self.current_step,
            "current_category": self.current_category,
            "current_topic": self.current_topic,
            "logs": self.logs,
            "settings": self.settings,
            "session_stats": self.session_stats
        }

    async def start(self, custom_settings: dict = None):
        async with self._lock:
            if self.is_running:
                return {"success": False, "error": "이미 실행 중입니다."}
            
            if custom_settings:
                for k, v in custom_settings.items():
                    if k in self.settings:
                        self.settings[k] = v
            
            self.session_stats["generated_count"] = 0
            self.is_running = True
            self.current_step = "initializing"
            self.add_log("Hermes 자동 생성기(Autopilot) 시작 요청됨.")
            self.add_log(f"적용 설정: 모드={self.settings['mode']}, 제한량={self.settings['target_limit']}개, 최소유지량={self.settings['min_buffer_per_category']}개, 활성카테고리={len(self.settings['active_categories'])}개")
            
            self.loop_task = asyncio.create_task(self._run_loop())
            self._save_state()
            return {"success": True}

    async def save_settings(self, new_settings: dict):
        async with self._lock:
            for k, v in new_settings.items():
                if k in self.settings:
                    self.settings[k] = v
            self._save_state()
            return {"success": True}

    async def stop(self):
        async with self._lock:
            if not self.is_running:
                return {"success": False, "error": "실행 중이 아닙니다."}
            
            self.is_running = False
            self.add_log("오토파일럿 중지 요청됨. 현재 진행 중인 스텝이 끝나는 대로 정지합니다.")
            if self.loop_task:
                self.loop_task.cancel()
            self.current_step = "stopped"
            self.current_category = ""
            self.current_topic = ""
            self._save_state()
            return {"success": True}

    async def _run_loop(self):
        try:
            self.add_log("오토파일럿 백그라운드 태스크가 성공적으로 기동되었습니다.")
            idx = 0
            
            while self.is_running:
                category = CATEGORIES[idx % len(CATEGORIES)]
                idx += 1
                
                # 활성 카테고리 체크
                active_cats = self.settings.get("active_categories", CATEGORIES)
                if category not in active_cats:
                    logger.info(f"카테고리 '{category}'는 설정에서 비활성화되어 있어 스킵합니다.")
                    await asyncio.sleep(0.5)
                    continue
                
                self.current_category = category
                self.current_step = f"[{category}] 유튜브 탐색 준비"
                self.add_log(f"==================================================")
                self.add_log(f"카테고리 '{category}'의 생성 루프 시작")
                
                try:
                    await self._process_category(category)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.add_log(f"❌ 카테고리 '{category}' 처리 중 에러 발생: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(5.0)  # 에러 발생 시 잠시 대기
                
                # 다음 카테고리 시작 전 짧은 간격
                await asyncio.sleep(3.0)

        except asyncio.CancelledError:
            self.add_log("오토파일럿 루프가 취소되었습니다. 정지 완료.")
        finally:
            self.is_running = False
            self.current_step = "stopped"
            self._save_state()

    async def _process_category(self, category: str):
        # 0. Supabase URL 및 키 읽기
        supabase_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        
        # categories 테이블에서 ID 확인 시도
        category_id = None
        if supabase_url and supabase_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        f"{supabase_url}/rest/v1/categories?select=id,name",
                        headers=headers
                    )
                    if r.status_code == 200:
                        cats = r.json()
                        for c in cats:
                            if c.get("name") == category:
                                category_id = c.get("id")
                                break
            except Exception as e:
                self.add_log(f"Supabase 카테고리 ID 조회 실패 (무시): {e}")

        # [신규] 카테고리별 최소 대기주제 유지량(min_buffer_per_category) 검사
        if supabase_url and supabase_key and category_id:
            try:
                min_buffer = self.settings.get("min_buffer_per_category", 5)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # status=pending 이고 pregenerated_script_status=ready 인 대본 개수 확인
                    r = await client.get(
                        f"{supabase_url}/rest/v1/topics_queue?select=id&category_id=eq.{category_id}&status=eq.pending&pregenerated_script_status=eq.ready",
                        headers=headers
                    )
                    if r.status_code == 200:
                        existing_pregens = r.json()
                        if len(existing_pregens) >= min_buffer:
                            self.add_log(f"📋 '{category}' 카테고리는 이미 대기 중인 대본이 {len(existing_pregens)}개 존재합니다. (설정 유지량: {min_buffer}개)")
                            self.add_log("목표 개수를 충족하여 생성을 생략합니다.")
                            return
            except Exception as e:
                self.add_log(f"Supabase 대기주제 개수 조회 실패 (무시하고 진행): {e}")

        # 1. Supabase topics_queue에 행 선점 생성
        topic_queue_id = None
        if supabase_url and supabase_key:
            self.current_step = "Supabase 큐 등록"
            self.add_log("Supabase topics_queue에 임시 행 생성 요청 중...")
            
            row_data = {
                "topic": f"{category}",
                "assigned_employee_email": "hermes_worker@local",
                "language": "ko",
                "status": "pending",
                "is_auto_generated": True,
                "pregenerated_structure_status": "queued",
                "pregenerated_script_status": "queued"
            }
            if category_id:
                row_data["category_id"] = category_id

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(
                        f"{supabase_url}/rest/v1/topics_queue",
                        headers={**headers, "Prefer": "return=representation"},
                        json=row_data
                    )
                    if r.status_code in (200, 201):
                        resp_data = r.json()
                        if isinstance(resp_data, list) and len(resp_data) > 0:
                            topic_queue_id = resp_data[0].get("id")
                        elif isinstance(resp_data, dict):
                            topic_queue_id = resp_data.get("id")
                        
                        if topic_queue_id:
                            self.add_log(f"Supabase topics_queue ID 할당 성공: {topic_queue_id}")
                        else:
                            self.add_log("Supabase insert는 성공했으나 ID 획득 실패. 로컬 테스트로 계속 진행.")
                    else:
                        self.add_log(f"Supabase 큐 생성 실패 (Status Code={r.status_code}): {r.text[:200]}")
            except Exception as e:
                self.add_log(f"Supabase 큐 생성 중 통신 실패: {e}")

        # 임시 topic_queue_id 부여 (Supabase 연동 안 되었거나 실패했을 때)
        if not topic_queue_id:
            topic_queue_id = f"local-auto-{int(time.time())}"
            self.add_log(f"Supabase 연동 생략 또는 실패로 임시 로컬 ID 사용: {topic_queue_id}")

        # 2. 유튜브 탐색 및 분석 실행
        self.current_step = "유튜브 탐색 및 고성과 분석"
        self.add_log(f"유튜브에서 '{category}' 관련 인기 영상 탐색 시작...")
        
        benchmark_job_id = job_store.submit_job(
            job_type="topic_benchmark_analyze",
            payload={
                "keyword": category,
                "language": "ko",
                "video_type": "longform",
                "max_candidates": 1,
                "topic_queue_id": topic_queue_id
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> topic_benchmark_analyze 작업 제출 완료 (Job ID: {benchmark_job_id})")
        
        # 작업 완료 대기
        await self._wait_for_job(benchmark_job_id)
        
        # 결과 읽기
        result_data = self._read_result_file(benchmark_job_id)
        if not result_data or "candidates" not in result_data or not result_data["candidates"]:
            raise RuntimeError("유튜브 벤치마크 탐색 결과 분석 데이터가 유효하지 않습니다.")
            
        candidates = result_data["candidates"]
        best_candidate = candidates[0]
        video_title = best_candidate.get("title", "")
        performance_ratio = best_candidate.get("performance_ratio", 0.0)
        self.add_log(f"📈 벤치마크 탐색 완료. 대상 비디오: '{video_title}' (구독자 대비 조회수 {performance_ratio}배)")

        # Supabase에 벤치마크 정보 업데이트
        if supabase_url and supabase_key and isinstance(topic_queue_id, int):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={"benchmark_analysis": best_candidate}
                    )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 벤치마크 분석 데이터 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 벤치마크 분석 동기화 실패: {e}")

        # 3. AI 기반 새로운 영상 제목(주제) 도출
        self.current_step = "신규 오리지널 영상 주제 도출"
        self.add_log("학습된 벤치마크 분석 내용을 토대로 신규 유튜브 제목 기획 중...")
        
        prompt = (
            f"You are a professional YouTube producer creating highly engaging Korean videos.\n"
            f"We analyzed a highly successful video for category: {category}.\n"
            f"Original video title: {video_title}\n"
            f"Benchmark analysis results: {json.dumps(best_candidate.get('analysis', {}), ensure_ascii=False)}\n"
            f"Success strategies extracted: {json.dumps(best_candidate.get('success_strategies', []), ensure_ascii=False)}\n\n"
            f"Based on this successful pattern, generate ONE highly attractive, natural, and clickable Korean video title/topic.\n"
            f"CRITICAL GUIDELINES:\n"
            f"- Output ONLY the final title, no description, no quotes, no markdown.\n"
            f"- It must be a natural, actual YouTube title that Korean viewers would eagerly click to watch the story.\n"
            f"- NEVER use awkward report-like structures, and NEVER write meta-analysis keywords like '스토리텔링 비결', '연출 공식', '해부', '분석', '성공적인 연출'.\n"
            f"- It must read like an actual story or documentary title (e.g., '평생을 숨겨온 할머니의 눈물겨운 탈북 사연', '단돈 5만원으로 노후 준비를 완전히 끝내버린 남자의 비결').\n"
            f"- Do not copy the original title directly. Create a fresh angle suitable for this category."
        )
        
        from config import config as app_config
        model = app_config.TOPIC_GENERATION_MODEL or "gemini-2.5-flash"
        
        new_topic = await ai_router.generate_text(
            prompt, model=model, temperature=0.9, max_tokens=1000,
            task_type="hermes_autopilot_title_gen"
        )
        new_topic = new_topic.strip().replace('"', '').replace("'", "")
        self.current_topic = new_topic
        self.add_log(f"✨ AI 기획 신규 오리지널 주제: '{new_topic}'")

        # Supabase에 신규 기획 주제 업데이트
        if supabase_url and supabase_key and isinstance(topic_queue_id, int):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={"topic": new_topic}
                    )
                    if r.status_code in (200, 204):
                        self.add_log(f"Supabase: 신규 주제명 '{new_topic}' 업데이트 완료")
            except Exception as e:
                self.add_log(f"Supabase 주제명 동기화 실패: {e}")

        # 4. 구조 및 씬 기획 생성
        self.current_step = "대본 구조 및 씬 기획"
        self.add_log(f"주제 '{new_topic}'에 대한 씬 구조(Scene Plan) 생성 시작...")
        
        plan_job_id = job_store.submit_job(
            job_type="script_plan_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "topic": new_topic,
                "target_duration_seconds": 600,
                "script_style": "default",
                "language": "ko",
                "benchmark_analysis": best_candidate
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> script_plan_generate 작업 제출 완료 (Job ID: {plan_job_id})")
        
        await self._wait_for_job(plan_job_id)
        
        plan_data = self._read_result_file(plan_job_id)
        if not plan_data or "structure" not in plan_data:
            raise RuntimeError("대본 구조 생성 데이터가 유효하지 않습니다.")
            
        structure = plan_data["structure"]
        scene_count = structure.get("scene_count", 0)
        self.add_log(f"📋 대본 구조 기획 성공. 총 {scene_count}개 씬 분할")

        # Supabase에 구조 동기화
        if supabase_url and supabase_key and isinstance(topic_queue_id, int):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "pregenerated_structure": structure,
                            "pregenerated_structure_status": "ready",
                            "total_scenes": scene_count
                        }
                    )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 구조 및 상태 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 대본 구조 동기화 실패: {e}")

        # 5. 최종 대본 텍스트 생성
        self.current_step = "나레이션 대본 집필"
        self.add_log(f"씬 구조를 바탕으로 나레이션 본문 생성 중...")
        
        script_job_id = job_store.submit_job(
            job_type="script_generate",
            payload={
                "topic_queue_id": topic_queue_id,
                "topic": new_topic,
                "structure": structure,
                "target_duration_seconds": 600,
                "script_style": "default",
                "language": "ko",
                "narration_mode": "single"
            },
            priority=100,
            source="autopilot"
        )
        self.add_log(f"-> script_generate 작업 제출 완료 (Job ID: {script_job_id})")
        
        await self._wait_for_job(script_job_id)
        
        script_data = self._read_result_file(script_job_id)
        if not script_data or "script" not in script_data:
            raise RuntimeError("대본 생성 본문 데이터가 유효하지 않습니다.")
            
        final_script = script_data["script"]
        char_count = len(final_script)
        self.add_log(f"✍️ 최종 대본 집필 완료 (총 글자수: {char_count}자)")

        # Supabase에 최종 대본 동기화 및 큐 완료 처리
        if supabase_url and supabase_key and isinstance(topic_queue_id, int):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.patch(
                        f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_queue_id}",
                        headers={**headers, "Prefer": "return=minimal"},
                        json={
                            "pregenerated_script": final_script,
                            "pregenerated_script_status": "ready",
                            "status": "pending"
                        }
                    )
                    if r.status_code in (200, 204):
                        self.add_log("Supabase: 대본 본문 및 상태(completed) 동기화 완료")
            except Exception as e:
                self.add_log(f"Supabase 대본 본문 동기화 실패: {e}")

        # 6. 로컬에 종합 최종 결과물 저장
        self.current_step = "로컬 저장 완료"
        self.add_log("종합 데이터를 로컬 결과 디렉토리에 백업 중...")
        
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        local_result_path = RESULTS_DIR / f"{topic_queue_id}.json"
        
        summary_payload = {
            "topic_queue_id": topic_queue_id,
            "category": category,
            "original_benchmark_title": video_title,
            "performance_ratio": performance_ratio,
            "benchmark_analysis": best_candidate,
            "generated_topic": new_topic,
            "structure": structure,
            "script": final_script,
            "char_count": char_count,
            "completed_at": time.time()
        }
        
        local_result_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.add_log(f"💾 로컬 백업 완료: {local_result_path}")
        self.add_log(f"🎉 '{category}' 카테고리의 1회차 자동 생성 완료!")

        # 세션 통계 및 목표 도달 점검
        self.session_stats["generated_count"] += 1
        self._save_state()
        
        mode = self.settings.get("mode", "infinite")
        limit = self.settings.get("target_limit", 10)
        generated = self.session_stats["generated_count"]
        
        if mode == "target_limit" and generated >= limit:
            self.add_log(f"🏁 설정된 목표 생성 총량({limit}개)에 도달했습니다. (현재 생성량: {generated}개)")
            self.is_running = False
            self.current_step = "stopped"
            self._save_state()

    async def _wait_for_job(self, job_id: str):
        """Waits until the job state is COMPLETED, FAILED or CANCELED."""
        self.add_log(f"작업({job_id}) 처리 대기 시작...")
        
        while self.is_running:
            job = job_store.get_job(job_id)
            if not job:
                raise RuntimeError(f"작업({job_id})을 job_store에서 찾을 수 없습니다.")
                
            status = job.get("status")
            progress = job.get("progress", 0)
            progress_msg = job.get("progress_message", "")
            
            if status == "COMPLETED":
                self.add_log(f"작업 완료: {job_id}")
                return
            elif status in ("FAILED", "CANCELED"):
                err_msg = job.get("error_message") or "알 수 없는 에러"
                raise RuntimeError(f"작업({job_id})이 실패/취소되었습니다. 상태: {status}, 원인: {err_msg}")
                
            # 진행 상태 로그 노출
            step_desc = f"진행률 {progress}%"
            if progress_msg:
                step_desc += f" ({progress_msg})"
            self.current_step = f"Hermes 작업 처리 중 ({step_desc})"
            
            await asyncio.sleep(3.0)
            
        # 루프가 정지된 경우 취소 에러 발생
        raise asyncio.CancelledError()

    def _read_result_file(self, job_id: str) -> dict | None:
        """Reads result JSON file from hermes_results folder."""
        result_path = OUTPUT_DIR / "hermes_results" / f"{job_id}.json"
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to read result file {result_path}: {e}")
        return None
