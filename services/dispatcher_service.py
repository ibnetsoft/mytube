import os
import time
import requests
import threading
from config import config
from services.gemini_service import gemini_service
import database as db

class DispatcherService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 3600  # 1시간 간격 실행
        self.auth_server_url = os.getenv("DASHBOARD_URL", "https://mytube-ashy-seven.vercel.app")
        # Antigravity SDK 모니터링/스케줄러 상태
        self.dispatcher_lock = threading.Lock()

    def get_license_key(self):
        if os.path.exists("license.key"):
            with open("license.key", "r") as f:
                return f.read().strip()
        return None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[Dispatcher] Smart Dispatcher service started (Every 1 hour).")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self.dispatch_daily_topics()
            except Exception as e:
                print(f"[Dispatcher Error] Dispatch runner exception: {e}")
            time.sleep(self.interval)

    def dispatch_daily_topics(self):
        """[SDK] Antigravity SDK 스케줄러 기반: 트렌드 분석 후 가용 직원 자동 배정 실행"""
        if not self.dispatcher_lock.acquire(blocking=False):
            return
            
        try:
            print("[Dispatcher] Starting automated trend search & employee load matching...")
            supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                print("[Dispatcher Warning] Supabase credentials missing. Auto Dispatcher aborted.")
                return

            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json"
            }

            # 1. 원격 Supabase 카테고리 목록 읽기
            cat_res = requests.get(f"{supabase_url}/rest/v1/categories?select=*", headers=headers, timeout=10)
            if cat_res.status_code != 200:
                print(f"[Dispatcher Error] Failed to fetch remote categories: {cat_res.text}")
                return

            categories = cat_res.json()
            if not categories:
                print("[Dispatcher] No categories found for dispatching.")
                return

            # 2. 원격 Supabase 유저 프로필 및 활성 프로젝트 로드
            user_res = requests.get(f"{supabase_url}/rest/v1/profiles?select=*", headers=headers, timeout=10)
            if user_res.status_code != 200:
                print(f"[Dispatcher Error] Failed to fetch user profiles: {user_res.text}")
                return
            users = user_res.json()

            # 직원별 활성 프로젝트 수(워크로드) 구하기
            workloads = {}
            for user in users:
                email = user.get("email")
                if not email:
                    continue
                # Supabase의 topics_queue에서 현재 담당 직원이고 status가 pending 혹은 assigned인 개수 합산
                assigned_res = requests.get(f"{supabase_url}/rest/v1/topics_queue?assigned_employee_email=eq.{email}&status=eq.assigned&select=count", headers=headers, timeout=10)
                assigned_count = 0
                if assigned_res.status_code == 200:
                    try:
                        assigned_count = int(assigned_res.headers.get("content-range", "0-0/0").split("/")[-1])
                    except: pass
                
                workloads[email] = assigned_count

            # 3. 카테고리별로 무인 자동화 주제 발굴 및 배정 실행
            for category in categories:
                cat_id = category.get("id")
                cat_name = category.get("name")
                keywords = category.get("keywords") or ""
                benchmark_url = category.get("benchmark_channel_url") or ""
                target_country = category.get("target_country", "KR")
                
                # [SDK Predicates] 활성 직원의 가용성 필터링 (워크로드가 3건 미만인 최적의 직원 탐색)
                eligible_employees = [email for email, load in workloads.items() if load < 3]
                if not eligible_employees:
                    # 모든 직원이 바쁜 경우 기본 관리자 계정으로 백업 배정
                    assigned_email = category.get("assigned_employee_email") or "ejsh0519@naver.com"
                else:
                    # 가장 일이 적은(워크로드가 최솟값인) 직원을 정밀 자동 선별
                    assigned_email = min(eligible_employees, key=lambda email: workloads[email])

                print(f"[Dispatcher] Category: '{cat_name}' (Target: {target_country}) -> Assigned to: {assigned_email} (Current load: {workloads.get(assigned_email, 0)})")

                # 4. LLM을 통한 바이럴 트렌드 주제 분석 (1개씩 정교하게 실시간 생성)
                prompt = f"""
                You are Google Antigravity SDK Smart Video Planner.
                Target Country: {target_country}
                Category Name: {cat_name}
                Keywords: {keywords}
                Benchmark Reference: {benchmark_url}

                Based on these settings, please generate exactly one highly compelling, click-worthy, and trending video title or topic (Korean script style).
                
                CRITICAL INSTRUCTION:
                - The result MUST be the actual video title itself. Do not generate meta production suggestions.
                - Output only the plain title string inside a JSON object: {{"topic": "Generated Title"}}
                - Do not include markdown wraps or code fences.
                """

                # [SDK Hook fallback] API 한도나 오류 시 재시도 안전장치 적용
                topic_title = None
                for attempt in range(3):
                    try:
                        response_text = gemini_service.generate_text(prompt, model="gemini-2.0-flash", temperature=0.7)
                        import json as _json
                        # clean json wrapper
                        cleaned = response_text.replace("```json", "").replace("```", "").strip()
                        data = _json.loads(cleaned)
                        topic_title = data.get("topic")
                        if topic_title:
                            break
                    except Exception as gen_err:
                        print(f"[Dispatcher Hook] LLM Generation attempt {attempt+1} failed: {gen_err}")
                        time.sleep(5)  # 5초 간 대기 후 retry

                if not topic_title:
                    print(f"[Dispatcher Warning] Failed to generate viral topic for category '{cat_name}' after 3 attempts.")
                    continue

                # 5. 스마트 적재 실행 (is_auto_generated 활성화)
                payload = {
                    "category_id": cat_id,
                    "topic": topic_title,
                    "assigned_employee_email": assigned_email,
                    "status": "pending",
                    "is_auto_generated": True
                }

                ins_res = requests.post(f"{supabase_url}/rest/v1/topics_queue", json=payload, headers=headers, timeout=10)
                if ins_res.status_code in [200, 201]:
                    print(f"[Dispatcher Success] Dispatched topic: '{topic_title}' -> {assigned_email}")
                    # 할당자의 워크로드 가상 카운트 가중치 증가
                    workloads[assigned_email] = workloads.get(assigned_email, 0) + 1
                else:
                    print(f"[Dispatcher Error] DB insert failed for topic '{topic_title}': {ins_res.text}")

        except Exception as err:
            print(f"[Dispatcher Error] Auto dispatch system failure: {err}")
        finally:
            self.dispatcher_lock.release()

# Singleton Instance
dispatcher_service = DispatcherService()
