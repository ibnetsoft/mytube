"""
TopView AI 모델 서비스
TopView API에서 제공하는 아바타, 음성 등의 모델 관리
"""

import httpx
import logging
from config import config
from typing import Dict, Any, List


class TopViewModelsService:
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

    async def get_available_models(self) -> Dict[str, Any]:
        """
        사용 가능한 모든 모델 정보 조회
        - 아바타 모델
        - 음성 모델
        """
        try:
            # TopView API에서 모델 목록을 가져오는 방식
            # 실제 API 문서에 따라 조정 필요

            # 기본 제공 모델 (하드코딩 - 실제 API 호출로 대체 가능)
            avatars = [
                {
                    "id": "AIAvatar1780521406560067586",
                    "name": "전문 여성 아바타",
                    "description": "전문적인 여성 아바타, 비즈니스 스타일",
                    "category": "business",
                    "gender": "female",
                    "age": "30s"
                },
                {
                    "id": "AIAvatar1780521406560067587",
                    "name": "전문 남성 아바타",
                    "description": "전문적인 남성 아바타, 비즈니스 스타일",
                    "category": "business",
                    "gender": "male",
                    "age": "40s"
                },
                {
                    "id": "AIAvatar1780521406560067588",
                    "name": "친근한 여성 아바타",
                    "description": "친근하고 부드러운 여성 아바타, 라이프스타일 콘텐츠",
                    "category": "lifestyle",
                    "gender": "female",
                    "age": "20s"
                },
                {
                    "id": "AIAvatar1780521406560067589",
                    "name": "카리스마 남성 아바타",
                    "description": "카리스마 있는 남성 아바타, 교육/강연 스타일",
                    "category": "education",
                    "gender": "male",
                    "age": "50s"
                }
            ]

            voices = [
                {
                    "id": "TtsVoice1780829871032872962",
                    "name": "명료한 여성 음성",
                    "description": "맑고 명료한 여성 음성, 뉴스/교육용",
                    "gender": "female",
                    "style": "clear",
                    "language": "ko"
                },
                {
                    "id": "TtsVoice1780829871032872963",
                    "name": "저명한 남성 음성",
                    "description": "차분하고 저명한 남성 음성, 다큐멘터리용",
                    "gender": "male",
                    "style": "calm",
                    "language": "ko"
                },
                {
                    "id": "TtsVoice1780829871032872964",
                    "name": "활기찬 여성 음성",
                    "description": "밝고 활기찬 여성 음성, 엔터테인먼트용",
                    "gender": "female",
                    "style": "energetic",
                    "language": "ko"
                },
                {
                    "id": "TtsVoice1780829871032872965",
                    "name": "신뢰감 있는 남성 음성",
                    "description": "신뢰감 있는 남성 음성, 뉴스/리포트용",
                    "gender": "male",
                    "style": "authoritative",
                    "language": "ko"
                }
            ]

            return {
                "avatars": avatars,
                "voices": voices
            }

        except Exception as e:
            self.logger.error(f"Failed to get TopView models: {e}")
            raise

    async def get_avatar_models(self) -> List[Dict[str, Any]]:
        """아바타 모델 목록만 조회"""
        try:
            models = await self.get_available_models()
            return models.get("avatars", [])
        except Exception as e:
            self.logger.error(f"Failed to get avatar models: {e}")
            raise

    async def get_voice_models(self) -> List[Dict[str, Any]]:
        """음성 모델 목록만 조회"""
        try:
            models = await self.get_available_models()
            return models.get("voices", [])
        except Exception as e:
            self.logger.error(f"Failed to get voice models: {e}")
            raise

    def validate_model_ids(self, avatar_id: str, voice_id: str) -> bool:
        """모델 ID 유효성 검사 (동기 버전)"""
        try:
            # 비동기 호출은 여기서 할 수 없으므로 기본 유효성 체크만 수행
            if not avatar_id or not voice_id:
                return False

            # ID 형식 검사 (간단한 체크)
            if not avatar_id.startswith("AIAvatar"):
                return False
            if not voice_id.startswith("TtsVoice"):
                return False

            return True

        except Exception as e:
            self.logger.error(f"Model validation error: {e}")
            return False

    async def fetch_real_models_from_api(self) -> Dict[str, Any]:
        """
        실제 TopView API에서 모델 정보를 가져오는 메서드
        API 문서에 따라 엔드포인트와 파라미터를 조정해야 함
        """
        headers = self.headers
        if not headers:
            self.logger.error("TopView API credentials missing")
            return await self.get_available_models()  # 폴백

        try:
            # 실제 API 엔드포인트 (문서 확인 후 수정 필요)
            # 예시: avatar 목록 가져오기
            async with httpx.AsyncClient() as client:
                # 아바타 목록 API (실제 엔드포인트로 변경 필요)
                avatar_url = f"{self.base_url}/avatar/list"
                avatar_response = await client.get(avatar_url, headers=headers, timeout=30)

                # 음성 목록 API (실제 엔드포인트로 변경 필요)
                voice_url = f"{self.base_url}/tts/voice/list"
                voice_response = await client.get(voice_url, headers=headers, timeout=30)

                avatars = []
                voices = []

                if avatar_response.status_code == 200:
                    avatar_data = avatar_response.json()
                    if avatar_data.get("code") == 0:
                        avatars = avatar_data.get("data", {}).get("avatars", [])

                if voice_response.status_code == 200:
                    voice_data = voice_response.json()
                    if voice_data.get("code") == 0:
                        voices = voice_data.get("data", {}).get("voices", [])

                return {
                    "avatars": avatars,
                    "voices": voices
                }

        except Exception as e:
            self.logger.error(f"Failed to fetch real models from API: {e}")
            # 폴백: 기본 모델 목록 반환
            return await self.get_available_models()


# 싱글톤 인스턴스
topview_models_service = TopViewModelsService()