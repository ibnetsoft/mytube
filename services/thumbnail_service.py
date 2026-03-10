from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import textwrap

class ThumbnailRenderer:
    def __init__(self, static_dir="static"):
        self.static_dir = static_dir
        self.fonts_dir = os.path.join(static_dir, "fonts")

        # 스타일별 폰트 맵핑 - NotoSansKR-Bold.ttf 통일 사용
        # GmarketSansTTFBold.ttf는 공백 글리프 누락으로 두부(⊠) 발생 → 사용 금지
        self.font_map = {
            "face": "NotoSansKR-Bold.ttf",
            "text": "NotoSansKR-Bold.ttf",
            "contrast": "NotoSansKR-Bold.ttf",
            "mystery": "NotoSansKR-Bold.ttf",
            "minimal": "NotoSansKR-Bold.ttf",
            "dramatic": "NotoSansKR-Bold.ttf",
            "japanese_viral": "NotoSansKR-Bold.ttf",
            "ghibli": "NotoSansKR-Bold.ttf",
            "wimpy": "NotoSansKR-Bold.ttf"
        }

        # 시스템 폰트 폴백 (Windows)
        self.system_font_fallbacks = [
            "malgunbd.ttf",   # 맑은 고딕 Bold (Windows)
            "malgun.ttf",     # 맑은 고딕 (Windows)
            "arial.ttf",
        ]

    def get_style_recipe(self, style_key: str, hook_text: str = "") -> list:
        """
        스타일 키에 따른 텍스트 레이어 구성을 반환합니다.
        좌표는 비율(0~1)로 저장하여 실제 이미지 크기에 맞게 스케일링합니다.
        """
        # Default Layer (Fallback)
        base_layer = {
            "text": hook_text or "텍스트 입력",
            "x_ratio": 0.5, "y_ratio": 0.5,  # 비율 기반 좌표
            "font_size_ratio": 0.078,  # 캔버스 높이 대비 비율 (100/1280 ≈ 0.078)
            "color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width_ratio": 0.006,  # 높이 대비 비율
            "font_family": "face"
        }

        layers = [base_layer]

        if style_key == "japanese_viral":
            layers = [
               {"text": "충격적인", "x_ratio": 0.25, "y_ratio": 0.25, "font_size_ratio": 0.063, "color": "#00FF00", "stroke_color": "#000000", "stroke_width_ratio": 0.006, "font_family": "japanese_viral"},
               {"text": hook_text or "진실", "x_ratio": 0.25, "y_ratio": 0.40, "font_size_ratio": 0.078, "color": "#00FFFF", "stroke_color": "#000000", "stroke_width_ratio": 0.008, "font_family": "japanese_viral"},
               {"text": "공개", "x_ratio": 0.25, "y_ratio": 0.58, "font_size_ratio": 0.063, "color": "#E000FF", "stroke_color": "#FFFFFF", "stroke_width_ratio": 0.006, "font_family": "japanese_viral"},
               {"text": "!!", "x_ratio": 0.25, "y_ratio": 0.75, "font_size_ratio": 0.094, "color": "#FF0000", "stroke_color": "#FFFF00", "stroke_width_ratio": 0.008, "font_family": "japanese_viral"},
            ]

        elif style_key == "face":
            layers[0].update({
                "y_ratio": 0.83,
                "font_size_ratio": 0.086,
                "color": "#FFFFFF",
                "stroke_width_ratio": 0.008,
                "font_family": "face"
            })

        elif style_key == "text":
            layers[0].update({
                "x_ratio": 0.5, "y_ratio": 0.5,
                "font_size_ratio": 0.117,
                "color": "#FFFF00",
                "stroke_color": "#000000",
                "stroke_width_ratio": 0.012,
                "font_family": "text"
            })

        elif style_key == "mystery":
            layers[0].update({
                "color": "#ADFF2F",
                "font_size_ratio": 0.070,
                "stroke_width_ratio": 0.005,
                "font_family": "mystery"
            })

        elif style_key == "contrast":
            layers[0].update({
                "color": "#FFFFFF",
                "stroke_color": "#FF0000",
                "stroke_width_ratio": 0.006,
                "font_family": "contrast"
            })

        elif style_key == "dramatic":
            layers[0].update({
                "color": "#FF0000",
                "stroke_color": "#000000",
                "stroke_width_ratio": 0.008,
                "font_family": "dramatic"
            })

        elif style_key == "minimal":
             layers[0].update({
                "color": "#000000",
                "stroke_color": "#FFFFFF",
                "stroke_width_ratio": 0.003,
                "font_size_ratio": 0.063,
                "font_family": "minimal"
             })

        elif style_key == "ghibli":
             layers[0].update({
                 "font_family": "ghibli",
                 "font_size_ratio": 0.070,
                 "stroke_width_ratio": 0.003,
                 "stroke_color": "#555555"
             })

        elif style_key == "wimpy":
             layers[0].update({
                 "font_family": "wimpy",
                 "color": "#000000",
                 "stroke_width_ratio": 0
             })

        return layers

    def _load_font(self, font_name, size):
        """폰트 로드 - static/fonts → 시스템 폰트 순서로 폴백"""
        # 1. static/fonts/ 에서 시도
        font_path = os.path.join(self.fonts_dir, font_name)
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

        # 2. 시스템 폰트 폴백 (한글 지원 폰트 우선)
        for fallback in self.system_font_fallbacks:
            try:
                return ImageFont.truetype(fallback, size)
            except Exception:
                continue

        print(f"[Thumbnail] WARNING: No Korean font available for '{font_name}', using default bitmap font")
        return ImageFont.load_default()

    def _wrap_text(self, text, font, max_width, draw):
        """텍스트가 max_width를 넘으면 줄바꿈하여 리스트로 반환"""
        # 짧은 텍스트는 바로 반환
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return [text]

        # 한글은 글자 단위로 줄바꿈 처리
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if (bbox[2] - bbox[0]) > max_width and current_line:
                lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        return lines

    def create_thumbnail(self, background_path, text_layers, output_path):
        """배경 이미지 위에 텍스트 레이어들을 합성하여 저장"""
        # 1. 배경 로드
        try:
            if not os.path.exists(background_path) and background_path.startswith("/"):
                background_path = background_path.lstrip("/")

            base_img = Image.open(background_path).convert("RGBA")
        except Exception as e:
            print(f"[Thumbnail] Failed to load background: {e}")
            return False

        width, height = base_img.size
        draw = ImageDraw.Draw(base_img)

        # 2. 텍스트 레이어 합성
        for layer in text_layers:
            text = layer.get("text", "")
            if not text:
                continue

            color = layer.get("color", "#FFFFFF")
            stroke_color = layer.get("stroke_color", "#000000")
            font_family = layer.get("font_family", "text")

            # 비율 기반 좌표 → 픽셀 변환 (ratio 키가 있으면 비율, 없으면 legacy 절대값)
            if "font_size_ratio" in layer:
                font_size = max(20, int(layer["font_size_ratio"] * height))
                stroke_width = max(0, int(layer.get("stroke_width_ratio", 0) * height))
                x = layer.get("x_ratio", 0.5) * width
                y = layer.get("y_ratio", 0.5) * height
            else:
                # Legacy 절대 좌표 (1280x720 기준) → 실제 이미지 크기로 스케일링
                font_size = int(layer.get("font_size", 80) * (height / 720))
                stroke_width = int(layer.get("stroke_width", 0) * (height / 720))
                x = layer.get("x", width / 2) * (width / 1280)
                y = layer.get("y", height / 2) * (height / 720)

            # 폰트 로드
            ttf_name = self.font_map.get(font_family, "GmarketSansTTFBold.ttf")
            font = self._load_font(ttf_name, font_size)

            # 텍스트 줄바꿈 (캔버스 폭의 90%까지 허용)
            max_text_width = int(width * 0.90)
            lines = self._wrap_text(text, font, max_text_width, draw)

            # 줄 높이 계산
            line_height = font_size * 1.2
            total_text_height = line_height * len(lines)

            # 각 줄 그리기 (중앙 정렬)
            start_y = y - (total_text_height / 2)
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_w = bbox[2] - bbox[0]
                line_x = x - (text_w / 2)
                line_y = start_y + (i * line_height)

                # 캔버스 밖으로 나가지 않도록 클램핑
                line_x = max(5, min(line_x, width - text_w - 5))
                line_y = max(5, min(line_y, height - font_size - 5))

                draw.text((line_x, line_y), line, font=font, fill=color,
                          stroke_width=stroke_width, stroke_fill=stroke_color)

            print(f"[Thumbnail] Drew '{text}' ({len(lines)} lines) with font {ttf_name} size={font_size}")

        # 3. 저장
        try:
            final_img = base_img.convert("RGB")
            final_img.save(output_path, quality=95)
            print(f"[Thumbnail] Saved to {output_path}")
            return True
        except Exception as e:
            print(f"[Thumbnail] Failed to save: {e}")
            return False

thumbnail_service = ThumbnailRenderer()
