import os
import httpx
import json
import logging
from config import config

class TopViewService:
    def __init__(self):
        self.base_url = "https://api.topview.ai/v1"
        self.logger = logging.getLogger(__name__)

    @property
    def headers(self):
        api_key = config.TOPVIEW_API_KEY
        uid = config.TOPVIEW_UID
        if not api_key or not uid:
            return None
            
        return {
            "Authorization": f"Bearer {api_key}",
            "Topview-Uid": uid,
            "Content-Type": "application/json"
        }

    async def submit_marketing_task(self, product_url: str, product_name: str, product_desc: str, voice_id: str = "TtsVoice1780829871032872962", avatar_id: str = "AIAvatar1780521406560067586", language: str = "ko"):
        """Avatar Marketing Video 시작 (Step 1)"""
        headers = self.headers
        if not headers:
            self.logger.error("TopView API Key or UID is missing")
            return None

        url = f"{self.base_url}/m2v/task/submit"
        
        # 기본 30-50초 길이
        payload = {
            "productName": product_name,
            "productDescription": product_desc,
            "aspectRatio": "9:16",
            "language": language,
            "voiceId": voice_id,
            "aiavatarId": avatar_id,
            "videoLengthType": 1
        }
        
        if product_url:
            payload["productLink"] = product_url

        async with httpx.AsyncClient() as client:
            try:
                self.logger.info(f"TopView Submit Task: {payload}")
                response = await client.post(url, json=payload, headers=headers, timeout=60)
                result = response.json()
                
                if response.status_code == 200 and result.get("code") == 0:
                    return result.get("data", {}) # {"taskId": "...", ...}
                else:
                    self.logger.error(f"TopView API Error (Submit): {response.status_code} - {response.text}")
                    return None
            except Exception as e:
                self.logger.error(f"TopView API Connection Error: {e}")
                return None

    async def query_task_status(self, task_id: str):
        """작업 상태 확인 (Step 2)"""
        headers = self.headers
        if not headers:
            return None

        url = f"{self.base_url}/m2v/task/query?taskId={task_id}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 0:
                        return result.get("data", {})
                self.logger.error(f"TopView Query Error: {response.status_code} - {response.text}")
                return None
            except Exception as e:
                self.logger.error(f"TopView Status Check Error: {e}")
                return None

    async def update_task_script(self, task_id: str, script_id: str, custom_text: str):
        """스크립트 업데이트 (Step 3)"""
        headers = self.headers
        if not headers:
            return None
            
        url = f"{self.base_url}/m2v/script/update"
        
        # 1. 문서 조회 필요 (List Script Content 활용 가능)
        # 지금은 전체를 통으로 덮어쓸 용도이므로 간단하게 첫번째 세그먼트를 시도
        # 실제로는 먼저 List Script API를 호출하여 구조를 받아와야 할 수 있음.
        
        try:
            # 먼저 스크립트 리스트 가져오기
            list_url = f"{self.base_url}/m2v/script/list?taskId={task_id}"
            async with httpx.AsyncClient() as client:
                res_list = await client.get(list_url, headers=headers)
                list_data = res_list.json().get("data", [])
                
                if not list_data or "scriptContents" not in list_data[0]:
                    self.logger.error("Cannot fetch original script for updating.")
                    return False
                    
                target_script = list_data[0]
                target_script_id = target_script.get("scriptId")
                first_seg_id = target_script.get("scriptContents", [])[0].get("segId")
                
                if not first_seg_id:
                    return False

                payload = {
                    "taskId": task_id,
                    "scriptId": target_script_id,
                    "scriptContents": [
                        {
                            "segId": first_seg_id,
                            "segText": custom_text
                        }
                    ]
                }
                
                response = await client.post(url, json=payload, headers=headers, timeout=60)
                if response.status_code == 200 and response.json().get("code") == 0:
                    return True
                return False
        except Exception as e:
            self.logger.error(f"TopView Update Script Error: {e}")
            return False

    async def export_task(self, task_id: str):
        """최종 영상 내보내기 (Step 4)"""
        headers = self.headers
        if not headers:
            return None
            
        url = f"{self.base_url}/m2v/task/export"
        payload = {"taskId": task_id}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=60)
                result = response.json()
                if response.status_code == 200 and result.get("code") == 0:
                    return True
                self.logger.error(f"TopView Export Error: {response.text}")
                return False
            except Exception as e:
                self.logger.error(f"TopView Export Connection Error: {e}")
                return False

topview_service = TopViewService()
