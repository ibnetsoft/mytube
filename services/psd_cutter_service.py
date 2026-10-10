"""
psd_cutter_service.py
PSD / PNG 이미지를 분석하여 컷(장면) 단위로 자동 분할하고 PNG로 저장하는 서비스.

처리 케이스:
  Case A. 긴 이미지 (세로로 긴, 여백 또는 캐릭터 기준) → 수평 분할 → 여러 PNG
  Case B. 흰 배경 위 네모 컷 배열 → 박스 감지 후 개별 crop
  Case C. 9:16 초과 통 이미지 (여백/컷 구분 없음) → 그대로 저장

v2 추가:
  - 가로형 컷 자동 감지 + Pan 모션 힌트 반환
  - 사다리꼴(기울어진 경계선) 감지 후 내부 콘텐츠 bbox로 정제
"""

import os
import re
import cv2
import numpy as np
from PIL import Image
from typing import List, Dict, Optional, Tuple


# ── 유틸: PIL ↔ OpenCV 변환 ───────────────────────────────────────────────
def _pil_to_cv(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _cv_to_pil(arr: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ── PSD → PIL 변환 (레이어 제외 지원) ────────────────────────────────────
def _normalize_layer_name(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize('NFKC', str(s))
    return "".join(c for c in s if not c.isspace() and ord(c) > 31).lower()


def _load_image_from_path(
    file_path: str,
    exclude_layers: Optional[List[str]] = None,
) -> Image.Image:
    """
    PSD 또는 일반 이미지를 PIL Image로 로드합니다.
    exclude_layers: PSD에서 숨길 레이어 키워드 목록 (정규화된 소문자) - 부분 일치
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".psd":
        from psd_tools import PSDImage
        psd = PSDImage.open(file_path)

        # 레이어 제외 처리
        if exclude_layers:
            keywords = [_normalize_layer_name(k) for k in exclude_layers if k.strip()]
            hidden_count = 0
            for layer in psd.descendants():
                if not layer.name:
                    continue
                name_norm = _normalize_layer_name(layer.name)
                if any(kw in name_norm for kw in keywords) and layer.visible:
                    layer.visible = False
                    if hasattr(layer, 'descendants'):
                        for child in layer.descendants():
                            child.visible = False
                    hidden_count += 1
            if hidden_count:
                print(f"[PSDCutter] Hidden {hidden_count} layers matching {keywords}")

        composite = psd.composite()
        if composite is None:
            canvas = Image.new("RGBA", psd.size, (255, 255, 255, 255))
            for layer in psd:
                if layer.visible:
                    try:
                        l_img = layer.composite()
                        if l_img:
                            canvas.alpha_composite(l_img.convert("RGBA"))
                    except Exception:
                        pass
            composite = canvas

        return composite.convert("RGB")
    else:
        return Image.open(file_path).convert("RGB")


# ══════════════════════════════════════════════════════════════════════════
# A. 가로형 컷 감지 + Pan 모션 힌트
# ══════════════════════════════════════════════════════════════════════════

def _detect_motion_hint(img: Image.Image) -> str:
    """
    컷 이미지의 가로/세로 비율을 분석하여 영상 모션 힌트를 반환합니다.

    - 가로형 (width > height × 1.2): 'pan_right' 또는 'pan_left'
    - 세로형 (높이가 더 긴): 'pan_up' (롱스트립) 또는 'zoom_in'
    - 정방형에 가까운: 'zoom_in'
    """
    w, h = img.size
    ratio = w / h  # > 1 이면 가로형

    if ratio >= 1.5:
        # 매우 가로형: 명확한 Pan
        return "pan_right"
    elif ratio >= 1.1:
        # 약간 가로형
        return "pan_right"
    elif ratio <= 0.5:
        # 세로 통 이미지 (롱스트립)
        return "pan_up"
    else:
        # 세로형 일반 컷
        return "zoom_in"


def _is_landscape(img: Image.Image, threshold: float = 1.1) -> bool:
    """컷이 가로형인지 여부."""
    w, h = img.size
    return (w / h) >= threshold


# ══════════════════════════════════════════════════════════════════════════
# B. 사다리꼴(사선 경계) 감지 및 컨텐츠 정제
# ══════════════════════════════════════════════════════════════════════════

def _detect_dominant_lines(gray: np.ndarray, min_line_ratio: float = 0.25) -> List[Tuple]:
    """
    Hough Line Transform으로 지배적인 직선을 감지합니다.
    Returns: [(x1,y1,x2,y2,angle_deg), ...]
    """
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 30, 100, apertureSize=3)

    min_length = min(w, h) * min_line_ratio
    lines_raw = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=60,
        minLineLength=int(min_length),
        maxLineGap=20
    )

    if lines_raw is None:
        return []

    results = []
    for line in lines_raw:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0:
            angle = 90.0
        else:
            angle = float(np.degrees(np.arctan2(dy, dx))) % 180.0
        results.append((x1, y1, x2, y2, angle))
    return results


def _has_angled_border(gray: np.ndarray, angle_tolerance: float = 12.0) -> bool:
    """
    이미지 경계 근처에 사선이 있는지 감지합니다.
    angle_tolerance: 수평/수직에서 몇 도 이상 기울어야 사선으로 인정
    """
    h, w = gray.shape
    lines = _detect_dominant_lines(gray, min_line_ratio=0.2)
    if not lines:
        return False

    for x1, y1, x2, y2, angle in lines:
        dist_from_horiz = min(angle, 180 - angle)       # 0° 에서 거리
        dist_from_vert = abs(90 - angle)                 # 90° 에서 거리
        is_angled = dist_from_horiz > angle_tolerance and dist_from_vert > angle_tolerance

        if not is_angled:
            continue

        # 경계 근처 (이미지 가장자리 20% 이내)에 있는 사선만 사다리꼴 경계로 간주
        near_border = (
            min(x1, x2) < w * 0.25 or max(x1, x2) > w * 0.75
            or min(y1, y2) < h * 0.25 or max(y1, y2) > h * 0.75
        )
        if near_border:
            return True

    return False


def _refine_angled_cut(img: Image.Image) -> Tuple[Image.Image, bool]:
    """
    사다리꼴 경계선이 있는 컷에서 실제 콘텐츠 bbox를 찾아 정제 crop합니다.

    Returns:
        (refined_image, was_refined: bool)
    """
    arr_rgb = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    if not _has_angled_border(gray):
        return img, False

    # ── 방법: 밝은 배경(흰색) 또는 어두운 테두리를 마스킹하여 콘텐츠 영역 찾기
    # 1) 밝은 영역(250 이상) = 배경
    bg_mask = (gray >= 250).astype(np.uint8) * 255

    # 2) 어두운 border line (0~30)
    border_mask = (gray <= 30).astype(np.uint8) * 255

    # 3) 콘텐츠 = 배경도 아니고 border도 아닌 영역
    content_mask = cv2.bitwise_not(cv2.bitwise_or(bg_mask, border_mask))

    # 노이즈 제거
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    content_clean = cv2.morphologyEx(content_mask, cv2.MORPH_OPEN, kernel)
    content_clean = cv2.dilate(content_clean, kernel, iterations=3)

    contours, _ = cv2.findContours(content_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img, False

    # 가장 큰 컨투어 = 주 콘텐츠 영역
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    # 면적이 너무 작으면 무시
    if area < (w * h * 0.15):
        return img, False

    x, y, bw, bh = cv2.boundingRect(largest)

    # 여백 추가
    margin = 6
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(w, x + bw + margin)
    y2 = min(h, y + bh + margin)

    # 원본과 비교해서 의미있는 변화가 있을 때만 crop
    crop_significant = (x1 > w * 0.04 or y1 > h * 0.04
                        or x2 < w * 0.96 or y2 < h * 0.96)
    if not crop_significant:
        return img, False

    refined = img.crop((x1, y1, x2, y2))
    print(f"[PSDCutter] Angled border refined: ({w}x{h}) → ({refined.width}x{refined.height})")
    return refined, True


# ══════════════════════════════════════════════════════════════════════════
# 기존 공통 함수들
# ══════════════════════════════════════════════════════════════════════════

def _detect_case(img: Image.Image, gray: np.ndarray) -> str:
    """
    이미지 유형을 판별합니다.
    Returns: 'grid_cuts' | 'overlay_cuts' | 'tall_solid' | 'long_strip'
    """
    h, w = gray.shape
    ratio = w / h

    bg_mean = float(np.mean(gray[0:20, :]))
    bg_mean_side = float(np.mean(gray[:, 0:10]))
    is_white_bg = bg_mean > 220 and bg_mean_side > 220

    if is_white_bg:
        _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(binary, kernel, iterations=3)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = (w * h) * 0.03
        valid = [c for c in contours if cv2.contourArea(c) > min_area]
        if len(valid) >= 2:
            return "grid_cuts"

    # ── overlay_cuts 감지 ──────────────────────────────────────────────────
    # 상단 일부에 흰 영역(네모 컷 포함)이 있고 나머지는 컬러 이미지인 경우
    # 패턴: 상단 ~40% 내에서 흰 배경 + 작은 네모 컷, 나머지는 dense colored
    if _detect_overlay_cuts(gray, h, w):
        return "overlay_cuts"

    if ratio < 0.65:
        return "tall_solid"

    return "long_strip"


def _detect_overlay_cuts(gray: np.ndarray, h: int, w: int) -> bool:
    """
    큰 이미지 위에 작은 네모 컷이 얹혀있는 overlay 패턴을 감지합니다.

    조건:
    - 상단 영역(최대 50%)에 흰 배경 + 불투명한 컬러 블록이 존재
    - 하단 영역은 전체가 컬러(colored content)
    """
    # 상단 40% 확인
    top_h = int(h * 0.50)
    top_region = gray[:top_h, :]
    bottom_region = gray[top_h:, :]

    # 상단: 흰 픽셀이 20% 이상 + 어두운 컬러 픽셀도 존재 (네모 컷)
    top_white = float(np.mean(top_region > 240))
    top_dark = float(np.mean(top_region < 200))

    # 하단: 대부분 컬러 (흰 픽셀 거의 없음)
    bottom_white = float(np.mean(bottom_region > 240))

    has_white_top = top_white > 0.15        # 상단에 흰 영역 존재
    has_content_top = top_dark > 0.05      # 상단에 컨텐츠도 존재
    is_solid_bottom = bottom_white < 0.15  # 하단은 컬러

    if has_white_top and has_content_top and is_solid_bottom:
        # 추가 확인: 상단 흰 영역을 이용해 컨투어들이 있는지
        _, binary = cv2.threshold(top_region, 240, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (6, 6))
        dilated = cv2.dilate(binary, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = (w * top_h) * 0.02
        valid = [c for c in contours if cv2.contourArea(c) > min_area]
        if len(valid) >= 1:
            return True

    return False


def _find_overlay_cuts(img: Image.Image, img_cv: np.ndarray, gray: np.ndarray) -> List[Image.Image]:
    """
    overlay_cuts 패턴에서 컷들을 추출합니다.

    전략:
    1. 상단 흰 배경 영역에서 작은 네모 컷들을 각각 crop
    2. 상단 흰 영역 아래부터 이미지 끝까지를 메인 컷으로 저장
    """
    h, w = gray.shape
    cuts = []

    # ── 단계 1: 상단 흰 영역 내 네모 컷 감지 ──────────────────────────────
    # 흰 배경이 끝나는 y 위치 탐색 (row_mean이 처음으로 낮아지는 지점)
    row_means = np.mean(gray, axis=1)
    white_end_y = h  # 기본값
    for y in range(int(h * 0.5), -1, -1):
        if row_means[y] > 235:
            white_end_y = y + 1
            break

    # 상단 흰 영역에서 컨투어 기반 네모 컷 추출
    top_region_gray = gray[:white_end_y, :]
    top_region_cv = img_cv[:white_end_y, :]

    _, binary = cv2.threshold(top_region_gray, 230, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    dilated = cv2.dilate(closed, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = (w * white_end_y) * 0.015
    small_cuts = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        margin = 3
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(w, x + bw + margin)
        y2 = min(white_end_y, y + bh + margin)
        crop_cv = top_region_cv[y1:y2, x1:x2]
        small_cuts.append((y1, crop_cv))

    small_cuts.sort(key=lambda t: t[0])

    for _, crop_cv in small_cuts:
        cuts.append(_cv_to_pil(crop_cv))

    # ── 단계 2: 흰 영역이 끝나는 y부터 전체 이미지를 메인 컷으로 ──────────
    # 단, 완전 흰 행만 skip하고 컨텐츠 시작 y를 찾기
    content_start_y = 0
    for y in range(white_end_y):
        if row_means[y] < 235:
            content_start_y = y
            break

    # 메인 컷: content_start_y 부터 끝까지
    if white_end_y < h:
        main_cut = img.crop((0, content_start_y, w, h))
        cuts.append(main_cut)
    else:
        # fallback: 전체
        cuts.append(img)

    print(f"[PSDCutter] overlay_cuts → small: {len(small_cuts)}개, main: 1개")
    return cuts


def _find_horizontal_split_points(gray: np.ndarray, min_blank_px: int = 20) -> List[tuple]:
    """수평 여백(흰/검) 라인 기준 분할 구간 반환."""
    h, w = gray.shape
    row_stds = np.std(gray, axis=1)
    row_means = np.mean(gray, axis=1)
    is_blank = (row_stds < 6) & ((row_means > 235) | (row_means < 15))

    blank_runs = []
    run_start = -1
    for y in range(h):
        if is_blank[y]:
            if run_start == -1:
                run_start = y
        else:
            if run_start != -1:
                if y - run_start >= min_blank_px:
                    blank_runs.append((run_start, y))
                run_start = -1
    if run_start != -1 and h - run_start >= min_blank_px:
        blank_runs.append((run_start, h))

    if not blank_runs:
        return [(0, h)]

    ranges = []
    last_y = 0
    for s, e in blank_runs:
        if s - last_y > 80:
            ranges.append((last_y, s))
        last_y = e
    if h - last_y > 80:
        ranges.append((last_y, h))

    return ranges if ranges else [(0, h)]


def _find_grid_cuts(img_cv: np.ndarray, gray: np.ndarray) -> List[np.ndarray]:
    """흰 배경 위 네모 컷들 감지."""
    h, w = gray.shape
    _, binary = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    dilated = cv2.dilate(closed, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = (w * h) * 0.02
    cuts = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        margin = 4
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(w, x + bw + margin)
        y2 = min(h, y + bh + margin)
        crop = img_cv[y1:y2, x1:x2]
        cuts.append((y1, crop))

    cuts.sort(key=lambda x: x[0])
    return [c for _, c in cuts]


def _remove_side_letterbox(img: Image.Image) -> Image.Image:
    """좌우 균일한 흰/검 여백 제거."""
    arr = np.array(img.convert("L"))
    h, w = arr.shape
    col_stds = np.std(arr, axis=0)
    col_means = np.mean(arr, axis=0)
    is_blank_col = (col_stds < 6) & ((col_means > 235) | (col_means < 15))

    left = 0
    right = w
    for x in range(w):
        if not is_blank_col[x]:
            left = x
            break
    for x in range(w - 1, -1, -1):
        if not is_blank_col[x]:
            right = x + 1
            break

    if right - left < w * 0.5:
        return img
    return img.crop((left, 0, right, h))


# ══════════════════════════════════════════════════════════════════════════
# 컷 후처리: 레터박스 제거 + 사선 정제 + 모션 힌트
# ══════════════════════════════════════════════════════════════════════════

def _postprocess_cut(img: Image.Image) -> Tuple[Image.Image, str, bool]:
    """
    개별 컷에 대해:
      1. 좌우 레터박스 제거
      2. 사다리꼴 사선 경계 정제 (가능한 경우)
      3. 가로/세로 비율 분석 → 모션 힌트 반환

    Returns:
        (processed_image, motion_hint, is_landscape)
    """
    # 1. 좌우 레터박스 제거
    img = _remove_side_letterbox(img)

    # 2. 사선 경계 정제
    img, _ = _refine_angled_cut(img)

    # 3. 모션 힌트
    hint = _detect_motion_hint(img)
    landscape = _is_landscape(img)

    return img, hint, landscape


# ══════════════════════════════════════════════════════════════════════════
# 메인 추출 함수
# ══════════════════════════════════════════════════════════════════════════

def extract_cuts(
    file_path: str,
    output_dir: str,
    file_prefix: str = "cut",
    start_idx: int = 1,
    psd_exclude_layer: Optional[str] = None,
) -> List[Dict]:
    """
    단일 파일에서 컷을 추출하여 output_dir에 PNG로 저장합니다.

    psd_exclude_layer: 쉼표/공백 구분 키워드 (예: '식자, 대사')

    Returns:
        [{"path", "filename", "width", "height", "case",
          "motion_hint", "landscape"}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)

    # 제외 레이어 키워드 파싱
    exclude_list: Optional[List[str]] = None
    if psd_exclude_layer and psd_exclude_layer.strip():
        exclude_list = [
            k.strip() for k in re.split(r'[,，\s\n]+', psd_exclude_layer)
            if k.strip()
        ]

    # 이미지 로드
    try:
        img = _load_image_from_path(file_path, exclude_layers=exclude_list)
    except Exception as e:
        print(f"[PSDCutter] Load error ({file_path}): {e}")
        return []

    img_cv = _pil_to_cv(img)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    detected_case = _detect_case(img, gray)
    print(f"[PSDCutter] {os.path.basename(file_path)} → Case: {detected_case}")

    results = []
    idx = start_idx

    def _save_cut(cut_img: Image.Image, case_tag: str) -> Optional[Dict]:
        nonlocal idx
        processed, motion_hint, landscape = _postprocess_cut(cut_img)
        if processed.width < 50 or processed.height < 50:
            return None
        fname = f"{file_prefix}_{idx:03d}.png"
        out_path = os.path.join(output_dir, fname)
        processed.save(out_path, "PNG")
        idx += 1
        info = {
            "path": out_path,
            "filename": fname,
            "width": processed.width,
            "height": processed.height,
            "case": case_tag,
            "motion_hint": motion_hint,
            "landscape": landscape,
        }
        if landscape:
            print(f"[PSDCutter]   ↳ Landscape detected → motion hint: {motion_hint}")
        return info

    # Case B: 흰배경 + 네모 컷
    if detected_case == "grid_cuts":
        cut_images = _find_grid_cuts(img_cv, gray)
        if len(cut_images) >= 2:
            for cut_cv in cut_images:
                cut_pil = _cv_to_pil(cut_cv)
                info = _save_cut(cut_pil, "grid_cuts")
                if info:
                    results.append(info)
            if results:
                return results

    # Case D: overlay_cuts — 큰 이미지 위에 작은 네모 컷이 얹혀있는 패턴
    if detected_case == "overlay_cuts":
        overlay_imgs = _find_overlay_cuts(img, img_cv, gray)
        for cut_pil in overlay_imgs:
            info = _save_cut(cut_pil, "overlay_cuts")
            if info:
                results.append(info)
        if results:
            return results

    # Case A: 수평 여백 기반 분할
    if detected_case in ("tall_solid", "grid_cuts"):
        ranges = _find_horizontal_split_points(gray, min_blank_px=15)
        if len(ranges) > 1:
            for (y0, y1) in ranges:
                cut_pil = img.crop((0, y0, img.width, y1))
                info = _save_cut(cut_pil, "horizontal_split")
                if info:
                    results.append(info)
            if results:
                return results

    # Case C (fallback): 통 이미지
    info = _save_cut(img, "long_strip")
    if info:
        results.append(info)
    return results


# ══════════════════════════════════════════════════════════════════════════
# 폴더 전체 처리
# ══════════════════════════════════════════════════════════════════════════

def extract_cuts_from_folder(
    input_dir: str,
    output_dir: str,
    psd_exclude_layer: Optional[str] = None,
) -> Dict:
    """
    폴더 내 모든 PSD/PNG/JPG 파일을 순서대로 처리하여 컷을 추출합니다.

    Returns:
        {
          "output_dir": str,
          "total_files": int,
          "total_cuts": int,
          "landscape_cuts": int,
          "results": [{"source": str, "cuts": [...]}],
          "errors": [str],
        }
    """
    valid_exts = {".psd", ".png", ".jpg", ".jpeg", ".webp"}
    files = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in valid_exts
        and os.path.isfile(os.path.join(input_dir, f))
    ])

    os.makedirs(output_dir, exist_ok=True)

    all_results = []
    errors = []

    for fname in files:
        fpath = os.path.join(input_dir, fname)
        stem = os.path.splitext(fname)[0]
        try:
            cuts = extract_cuts(
                fpath, output_dir,
                file_prefix=stem, start_idx=1,
                psd_exclude_layer=psd_exclude_layer,
            )
            all_results.append({"source": fname, "cuts": cuts})
        except Exception as e:
            errors.append(f"{fname}: {str(e)}")
            import traceback
            print(f"[PSDCutter] Error on {fname}: {e}")
            traceback.print_exc()

    total_cuts = sum(len(r["cuts"]) for r in all_results)
    landscape_cuts = sum(
        sum(1 for c in r["cuts"] if c.get("landscape"))
        for r in all_results
    )

    return {
        "output_dir": output_dir,
        "total_files": len(files),
        "total_cuts": total_cuts,
        "landscape_cuts": landscape_cuts,
        "results": all_results,
        "errors": errors,
    }
