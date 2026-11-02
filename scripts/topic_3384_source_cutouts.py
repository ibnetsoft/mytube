"""Produce source-pixel character cutout drafts without redrawing scene images."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from ultralytics import YOLO


ROOT = Path('output/codex-local-console/3384-scene-recovery-v3')
DEST = ROOT / 'source-pixel-cutouts-v1'
MODEL = Path('yolov8n-seg.pt')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(MODEL))
    started = time.monotonic()
    results = []
    for number in range(19, 81):
        source = ROOT / 'production' / f'scene-{number:03}.png'
        directory = DEST / f'scene-{number:03}'
        directory.mkdir(exist_ok=True)
        manifest = directory / 'manifest.json'
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding='utf8'))
            if previous.get('source_sha256') != digest(source):
                raise ValueError(f'Scene {number}: source changed; preserve prior output')
            results.append(previous)
            continue
        try:
            with Image.open(source) as image:
                rgb = np.asarray(image.convert('RGB')).copy()
            height, width = rgb.shape[:2]
            prediction = model.predict(str(source), classes=[0], conf=0.28, iou=0.4,
                                       imgsz=960, retina_masks=True, verbose=False,
                                       device='cpu', max_det=12)[0]
            masks = prediction.masks.data.cpu().numpy() if prediction.masks is not None else []
            boxes = prediction.boxes.xyxy.cpu().numpy() if prediction.boxes is not None else []
            confs = prediction.boxes.conf.cpu().numpy() if prediction.boxes is not None else []
            instances = []
            accepted = []
            order = sorted(range(len(masks)), key=lambda i: float(confs[i]), reverse=True)
            for index in order:
                mask = cv2.resize(masks[index], (width, height), interpolation=cv2.INTER_LINEAR) >= 0.5
                area = int(mask.sum())
                if area < width * height * 0.003:
                    continue
                if any(np.logical_and(mask, old).sum() / max(1, min(area, int(old.sum()))) > .88 for old in accepted):
                    continue
                accepted.append(mask)
                rgba = np.empty((height, width, 4), dtype=np.uint8)
                rgba[:, :, :3] = rgb
                rgba[:, :, 3] = mask.astype(np.uint8) * 255
                target = directory / f'person-{len(accepted):02}.png'
                if target.exists():
                    raise FileExistsError(f'Preserve existing unfinished output: {target}')
                Image.fromarray(rgba, 'RGBA').save(target)
                with Image.open(target) as readback:
                    readback.load()
                    arr = np.asarray(readback)
                    if readback.size != (width, height) or not np.array_equal(arr[:, :, :3][mask], rgb[mask]):
                        raise ValueError('Source pixel/canvas mismatch')
                instances.append({'file': target.name, 'sha256': digest(target),
                                  'bbox': [round(float(v), 1) for v in boxes[index]],
                                  'detection_confidence': round(float(confs[index]), 4),
                                  'pixel_count': area})
            psd_path = directory / f'scene-{number:03}-source-cutouts.psd'
            doc = PSDImage.new('RGBA', (width, height))
            with Image.open(source) as image:
                doc.create_pixel_layer(image.convert('RGBA'), name='original_scene').visible = True
            for i, entry in enumerate(instances, 1):
                with Image.open(directory / entry['file']) as layer:
                    doc.create_pixel_layer(layer.convert('RGBA'), name=f'person_{i:02}').visible = False
            doc.save(psd_path)
            reopened = PSDImage.open(psd_path)
            if reopened.size != (width, height) or len(reopened) != len(instances) + 1:
                raise ValueError('PSD did not reopen with expected layers')
            record = {'scene_number': number, 'status': 'source_pixel_cutouts_created' if instances else 'no_person_detected',
                      'source_sha256': digest(source), 'source_size': [width, height],
                      'instances': instances, 'psd': psd_path.name, 'psd_sha256': digest(psd_path),
                      'notes': 'Automatic masks may miss, merge, or include a pictured person or object. No identity comparison. Original visible as the base; hidden cutouts preserve visible source RGB and placement. The base is not an erased background and occluded portions are unavailable.'}
            manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
            results.append(record)
            print(f'{number}: {len(instances)} cutouts, {time.monotonic()-started:.1f}s', flush=True)
        except Exception as exc:
            results.append({'scene_number': number, 'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
            print(f'{number}: failed: {exc}', flush=True)
    report = {'model': str(MODEL), 'model_sha256': digest(MODEL),
              'elapsed_seconds': round(time.monotonic()-started, 2), 'scenes': results}
    (DEST / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print('summary', {s: sum(x['status'] == s for x in results)
                      for s in ('source_pixel_cutouts_created', 'no_person_detected', 'failed')}, flush=True)


if __name__ == '__main__':
    main()
