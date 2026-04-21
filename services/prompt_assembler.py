import yaml
import json
from typing import List, Dict, Any, Optional
from services.negative_prompt_engine import negative_engine

class PromptAssembler:
    """
    피카디리 프롬프트 지침 보강안 - 지침 1-5 (프롬프트 조립 순서) 구현체
    6개 블록 고정 순서로 프롬프트를 조립합니다.
    """
    
    def assemble_scene_prompt(
        self, 
        style_prefix: str,
        character_dnas: List[Dict[str, Any]], 
        scene_context: Dict[str, Any],
        cinematic_tags: str = "cinematic lighting, high resolution, 8k",
        aspect_ratio: str = "9:16",
        seed: int = -1,
        model_type: str = "sdxl",
        global_ethnicity: Optional[str] = None
    ) -> Dict[str, str]:
        """
        [BLOCK 1~6] 조립 및 최종 프롬프트 세트 반환
        """
        
        # --- BLOCK 1: STYLE ---
        block1 = style_prefix.strip()
        
        # --- BLOCK 2: CHARACTER DNA ---
        dna_blocks = []
        for char in character_dnas:
            dna_text = self._format_dna_block(char)
            if dna_text:
                if global_ethnicity and global_ethnicity.lower() not in dna_text.lower():
                    dna_text = f"{global_ethnicity}, {dna_text}"
                dna_blocks.append(dna_text)
        block2 = " ".join(dna_blocks)
        
        # If no characters but global ethnicity exists, inject it near style
        if not block2 and global_ethnicity:
            block1 = f"{block1}, {global_ethnicity}"
        
        # --- BLOCK 3: SCENE CONTEXT ---
        # action, expression, location, time, weather, props
        ctx_parts = []
        for key in ["action", "expression", "location", "time", "weather", "props"]:
            val = scene_context.get(key)
            if val:
                ctx_parts.append(val)
        block3 = ", ".join(ctx_parts)
        
        # --- BLOCK 4: CINEMATIC FINISH ---
        block4 = cinematic_tags.strip()
        
        # --- BLOCK 5: NEGATIVE (Phase 1 엔진 호출) ---
        scene_type = scene_context.get("scene_type", "Mixed")
        # style_prefix에서 스타일 키워드 매칭 (간이 처리)
        style_key = self._detect_style_key(style_prefix)
        block5 = negative_engine.build_negative_prompt(scene_type, style_key, model_type)
        
        # --- BLOCK 6: TECHNICAL ---
        block6 = f"--ar {aspect_ratio}" if model_type == "mj" else f"aspect ratio {aspect_ratio}"
        if seed is not None and str(seed) != "-1":
            block6 += f", seed {seed}"

        # 최종 조립 (Block 5는 별도 필드로 분리)
        # Block 1~4, 6 순서로 텍스트 생성
        positive_prompt = f"{block1}, {block2}, {block3}, {block4}, {block6}"
        
        # 쉼표 중복 정제
        positive_prompt = self._cleanup_commas(positive_prompt)

        return {
            "prompt_en": positive_prompt,
            "negative_prompt": block5,
            "seed": seed
        }

    def _format_dna_block(self, char_data: Dict[str, Any]) -> str:
        """
        YAML DNA를 프롬프트용 텍스트로 변환
        지침 1-3: 불변 속성 서술
        """
        dna_yaml_str = char_data.get("dna_yaml", "")
        if not dna_yaml_str:
            return char_data.get("prompt_en", "") # 백업용

        try:
            dna = yaml.safe_load(dna_yaml_str)
            immutable = dna.get("immutable", {})
            
            # DNA 속성들을 하나의 서술로 병합
            dna_tokens = []
            for key, val in immutable.items():
                if val:
                    dna_tokens.append(str(val))
            
            # 현재 선택된 wardrobe 적용
            wardrobe = dna.get("wardrobe_sets", [{}])[0] # 기본 첫 번째 세트
            for key in ["top", "bottom", "accessories"]:
                val = wardrobe.get(key)
                if val:
                    dna_tokens.append(val)
            
            return f"{char_data.get('character_id', 'character')}: " + ", ".join(dna_tokens)
        except Exception:
            return char_data.get("prompt_en", "")

    def _detect_style_key(self, style_prefix: str) -> str:
        """prefix에서 NEGATIVE_LAYERS용 키워드 감지"""
        style_prefix = style_prefix.lower()
        if "anime" in style_prefix: return "Anime"
        if "webtoon" in style_prefix or "manhwa" in style_prefix: return "Webtoon"
        if "render" in style_prefix or "cgi" in style_prefix: return "3DRender"
        if "sketch" in style_prefix or "hand-drawn" in style_prefix: return "Sketch"
        return "Cinematic"

    def _cleanup_commas(self, text: str) -> str:
        """연속된 쉼표나 공백 정제"""
        text = re.sub(r',\s*,', ',', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip().strip(',')

import re
prompt_assembler = PromptAssembler()
