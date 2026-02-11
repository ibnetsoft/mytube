
import os
import httpx
import json
import logging
from config import config

class TopViewService:
    def __init__(self):
        self.api_key = config.TOPVIEW_API_KEY
        self.base_url = "https://api.topview.ai/v1" # Hypothesized base URL based on common patterns
        self.logger = logging.getLogger(__name__)

    async def create_video_by_url(self, product_url: str):
        """URL을 이용한 비디오 생성 요청 (URL-to-Video)"""
        if not self.api_key:
            self.logger.error("TopView API Key is missing")
            return None

        url = f"{self.base_url}/video/create-by-url" # Example endpoint
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "url": product_url,
            "aspect_ratio": "9:16"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=60)
                if response.status_code == 200:
                    return response.json() # { "id": "task_id", ... }
                else:
                    self.logger.error(f"TopView API Error: {response.status_code} - {response.text}")
                    return None
            except Exception as e:
                self.logger.error(f"TopView API Connection Error: {e}")
                return None

    async def get_task_status(self, task_id: str):
        """비디오 생성 상태 확인"""
        if not self.api_key:
            return None

        url = f"{self.base_url}/video/status/{task_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                self.logger.error(f"TopView Status Check Error: {e}")
                return None

topview_service = TopViewService()
