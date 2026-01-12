"""
MusicGen 배경음악 생성 서비스
Meta의 MusicGen AI 모델을 사용하여 텍스트 프롬프트 기반 배경음악 생성
"""
import os
import torch
import scipy.io.wavfile
import numpy as np
from typing import Optional
from config import config

class MusicService:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.output_dir = config.OUTPUT_DIR
        
    def _load_model(self):
        """MusicGen 모델 로딩 (lazy loading)"""
        if self.model is None:
            print(f"[MusicGen] Loading model on {self.device}...")
            try:
                from transformers import AutoProcessor, MusicgenForConditionalGeneration
                
                # Small 모델 사용 (빠르고 메모리 효율적)
                model_name = "facebook/musicgen-small"
                
                self.processor = AutoProcessor.from_pretrained(model_name)
                self.model = MusicgenForConditionalGeneration.from_pretrained(model_name)
                self.model.to(self.device)
                
                print(f"[MusicGen] Model loaded successfully on {self.device}")
            except Exception as e:
                print(f"[MusicGen] Model loading failed: {e}")
                raise
    
    async def generate_music(
        self,
        prompt: str,
        duration_seconds: int = 10,
        filename: str = "background_music.wav",
        project_id: Optional[int] = None
    ) -> Optional[str]:
        """
        텍스트 프롬프트로 배경음악 생성
        
        Args:
            prompt: 음악 스타일 설명 (예: "calm piano background music")
            duration_seconds: 음악 길이 (초) - 5~30초 권장
            filename: 저장할 파일명
            project_id: 프로젝트 ID (폴더 구분용)
        
        Returns:
            생성된 음악 파일 경로
        """
        try:
            # 모델 로딩
            self._load_model()
            
            # 길이 제한 (5~30초)
            duration_seconds = max(5, min(30, duration_seconds))
            
            print(f"[MusicGen] Generating music: '{prompt}' ({duration_seconds}s)")
            
            # 프롬프트 처리
            inputs = self.processor(
                text=[prompt],
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            
            # 샘플링 레이트 (MusicGen 기본값: 32kHz)
            sampling_rate = self.model.config.audio_encoder.sampling_rate
            
            # 생성할 토큰 수 계산
            # MusicGen은 초당 약 50 토큰 생성
            max_new_tokens = int(duration_seconds * 50)
            
            # 음악 생성
            print(f"[MusicGen] Generating {max_new_tokens} tokens...")
            with torch.no_grad():
                audio_values = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    guidance_scale=3.0  # 프롬프트 준수 강도
                )
            
            # CPU로 이동 및 numpy 변환
            audio_np = audio_values[0, 0].cpu().numpy()
            
            # 정규화 (16-bit PCM 범위로)
            audio_np = np.int16(audio_np / np.max(np.abs(audio_np)) * 32767)
            
            # 저장 경로 생성
            if project_id:
                save_dir = os.path.join(self.output_dir, f"project_{project_id}", "music")
            else:
                save_dir = os.path.join(self.output_dir, "music")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 파일 저장
            output_path = os.path.join(save_dir, filename)
            scipy.io.wavfile.write(output_path, rate=sampling_rate, data=audio_np)
            
            print(f"[MusicGen] Music saved to: {output_path}")
            
            return output_path
            
        except Exception as e:
            print(f"[MusicGen] Generation failed: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"음악 생성 실패: {str(e)}")
    
    def unload_model(self):
        """메모리 절약을 위한 모델 언로드"""
        if self.model is not None:
            del self.model
            del self.processor
            self.model = None
            self.processor = None
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            print("[MusicGen] Model unloaded")


# 싱글톤 인스턴스
music_service = MusicService()
