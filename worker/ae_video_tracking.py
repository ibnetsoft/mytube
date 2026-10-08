"""Conservative optical-flow tracking of user-identified speaking faces."""
import copy
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def track_video(video, reference, speakers, directory, duration):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        ok, first = cap.read()
        if not ok or not math.isfinite(fps) or fps <= 0:
            raise ValueError('원본 영상의 프레임과 재생 속도를 읽지 못했습니다.')
        h, w = first.shape[:2]
        ref = cv2.imread(str(reference))
        if ref is None:
            raise ValueError('저장된 화자 좌표의 기준 이미지를 읽지 못했습니다.')
        ref = cv2.resize(ref, (w, h))
        gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
        reference_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        first_path = directory / 'video-first-frame.png'
        cv2.imwrite(str(first_path), first)
        tracked, states = copy.deepcopy(speakers), []
        for speaker in tracked:
            box = speaker.get('face_box')
            if not box or len(box) != 4:
                raise ValueError('영상 화자 추적에는 저장된 얼굴 좌표가 필요합니다.')
            x, y, right, bottom = [round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(box)]
            template = reference_gray[y:bottom, x:right]
            if min(template.shape, default=0) < 16 or template.std() < 5:
                raise ValueError('얼굴 영역이 너무 작거나 특징이 부족합니다.')
            scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(scores)
            if score < .82:
                raise ValueError('영상 첫 프레임의 화자가 저장된 기준 이미지와 일치하지 않습니다. 얼굴·입 위치를 확인해 주세요.')
            alternatives = scores.copy()
            alternatives[max(0,loc[1]-template.shape[0]//2):loc[1]+template.shape[0]//2+1,
                         max(0,loc[0]-template.shape[1]//2):loc[0]+template.shape[1]//2+1] = -1
            if alternatives.max() > .9 and score - alternatives.max() < .03:
                raise ValueError('비슷한 얼굴이 여러 위치에 있어 화자를 확정할 수 없습니다.')
            dx, dy = loc[0] - x, loc[1] - y
            speaker['face_box'] = [(x+dx)/w, (y+dy)/h, (right+dx)/w, (bottom+dy)/h]
            speaker['mouth_box'] = [v + (dx/w if i % 2 == 0 else dy/h) for i, v in enumerate(speaker['mouth_box'])]
            mask = np.zeros(gray.shape, np.uint8)
            cv2.rectangle(mask, loc, (loc[0]+right-x, loc[1]+bottom-y), 255, -1)
            l, t, r, b = [round(v * (w if i % 2 == 0 else h)) for i,v in enumerate(speaker['mouth_box'])]
            cv2.rectangle(mask, (l-4,t-4), (r+4,b+4), 0, -1)
            points = cv2.goodFeaturesToTrack(gray, maxCorners=120, qualityLevel=.02, minDistance=4, mask=mask)
            if points is None or len(points) < 12:
                raise ValueError('화자 얼굴을 안정적으로 추적할 특징점이 부족합니다.')
            states.append({'points':points, 'origin':points.copy(), 'initial_count':len(points),
                           'center':np.array([[(l+r)/2, (t+b)/2]],np.float32), 'matrix':np.eye(2,3,dtype=np.float32),
                           'mask':mask.astype(bool), 'appearance':gray[mask.astype(bool)].astype(float)})
            speaker['tracking'] = [{'at_seconds':0., 'offset':[0.,0.], 'scale':100., 'rotation':0.}]
        previous = gray
        frame = 1
        while frame / fps < duration:
            ok, image = cap.read()
            if not ok:
                break
            current = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            for speaker, state in zip(tracked, states):
                points = state['points']
                moved, good, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None)
                if moved is None or good is None:
                    raise ValueError('영상 화자 추적이 끊겼습니다.')
                back, valid, _ = cv2.calcOpticalFlowPyrLK(current, previous, moved, None)
                if back is None or valid is None:
                    raise ValueError('영상 화자 추적의 역방향 검증에 실패했습니다.')
                keep = (good.ravel()==1) & (valid.ravel()==1) & (np.linalg.norm(points-back,axis=2).ravel()<1.2)
                if keep.sum() < max(10, state['initial_count']*.45):
                    raise ValueError('얼굴 가림 또는 장면 전환으로 추적 신뢰도가 낮아졌습니다.')
                origin, moved = state['origin'][keep], moved[keep]
                matrix, inliers = cv2.estimateAffinePartial2D(origin, moved, method=cv2.RANSAC, ransacReprojThreshold=1.5)
                if matrix is None or inliers is None or inliers.mean()<.8:
                    raise ValueError('얼굴 움직임을 안정적으로 추정하지 못했습니다.')
                scale = math.hypot(matrix[0,0],matrix[1,0])
                rotation = math.degrees(math.atan2(matrix[1,0],matrix[0,0]))
                if not (.7 <= scale <= 1.4) or abs(rotation)>20:
                    raise ValueError('얼굴 회전·크기 변화가 자동 입 합성 범위를 넘었습니다.')
                center = cv2.transform(state['center'][None,:,:], matrix)[0,0]
                if not (0 <= center[0] < w and 0 <= center[1] < h):
                    raise ValueError('화자의 입이 화면 밖으로 이동했습니다.')
                # Reject identity switches, occlusion and large out-of-plane changes.
                aligned = cv2.warpAffine(current, matrix, (w,h), flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP)
                appearance = aligned[state['mask']].astype(float)
                similarity = np.corrcoef(state['appearance'],appearance)[0,1]
                if not math.isfinite(similarity) or similarity < .65:
                    raise ValueError('얼굴 가림·회전 또는 화자 변경으로 추적을 검수해야 합니다.')
                speaker['tracking'].append({'at_seconds':round(frame/fps,6),
                    'offset':(center-state['center'][0]).tolist(), 'scale':scale*100, 'rotation':rotation})
                state.update(points=moved,origin=origin,matrix=matrix)
            previous = current
            frame += 1
        actual_duration = frame / fps
        report = {'version':1,'video_sha256':hashlib.sha256(Path(video).read_bytes()).hexdigest(),
            'first_frame_sha256':hashlib.sha256(first_path.read_bytes()).hexdigest(),
            'fps':fps,'frames_checked':frame,'source_duration':actual_duration,'width':w,'height':h,
            'speakers':[{'speaker':s['speaker'],'keyframes':len(s['tracking'])} for s in tracked]}
        (directory/'tracking.json').write_text(json.dumps({'report':report,'speakers':tracked},ensure_ascii=False),encoding='utf-8')
        return first_path, tracked, report
    finally:
        cap.release()
