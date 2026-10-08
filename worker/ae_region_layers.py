"""Reusable, reviewed scene layers, independent of motion and subtitle timing."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import cv2


def build_layers(source, directory, data, replacements=None, background=None):
    if hashlib.sha256(source.read_bytes()).hexdigest() != data['imageSha256']:
        raise ValueError('원본 이미지가 변경됐습니다.')
    original = Image.open(source).convert('RGB')
    ratio = min(1, 1920/max(original.size))
    size = tuple(max(2, int(n*ratio)//2*2) for n in original.size)
    original = original.resize(size, Image.Resampling.LANCZOS)
    pixels = np.asarray(original)
    directory.mkdir(parents=True, exist_ok=True)
    union = np.zeros((size[1], size[0]), np.uint8)
    layers, warnings = [], []
    for i, r in enumerate(data['geometry']):
        poly = Image.new('L', size)
        ImageDraw.Draw(poly).polygon([(round(p[0]*size[0]), round(p[1]*size[1])) for p in r['polygon']], fill=255)
        mask = np.asarray(poly).copy()
        replacement = (replacements or {}).get(r['id'])
        if r.get('occluded') and not replacement:
            raise ValueError('가려진 부위의 완성된 투명 PNG가 필요합니다.')
        if replacement:
            layer = Image.open(replacement).convert('RGBA')
            if layer.size != size:
                raise ValueError('보완 이미지 캔버스 크기가 다릅니다.')
            alpha = np.asarray(layer.getchannel('A'))
            if alpha.min() == 255 or alpha.max() == 0:
                raise ValueError('보완 부위는 투명 배경이 필요합니다.')
            # Erase the original visible extent as well as the supplied completed part.
            union = np.maximum(union, mask)
        else:
            if r.get('contour') != 'exact':
                labels = np.full(mask.shape, cv2.GC_BGD, np.uint8)
                labels[mask > 0] = cv2.GC_PR_FGD
                core = cv2.erode(mask, np.ones((5, 5), np.uint8))
                labels[core > 0] = cv2.GC_PR_FGD
                # Seed a narrow interior core, while allowing the boundary to follow edges.
                distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
                if distance.max() > 0:
                    labels[distance > distance.max()*.7] = cv2.GC_FGD
                try:
                    cv2.grabCut(pixels, labels, None, np.zeros((1, 65)), np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_MASK)
                    refined = np.where((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
                    if np.count_nonzero(refined) < 20:
                        raise ValueError('empty contour')
                    mask = refined
                except (cv2.error, ValueError):
                    warnings.append(r['id'] + ': 자동 외곽선 분리가 어려워 지정 외곽선을 사용했습니다. 브러시로 확인해 주세요.')
            alpha = np.asarray(Image.fromarray(mask).filter(ImageFilter.GaussianBlur(.5)))
            layer = original.convert('RGBA')
            layer.putalpha(Image.fromarray(alpha))
        union = np.maximum(union, np.where(alpha > 8, 255, 0).astype(np.uint8))
        path = directory / f'foreground-{i}.png'
        layer.save(path)
        layers.append({'id': r['id'], 'role': 'region:'+r['id'], 'path': path})
    if background:
        plate = Image.open(background).convert('RGB')
        if plate.size != size:
            raise ValueError('수정 배경의 캔버스 크기가 다릅니다.')
    else:
        expanded = cv2.dilate(union, np.ones((5, 5), np.uint8))
        plate = Image.fromarray(cv2.inpaint(pixels, expanded, 5, cv2.INPAINT_TELEA))
        warnings.append('자동 복원한 배경은 추정 결과입니다. 복잡한 무늬·몸통·가려진 사물은 수정 배경을 올려 보완하세요.')
    plate_path = directory/'background.png'
    plate.save(plate_path)
    composite = plate.convert('RGBA')
    for layer in layers:
        composite.alpha_composite(Image.open(layer['path']).convert('RGBA'))
    composite_path = directory/'composite.png'
    composite.save(composite_path)
    return {'width': size[0], 'height': size[1], 'warnings': warnings,
            'files': [{'role': 'background', 'path': plate_path}, *layers, {'role': 'composite', 'path': composite_path}]}


def load_runtime(directory, data, download):
    """Use saved PNG bytes without segmentation or inpainting on subsequent renders."""
    package = data['layerPackage']
    result = package['result']
    paths = {}
    directory.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(result['files']):
        if f['role'] == 'composite':
            continue
        target = directory / f'layer-{i}.png'
        download(f, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != f['sha256']:
            raise ValueError('저장 레이어 파일이 변경됐습니다. 다시 준비해 주세요.')
        paths[f['role']] = str(target.resolve())
    return {'width': result['width'], 'height': result['height'], 'duration': data['timeline']['duration'],
            'background': paths['background'],
            'regions': [{**r, 'path': paths['region:'+r['id']]} for r in data['regions']]}
