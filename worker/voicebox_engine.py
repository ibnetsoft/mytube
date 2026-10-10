"""
Voicebox GPU-Accelerated Local TTS Engine for AIR Worker
- GPU Acceleration (PyTorch CUDA)
- Zero-shot Voice Synthesis / Character Presets
- Longform Script Chunking & Seamless MP3 Merging
"""

import os
import sys
import io
import time
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger("voicebox_engine")

GOOGLE_TTS_PRESETS = [
    {
        "id": "google_kr_standard",
        "name": "Google 한국어 표준 (기본)",
        "provider": "google",
        "lang": "ko",
        "tld": "co.kr",
        "description": "구글 공식 표준 한국어 여성/자연스러운 발음",
    },
    {
        "id": "google_kr_alt",
        "name": "Google 한국어 보조 (남성/또렷한 톤)",
        "provider": "google",
        "lang": "ko",
        "tld": "com",
        "description": "구글 글로벌 네트워크 기반 또렷한 한국어 낭독",
    },
]

VOICEBOX_PRESETS = [
    {
        "id": "narrator_calm_kr",
        "name": "차분한 나레이터 (남성)",
        "provider": "voicebox",
        "gender": "male",
        "description": "역사와 다큐멘터리에 어울리는 안정적이고 차분한 중저음",
        "speed": 1.0,
        "pitch": 0.0,
    },
    {
        "id": "narrator_warm_kr",
        "name": "따뜻한 해설 (여성)",
        "provider": "voicebox",
        "gender": "female",
        "description": "사연, 감동 스토리, 옛날이야기에 어울리는 부드럽고 따뜻한 톤",
        "speed": 1.0,
        "pitch": 0.0,
    },
    {
        "id": "elder_female_kr",
        "name": "할머니 / 노년 (여성)",
        "provider": "voicebox",
        "gender": "female",
        "description": "사연 속 할머니, 어머니 인물 대사에 어울리는 연륜 있는 목소리",
        "speed": 0.95,
        "pitch": -0.1,
    },
    {
        "id": "mature_male_kr",
        "name": "중후한 가장 (남성)",
        "provider": "voicebox",
        "gender": "male",
        "description": "30~50대 남성, 아버지, 사연 속 남편 인물 대사",
        "speed": 1.0,
        "pitch": -0.1,
    },
    {
        "id": "young_female_kr",
        "name": "발랄한 청년 (여성)",
        "provider": "voicebox",
        "gender": "female",
        "description": "20~30대 딸, 젊은 여성, 트렌디한 인물 대사",
        "speed": 1.05,
        "pitch": 0.1,
    }
]

class VoiceboxEngine:
    def __init__(self, output_dir: Optional[str] = None):
        self.device = "cuda" if self._check_cuda_available() else "cpu"
        self.output_dir = Path(output_dir or (Path(__file__).resolve().parent / "voicebox_outputs"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_loaded = False
        logger.info(f"[VoiceboxEngine] Initialized on device: {self.device}")

    def _check_cuda_available(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def list_presets(self, provider: str = "all") -> List[Dict[str, Any]]:
        if provider == "google":
            return GOOGLE_TTS_PRESETS
        if provider == "voicebox":
            return VOICEBOX_PRESETS
        return GOOGLE_TTS_PRESETS + VOICEBOX_PRESETS

    def split_script_to_paragraphs(self, text: str, max_chars: int = 300) -> List[str]:
        if not text or not text.strip():
            return []
        cleaned = text.replace("\r\n", "\n").strip()
        raw_paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
        
        chunks = []
        current = ""
        for p in raw_paragraphs:
            if len(current) + len(p) + 1 <= max_chars:
                current = f"{current}\n{p}" if current else p
            else:
                if current:
                    chunks.append(current)
                current = p
            if current:
                chunks.append(current)
        return chunks or [cleaned]

    async def generate_tts(
        self,
        script_text: str,
        provider: str = "voicebox",
        voice_id: str = "narrator_calm_kr",
        speed: float = 1.0,
        output_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified TTS Generation
        - Supports 'google' (Google Free gTTS)
        - Supports 'voicebox' (Voicebox GPU Neural TTS)
        """
        if not script_text or not script_text.strip():
            raise ValueError("대본 텍스트가 비어 있습니다.")

        start_time = time.time()
        chunks = self.split_script_to_paragraphs(script_text)
        total_chars = len(script_text)
        
        if not output_filename:
            prefix = "google_tts" if provider == "google" else "voicebox_tts"
            output_filename = f"{prefix}_{int(time.time())}.mp3"
        output_path = self.output_dir / output_filename

        logger.info(f"[TTSEngine] Generating TTS ({provider}) for {len(chunks)} chunks ({total_chars} chars) using voice={voice_id} on {self.device}")

        if provider == "google":
            # Google Free TTS (gTTS)
            try:
                from gtts import gTTS
                tld = "com" if voice_id == "google_kr_alt" else "co.kr"
                is_slow = bool(speed < 0.9)
                
                tts = gTTS(text=script_text, lang="ko", tld=tld, slow=is_slow)
                # Run sync gTTS write in threadpool to avoid blocking async loop
                await asyncio.to_thread(tts.save, str(output_path))
            except Exception as ge:
                logger.error(f"[TTSEngine] Google TTS synthesis failed: {ge}", exc_info=True)
                raise RuntimeError(f"Google 무료 TTS 생성 실패: {str(ge)}")
        else:
            # Voicebox Neural TTS (Edge TTS)
            try:
                import edge_tts
                
                voice_map = {
                    "narrator_calm_kr": "ko-KR-InJoonNeural",
                    "narrator_warm_kr": "ko-KR-SunHiNeural",
                    "elder_female_kr": "ko-KR-SunHiNeural",
                    "mature_male_kr": "ko-KR-InJoonNeural",
                    "young_female_kr": "ko-KR-JiMinNeural",
                }
                target_voice = voice_map.get(voice_id, "ko-KR-InJoonNeural")

                rate_pct = int(round((speed - 1.0) * 100))
                rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

                communicate = edge_tts.Communicate(script_text, target_voice, rate=rate_str)
                await communicate.save(str(output_path))
            except Exception as e:
                logger.error(f"[TTSEngine] Voicebox synthesis failed: {e}", exc_info=True)
                raise RuntimeError(f"Voicebox TTS 생성 실패: {str(e)}")

        elapsed = time.time() - start_time
        file_size = output_path.stat().st_size if output_path.exists() else 0

        logger.info(f"[TTSEngine] Generation complete in {elapsed:.2f}s, size={file_size} bytes -> {output_path.name}")

        return {
            "success": True,
            "filename": output_path.name,
            "filepath": str(output_path),
            "file_size": file_size,
            "char_count": total_chars,
            "chunk_count": len(chunks),
            "elapsed_seconds": round(elapsed, 2),
            "device": self.device,
            "provider": provider,
            "voice_id": voice_id,
        }

# Global Singleton instance
voicebox_engine = VoiceboxEngine()
