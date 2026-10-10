import os
import time
import queue
import threading
import json
import requests
import datetime

class RenderQueueWorker:
    def __init__(self):
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.current_task = None
        self._lock = threading.Lock()
        
    def start(self):
        with self._lock:
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
                self.worker_thread.start()
                print("[RenderQueueWorker] Sequential worker thread started.")
                
    def add_task(self, task_id: str, temp_dir: str, use_gpu: bool, project_id: int, project_name: str, email: str):
        task_data = {
            "task_id": task_id,
            "temp_dir": temp_dir,
            "use_gpu": use_gpu,
            "project_id": project_id,
            "project_name": project_name,
            "email": email
        }
        self.task_queue.put(task_data)
        # 즉시 Supabase pending으로 등록
        self._update_supabase_status(task_id, project_id, project_name, email, "pending", 0, "대기 중...")
        # 백그라운드 스레드 기동
        self.start()
        
    def _update_supabase_status(self, task_id: str, project_id: int, project_name: str, email: str, status: str, progress: int, message: str):
        supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_key:
            return
            
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        payload = {
            "id": task_id,
            "project_id": project_id,
            "project_name": project_name,
            "email": email,
            "status": status,
            "progress": progress,
            "message": message,
            "updated_at": datetime.datetime.now().isoformat()
        }
        if status == "completed":
            payload["completed_at"] = datetime.datetime.now().isoformat()
            
        url = f"{supabase_url.rstrip('/')}/rest/v1/remote_render_queue"
        
        # Suppress insecure request warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10, verify=False, proxies={"http": None, "https": None})
            if r.status_code not in [200, 201]:
                print(f"[RenderQueueWorker] Supabase update fail (status {r.status_code}): {r.text}")
        except Exception as e:
            print(f"[RenderQueueWorker] Supabase connection error: {e}")

    def _worker_loop(self):
        while True:
            try:
                task = self.task_queue.get(timeout=5)
            except queue.Empty:
                continue
                
            task_id = task["task_id"]
            temp_dir = task["temp_dir"]
            use_gpu = task["use_gpu"]
            project_id = task["project_id"]
            project_name = task["project_name"]
            email = task["email"]
            
            self.current_task = task
            print(f"[RenderQueueWorker] Processing remote render task {task_id} for project {project_id}")
            
            # Update status to rendering
            self._update_supabase_status(task_id, project_id, project_name, email, "rendering", 0, "렌더링 작업 시작...")
            
            progress_file = os.path.join(temp_dir, "progress.txt")
            
            # Start rendering function
            from services.remote_render_service import remote_render_executor_func
            
            # Define a tracker function
            def track_progress():
                last_progress = -1
                last_msg = ""
                while self.current_task and self.current_task["task_id"] == task_id:
                    if os.path.exists(progress_file):
                        try:
                            with open(progress_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            p = data.get("progress", 0)
                            msg = data.get("message", "")
                            if p != last_progress or msg != last_msg:
                                status = "rendering"
                                if p == -1:
                                    status = "failed"
                                elif p == 100:
                                    status = "completed"
                                    
                                self._update_supabase_status(task_id, project_id, project_name, email, status, p, msg)
                                last_progress = p
                                last_msg = msg
                                
                                if status in ["completed", "failed"]:
                                    break
                        except Exception:
                            pass
                    time.sleep(1)
            
            tracker_thread = threading.Thread(target=track_progress, daemon=True)
            tracker_thread.start()
            
            try:
                # Synchronous execution within thread
                remote_render_executor_func(task_id, temp_dir, use_gpu)
                self._update_supabase_status(task_id, project_id, project_name, email, "completed", 100, "완료")
            except Exception as e:
                print(f"[RenderQueueWorker] Render task {task_id} failed: {e}")
                self._update_supabase_status(task_id, project_id, project_name, email, "failed", -1, f"에러: {str(e)}")
            finally:
                self.current_task = None
                self.task_queue.task_done()
    
    def get_queue_status(self) -> dict:
        queue_list = []
        # Copy queue items safely
        for task in list(self.task_queue.queue):
            queue_list.append({
                "task_id": task["task_id"],
                "project_id": task["project_id"],
                "project_name": task["project_name"],
                "email": task["email"]
            })
            
        active_task = None
        if self.current_task:
            progress = 0
            message = "렌더링 중..."
            temp_dir = self.current_task.get("temp_dir")
            if temp_dir:
                progress_file = os.path.join(temp_dir, "progress.txt")
                if os.path.exists(progress_file):
                    try:
                        with open(progress_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        progress = data.get("progress", 0)
                        message = data.get("message", "렌더링 중...")
                    except Exception:
                        pass
                        
            active_task = {
                "task_id": self.current_task["task_id"],
                "project_id": self.current_task["project_id"],
                "project_name": self.current_task["project_name"],
                "email": self.current_task["email"],
                "progress": progress,
                "message": message
            }
            
        return {
            "status": "ok",
            "active": active_task,
            "queue": queue_list
        }
                
render_queue_worker = RenderQueueWorker()
