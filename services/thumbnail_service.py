from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import textwrap

class ThumbnailRenderer:
    def __init__(self, static_dir="static"):
        self.static_dir = static_dir
        self.fonts_dir = os.path.join(static_dir, "fonts")
        
        # 기본 폰트 설정 (폰트 파일이 없으면 기본값 사용)
        self.default_font = "arial.ttf"
        
        # 스타일별 폰트 맵핑 (TTF 파일 이름)
        self.font_map = {
            "face": "Recipekorea.ttf",
            "text": "GmarketSansBold.ttf",
            "contrast": "GmarketSansBold.ttf",
            "mystery": "GmarketSansMedium.ttf",
            "minimal": "NanumGothic.ttf",
            "dramatic": "Recipekorea.ttf",
            "japanese_viral": "GmarketSansBold.ttf", # GHS.ttf
            "ghibli": "NanumPen.ttf",
            "wimpy": "NanumPen.ttf"
        }

    def _load_font(self, font_name, size):
        """폰트 로드 (실패시 기본 폰트)"""
        font_path = os.path.join(self.fonts_dir, font_name)
        try:
            return ImageFont.truetype(font_path, size)
        except:
            print(f"[Thumbnail] Font not found: {font_name}, utilizing default.")
            try:
                return ImageFont.truetype("arial.ttf", size)
            except:
                return ImageFont.load_default()

    def create_thumbnail(self, background_path, text_layers, output_path):
        """
        배경 이미지 위에 텍스트 레이어들을 합성하여 저장
        """
        # 1. 배경 로드
        try:
            # 절대 경로 보정
            if not os.path.exists(background_path) and background_path.startswith("/"):
                # web absolute path -> local file path
                background_path = background_path.lstrip("/")
            
            base_img = Image.open(background_path).convert("RGBA")
        except Exception as e:
            print(f"[Thumbnail] Failed to load background: {e}")
            return False

        # Canvas 크기 (보통 1280x720)
        width, height = base_img.size
        
        # Drawing Context
        draw = ImageDraw.Draw(base_img)

        # 2. 텍스트 레이어 합성
        for layer in text_layers:
            text = layer.get("text", "")
            if not text: continue
            
            # 스타일 속성
            color = layer.get("color", "#FFFFFF")
            stroke_color = layer.get("stroke_color", "#000000")
            stroke_width = int(layer.get("stroke_width", 0))
            font_family = layer.get("font_family", "GmarketSansBold")
            font_size = int(layer.get("font_size", 80))
            
            # 위치 (JS의 x, y는 캔버스 기준 상대/절대값일 수 있음. 여기선 단순화)
            # 저장된 데이터가 {x: 640, y: 360, align: 'center'} 형식이면 좋지만
            # 현재 프론트엔드 로직에 맞춰야 함.
            # 일단 중앙 정렬 기본으로 가정
            
            # 폰트 로드 (매핑 확인)
            ttf_name = self.font_map.get(font_family, "GmarketSansBold.ttf") # Default fallback map
            # 실제 파일명이 다를 수 있으므로 검색 로직 필요할 수도 있음
            # 여기서는 매핑된 이름을 신뢰
            
            font = self._load_font(ttf_name, font_size)
            
            # 텍스트 크기 계산
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # 위치 결정 
            # layer['x'], layer['y']가 있으면 사용, 없으면 중앙
            x = layer.get("x", width / 2)
            y = layer.get("y", height / 2)
            
            # Anchor Point 보정 (중앙 기준이면)
            # HTML Canvas transform(-50%, -50%) 로직을 시뮬레이션
            x = x - (text_w / 2)
            y = y - (text_h / 2)

            # 외곽선 (Stroke) - PIL은 stroke_width 파라미터 지원 (Pillow 4.2+)
            # 외곽선 (Stroke) - PIL은 stroke_width 파라미터 지원 (Pillow 4.2+)
            # PIL requires stroke_fill, stroke_width
            draw.text((x, y), text, font=font, fill=color, 
                      stroke_width=stroke_width, stroke_fill=stroke_color) 
            print(f"[Thumbnail] Drew text '{text}' at ({x},{y}) with font {ttf_name}")

        # 3. 저장
        try:
            # RGB로 변환 (JPG 저장 위함)
            final_img = base_img.convert("RGB")
            final_img.save(output_path, quality=95)
            print(f"[Thumbnail] Saved to {output_path}")
            return True
        except Exception as e:
            print(f"[Thumbnail] Failed to save: {e}")
            return False

thumbnail_service = ThumbnailRenderer()
