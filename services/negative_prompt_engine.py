import re
from typing import List, Optional
try:
    from services.prompts import prompts
except ImportError:
    # 테스트 환경이나 순환 참조 방지용 예외 처리
    class MockPrompts:
        NEGATIVE_LAYERS = {
            "BASE": "blurry, bad quality",
            "SAFETY": "nudity, violence",
            "SCENE_TYPE": {"Portrait": "distorted face", "Environment": "warped perspective", "Action": "stiff pose"},
            "STYLE_EXCLUSION": {"Cinematic": "cartoon", "Anime": "photorealistic"}
        }
    prompts = MockPrompts()

class NegativePromptEngine:
    """
    피카디리 프롬프트 지침 보강안 - 지침 2 (네거티브 프롬프트) 구현체
    """
    def __init__(self):
        self.layers = getattr(prompts, 'NEGATIVE_LAYERS', {})

    def build_negative_prompt(self, scene_type: str = "Mixed", style: str = "Cinematic", model_type: str = "sdxl") -> str:
        """
        4층 레이어 구조 (Base, Safety, Scene, Style Exclusion) 병합 및 모델별 문법 변환
        """
        if not self.layers:
            return ""

        # Layer 1 & 2: 필수 레이어
        base = self.layers.get("BASE", "")
        safety = self.layers.get("SAFETY", "")
        
        layers_to_merge = [base, safety]
        
        # Layer 3: 씬 타입별 선택
        st_dict = self.layers.get("SCENE_TYPE", {})
        if scene_type == "Mixed":
            # Mixed는 Portrait와 Environment의 핵심 토큰 병합
            p = st_dict.get("Portrait", "")
            e = st_dict.get("Environment", "")
            layers_to_merge.append(p)
            layers_to_merge.append(e)
        else:
            layers_to_merge.append(st_dict.get(scene_type, ""))
            
        # Layer 4: 스타일 배제 (반대 속성 차단)
        style_ex = self.layers.get("STYLE_EXCLUSION", {}).get(style, "")
        layers_to_merge.append(style_ex)
        
        # 병합 및 정제
        merged_text = ", ".join([l for l in layers_to_merge if l])
        cleaned_text = self._cleanup_tokens(merged_text)
        
        # 모델별 문법 대응
        return self._format_for_model(cleaned_text, model_type)

    def _cleanup_tokens(self, text: str) -> str:
        """중복 토큰 제거 및 소문자 정규화"""
        # 불필요한 공백 및 대소문자 제거
        tokens = [t.strip().lower() for t in text.split(',') if t.strip()]
        
        # 순서 유지 중복 제거
        seen = set()
        deduped = []
        for t in tokens:
            if t not in seen:
                deduped.append(t)
                seen.add(t)
        
        return ", ".join(deduped)

    def _format_for_model(self, text: str, model: str) -> str:
        """모델별 네거티브 문법 대응표 반영"""
        model = model.lower()
        
        if model == "mj":
            # Midjourney: --no 키워드 사용. 컴마를 공백으로 변환
            return f"--no {text.replace(', ', ' ')}"
        
        elif model in ["dalle", "veo", "imagen"]:
            # 지원하지 않는 모델은 빈 문자열 (포지티브 프롬프트 말미 보강 방식으로 대체 권장)
            return ""
        
        # Flux, SDXL, Stable Diffusion 등 표준 방식
        return text

    def get_alternative_positive_suffix(self) -> str:
        """네거티브 미지원 모델용 대체 포지티브 접미사"""
        return "clean professional composition, anatomically correct with five fingers per hand and symmetric facial features, single coherent lighting source, no visible text or watermarks, original character design, natural proportions, high quality rendering"

negative_engine = NegativePromptEngine()
