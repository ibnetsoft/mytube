"""
오토파일럿 렌더 로직 단위 테스트
- 실제 렌더 없이 이미지 배열 구성, 자막 타이밍 조정, bg_enabled 처리를 검증
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db

def get_best_path(img, settings, project_id):
    """autopilot_service._render_video 의 best_path 선택 로직 복제"""
    import config as _cfg; OUTPUT_DIR = _cfg.Config().OUTPUT_DIR
    video_url = img.get("video_url")
    image_url = img.get("image_url")
    scene_num = img.get('scene_number')

    # video_url filesystem fallback
    if not video_url:
        import glob as _glob
        manual_files = _glob.glob(os.path.join(OUTPUT_DIR, f"vid_*_{project_id}_{scene_num}_*.mp4"))
        if manual_files:
            manual_files.sort(key=os.path.getmtime, reverse=True)
            video_url = manual_files[0]

    best_path = None
    if video_url:
        fpath = os.path.join(OUTPUT_DIR, video_url.replace("/output/", "")) if video_url.startswith("/output/") else os.path.join(OUTPUT_DIR, video_url.split("/")[-1])
        if os.path.exists(fpath):
            best_path = fpath

    if not best_path and image_url:
        fpath = os.path.join(OUTPUT_DIR, image_url.replace("/output/", "")) if image_url.startswith("/output/") else os.path.join(OUTPUT_DIR, image_url.split("/")[-1])
        if os.path.exists(fpath):
            best_path = fpath

    return best_path

def test_project(project_id):
    print(f"\n{'='*60}")
    print(f"  PROJECT {project_id} 렌더 로직 테스트")
    print(f"{'='*60}")

    settings = db.get_project_settings(project_id) or {}
    tts_data = db.get_tts(project_id)
    images_data = db.get_image_prompts(project_id)

    if not images_data:
        print("❌ image_prompts 없음")
        return
    if not tts_data:
        print("❌ TTS 없음")
        return

    sorted_prompts = sorted(images_data, key=lambda x: x.get('scene_number', 0))
    print(f"\n[1] 전체 씬: {len(sorted_prompts)}개, TTS duration: {tts_data.get('duration', 0):.2f}s")

    # --- images 배열 구성 ---
    images = []
    _valid_scene_numbers = []
    _skipped_scene_numbers = []
    for img in sorted_prompts:
        scene_num = img.get('scene_number')
        best_path = get_best_path(img, settings, project_id)
        if best_path:
            images.append(best_path)
            _valid_scene_numbers.append(scene_num)
        else:
            _skipped_scene_numbers.append(scene_num)

    print(f"\n[2] 유효 씬: {_valid_scene_numbers}")
    print(f"    스킵된 씬: {_skipped_scene_numbers} ← 이 씬이 없어서 첫 이미지가 빠짐")

    # --- image_timings 로드 ---
    timings_path = settings.get("image_timings_path")
    all_durations = None
    if timings_path and os.path.exists(timings_path):
        with open(timings_path, encoding="utf-8") as f:
            loaded_starts = json.load(f)
        total_dur = tts_data["duration"]
        is_pacing = all(x < y for x, y in zip(loaded_starts, loaded_starts[1:])) if len(loaded_starts) > 1 else True
        if is_pacing:
            all_durations = []
            for i in range(len(loaded_starts)):
                if i < len(loaded_starts) - 1:
                    all_durations.append(loaded_starts[i+1] - loaded_starts[i])
                else:
                    all_durations.append(max(2.0, total_dur - loaded_starts[i]))
        else:
            all_durations = loaded_starts
        print(f"\n[3] image_timings: {len(all_durations)}개 구간")
        for i, (sn, dur) in enumerate(zip([p.get('scene_number') for p in sorted_prompts], all_durations)):
            skip_mark = " ← SKIPPED" if sn in _skipped_scene_numbers else ""
            print(f"    Scene {sn}: {dur:.2f}s{skip_mark}")
    else:
        print(f"\n[3] image_timings 없음")

    # --- duration 조정 ---
    if all_durations and _skipped_scene_numbers and len(all_durations) == len(sorted_prompts):
        skipped_indices = {idx for idx, p in enumerate(sorted_prompts) if p.get('scene_number') in _skipped_scene_numbers}
        image_durations = [d for idx, d in enumerate(all_durations) if idx not in skipped_indices]
        skipped_offset = sum(all_durations[idx] for idx in skipped_indices)
        print(f"\n[4] 조정 후 durations: {len(image_durations)}개, skipped_offset={skipped_offset:.2f}s")
        print(f"    durations: {[round(d,2) for d in image_durations]}")
        print(f"    images 배열 길이: {len(images)}")
        match = len(image_durations) == len(images)
        print(f"    ✅ images vs durations 길이 일치: {match}" if match else f"    ❌ 불일치! images={len(images)}, durations={len(image_durations)}")
    elif all_durations:
        image_durations = all_durations[:len(images)]
        skipped_offset = 0.0
        print(f"\n[4] 스킵 없음, durations 그대로 사용")

    # --- 자막 로드 및 타이밍 체크 ---
    subtitle_path = settings.get("subtitle_path")
    subs = []
    if subtitle_path and os.path.exists(subtitle_path):
        with open(subtitle_path, encoding="utf-8") as f:
            subs = json.load(f)
    print(f"\n[5] 자막: {len(subs)}개")
    if subs:
        print(f"    첫 자막: start={subs[0]['start']}, text={subs[0]['text'][:30]}")
        print(f"    마지막 자막: end={subs[-1]['end']}")
        video_total = sum(image_durations) if isinstance(image_durations, list) else image_durations * len(images)
        print(f"    영상 총 길이(예상): {video_total:.2f}s")
        out_of_range = [s for s in subs if s['start'] >= video_total]
        print(f"    영상 범위 초과 자막: {len(out_of_range)}개 {'← 문제!' if out_of_range else '(정상)'}")

        if skipped_offset > 0:
            print(f"\n    [자막 타이밍 조정 시뮬레이션] offset={skipped_offset:.2f}s 빼기:")
            adj = []
            for s in subs:
                ns = s['start'] - skipped_offset
                ne = s['end'] - skipped_offset
                if ne > 0:
                    adj.append({"text": s['text'], "start": max(0.0, round(ns,2)), "end": round(ne,2)})
            print(f"    조정 후 자막: {len(adj)}개 (제거된 자막: {len(subs)-len(adj)}개)")
            if adj:
                print(f"    첫 자막: start={adj[0]['start']}, text={adj[0]['text'][:30]}")
            out_of_range2 = [s for s in adj if s['start'] >= video_total]
            print(f"    조정 후 초과 자막: {len(out_of_range2)}개 {'← 여전히 문제' if out_of_range2 else '✅ 정상'}")

    # --- bg_enabled 체크 ---
    bg_raw = settings.get("subtitle_bg_enabled")
    bg_legacy = settings.get("bg_enabled")
    print(f"\n[6] subtitle_bg_enabled={repr(bg_raw)}, bg_enabled={repr(bg_legacy)}")
    final_bg = bg_raw if bg_raw is not None else bg_legacy
    if final_bg is None:
        print(f"    ❌ bg_enabled=None → TypeError 발생! 자막 PNG 생성 실패")
    else:
        print(f"    ✅ bg_enabled={final_bg} → 정상")

    # --- render_settings sanitize 체크 (새 코드) ---
    render_settings = dict(settings)
    if render_settings.get("subtitle_bg_enabled") is None and render_settings.get("bg_enabled") is None:
        render_settings["subtitle_bg_enabled"] = 1
    if render_settings.get("bg_enabled") is None:
        render_settings["bg_enabled"] = render_settings.get("subtitle_bg_enabled", 1)
    print(f"    render_settings 정리 후: subtitle_bg_enabled={render_settings.get('subtitle_bg_enabled')}, bg_enabled={render_settings.get('bg_enabled')}")

    print(f"\n{'='*60}")
    print(f"  진단 요약")
    print(f"{'='*60}")
    issues = []
    if _skipped_scene_numbers:
        issues.append(f"❌ Scene {_skipped_scene_numbers} 파일 없음 → 첫 이미지 누락")
    if all_durations and len(images) != len(image_durations):
        issues.append(f"❌ images({len(images)}) vs durations({len(image_durations)}) 불일치")
    if final_bg is None:
        issues.append(f"❌ bg_enabled=None → 자막 없음")
    if not issues:
        print("  ✅ 모든 항목 정상")
    for iss in issues:
        print(f"  {iss}")

    return {
        "skipped": _skipped_scene_numbers,
        "images_count": len(images),
        "durations_count": len(image_durations) if isinstance(image_durations, list) else 1,
        "subs_count": len(subs),
        "bg_issue": final_bg is None,
    }

if __name__ == "__main__":
    # 최근 프로젝트들 테스트
    import database as db
    projects = db.get_all_projects() if hasattr(db, 'get_all_projects') else []

    # 직접 지정
    test_ids = [149, 150, 151]

    for pid in test_ids:
        try:
            test_project(pid)
        except Exception as e:
            import traceback
            print(f"Project {pid} 테스트 실패: {e}")
            traceback.print_exc()
