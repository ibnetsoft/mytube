import os
import json
import shutil
import zipfile
import tempfile
import time
import glob
import re

from config import config
import database as db
from app.modes import is_shorts_mode


def _resolve_packaged_asset_path(asset_url_or_path: str):
    """Resolve app asset URLs even when the logged-in user output dir lives in AppData."""
    if not asset_url_or_path:
        return None

    candidate = asset_url_or_path
    if os.path.isabs(candidate) and os.path.exists(candidate):
        return candidate

    rel = None
    if candidate.startswith('/static/'):
        rel = candidate.replace('/static/', '', 1).replace('/', os.sep)
        static_path = os.path.join(config.STATIC_DIR, rel)
        if os.path.exists(static_path):
            return static_path
        return None
    if candidate.startswith('/output/'):
        rel = candidate.replace('/output/', '', 1).replace('/', os.sep)
    elif not candidate.startswith(('http://', 'https://')):
        rel = candidate.replace('/', os.sep)

    if not rel:
        return None

    output_path = os.path.join(config.OUTPUT_DIR, rel)
    if os.path.exists(output_path):
        return output_path

    local_appdata = os.getenv('LOCALAPPDATA')
    if local_appdata:
        matches = glob.glob(os.path.join(local_appdata, 'picadilly', '*', 'output', rel))
        for match in matches:
            if os.path.exists(match):
                return match

    return None


def _sanitize_subtitles_for_render(subtitles):
    cleaned = []
    for sub in subtitles or []:
        if not isinstance(sub, dict):
            continue
        text_value = str(sub.get('text', '') or '')
        text_value = re.sub(r'\[[^\]]*\]', '', text_value)
        text_value = re.sub(r'\([^)]*\)', '', text_value)
        text_value = re.sub(r'\s+', ' ', text_value).strip()
        cleaned.append({
            'text': text_value,
            'start': sub.get('start', 0),
            'end': sub.get('end', 0),
        })
    return cleaned


def _compute_image_durations(starts_or_durations, scene_count: int, audio_duration: float):
    if scene_count <= 0:
        return []

    values = []
    for raw in starts_or_durations or []:
        try:
            values.append(float(raw))
        except Exception:
            continue

    if not values:
        avg = audio_duration / scene_count if audio_duration and scene_count else 5.0
        return [avg] * scene_count

    if len(values) == scene_count and all(values[i] <= values[i + 1] for i in range(len(values) - 1)):
        durations = []
        for idx, start in enumerate(values):
            if idx < len(values) - 1:
                durations.append(max(0.1, values[idx + 1] - start))
            else:
                durations.append(max(2.0, audio_duration - start))
        return durations

    durations = values[:scene_count]
    if len(durations) < scene_count:
        remaining = max(0.0, audio_duration - sum(durations))
        remaining_count = scene_count - len(durations)
        avg = max(3.0, remaining / remaining_count) if remaining_count > 0 else 5.0
        durations.extend([avg] * remaining_count)
    return durations


def _build_project_upload_metadata(project_id: int, project_obj: dict, p_settings: dict):
    metadata = db.get_metadata(project_id) or {}
    title = (
        (metadata.get('titles') or [None])[0]
        or p_settings.get('title')
        or project_obj.get('name')
        or f'Project {project_id}'
    )
    description = metadata.get('description') or p_settings.get('description') or ''
    tags = metadata.get('tags') or []
    hashtags = metadata.get('hashtags') or [
        item.strip() for item in str(p_settings.get('hashtags') or '').split(',') if item.strip()
    ]
    return {
        'project_id': project_id,
        'project_name': project_obj.get('name') or f'Project {project_id}',
        'topic': project_obj.get('topic') or '',
        'title': title,
        'description': description,
        'tags': tags,
        'hashtags': hashtags,
        'status': 'ready_for_upload',
    }


def package_project_assets(project_id: int, use_subtitles: bool = True, resolution: str = '1080p') -> str:
    """Package local render inputs for remote rendering."""
    temp_dir = tempfile.mkdtemp(prefix=f'render_pkg_{project_id}_')

    try:
        images_dir = os.path.join(temp_dir, 'images')
        audio_dir = os.path.join(temp_dir, 'audio')
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(audio_dir, exist_ok=True)

        images_data = db.get_image_prompts(project_id) or []
        tts_data = db.get_tts(project_id) or {}
        p_settings = db.get_project_settings(project_id) or {}
        global_settings = db.get_global_setting('app_mode', 'longform')

        proj_mode = p_settings.get('app_mode', global_settings)
        is_shorts_project = is_shorts_mode(proj_mode) or p_settings.get('is_shorts') is True
        project_aspect = '9:16' if is_shorts_project else '16:9'

        audio_path = tts_data.get('audio_path')
        audio_filename = None
        if audio_path and os.path.exists(audio_path):
            audio_filename = os.path.basename(audio_path)
            shutil.copy2(audio_path, os.path.join(audio_dir, audio_filename))

        images = []
        timeline_path = p_settings.get('timeline_images_path')
        loaded_from_timeline = False

        if timeline_path and os.path.exists(timeline_path):
            try:
                with open(timeline_path, 'r', encoding='utf-8') as f:
                    urls = json.load(f)
                for url in urls:
                    if not url:
                        images.append('')
                        continue
                    fpath = _resolve_packaged_asset_path(url)
                    images.append(fpath if fpath and os.path.exists(fpath) else '')
                if images:
                    loaded_from_timeline = True
            except Exception:
                pass

        if not loaded_from_timeline:
            for img in images_data:
                target_url = img.get('image_url') or img.get('video_url')
                fpath = _resolve_packaged_asset_path(target_url)
                images.append(fpath if fpath and os.path.exists(fpath) else '')

        img_to_video = {}
        for prompt in images_data:
            v_url = prompt.get('video_url')
            i_url = prompt.get('image_url')
            if i_url and v_url:
                img_to_video[os.path.basename(i_url)] = v_url

        final_images_filenames = []
        for img_path in images:
            if not img_path:
                final_images_filenames.append(None)
                continue

            base_name = os.path.basename(img_path)
            if base_name in img_to_video:
                v_url = img_to_video[base_name]
                v_path = _resolve_packaged_asset_path(v_url)
                if v_path and os.path.exists(v_path):
                    img_path = v_path
                    base_name = os.path.basename(img_path)

            dest_path = os.path.join(images_dir, base_name)
            shutil.copy2(img_path, dest_path)
            final_images_filenames.append(base_name)

        subs = []
        if use_subtitles:
            db_sub_path = p_settings.get('subtitle_path')
            if db_sub_path and os.path.exists(db_sub_path):
                try:
                    with open(db_sub_path, 'r', encoding='utf-8') as f:
                        subs = json.load(f)
                except Exception:
                    pass
            if not subs:
                output_dir_local, _ = db.get_project_output_dir(project_id) if hasattr(db, 'get_project_output_dir') else (os.path.join(config.OUTPUT_DIR, f'project_{project_id}'), '')
                saved_sub_path = os.path.join(output_dir_local, f'subtitles_{project_id}.json')
                if os.path.exists(saved_sub_path):
                    try:
                        with open(saved_sub_path, 'r', encoding='utf-8') as f:
                            subs = json.load(f)
                    except Exception:
                        pass
        subs = _sanitize_subtitles_for_render(subs)

        render_settings = dict(p_settings)
        if render_settings.get('subtitle_bg_enabled') is None and render_settings.get('bg_enabled') is None:
            render_settings['subtitle_bg_enabled'] = 1
        elif render_settings.get('subtitle_bg_enabled') is None:
            render_settings['subtitle_bg_enabled'] = render_settings.get('bg_enabled', 1)
        if render_settings.get('bg_enabled') is None:
            render_settings['bg_enabled'] = render_settings.get('subtitle_bg_enabled', 1)

        stored_effects = []
        effects_path = p_settings.get('image_effects_path')
        if effects_path and os.path.exists(effects_path):
            try:
                with open(effects_path, 'r', encoding='utf-8') as f_eff:
                    raw_effects = json.load(f_eff)
                if isinstance(raw_effects, list):
                    stored_effects = raw_effects
            except Exception:
                stored_effects = []

        image_effects = []
        focal_point_ys = []
        for idx, img in enumerate(images_data):
            scene_number = img.get('scene_number') or (idx + 1)
            explicit_effect = p_settings.get(f'scene_{scene_number}_motion')
            if explicit_effect:
                image_effects.append(explicit_effect)
            elif idx < len(stored_effects) and stored_effects[idx]:
                image_effects.append(stored_effects[idx])
            else:
                image_effects.append('auto_classify')
            try:
                focal_point_ys.append(float(img.get('focal_point_y', 0.5) or 0.5))
            except Exception:
                focal_point_ys.append(0.5)

        while len(image_effects) < len(final_images_filenames):
            image_effects.append('auto_classify')
        while len(focal_point_ys) < len(final_images_filenames):
            focal_point_ys.append(0.5)

        image_timing_starts = None
        tm_path = p_settings.get('image_timings_path')
        if tm_path and os.path.exists(tm_path):
            try:
                with open(tm_path, 'r', encoding='utf-8') as f_tm:
                    image_timing_starts = json.load(f_tm)
            except Exception:
                pass

        bg_video_url = p_settings.get('bg_video_url')
        intro_video_path = p_settings.get('intro_video_path')
        intro_filename = None
        if intro_video_path and os.path.exists(intro_video_path):
            intro_filename = os.path.basename(intro_video_path)
            shutil.copy2(intro_video_path, os.path.join(temp_dir, intro_filename))

        template_overlay_filename = None
        preset_name = render_settings.get('shorts_template_preset')
        if preset_name:
            try:
                all_presets = db.get_shorts_template_presets()
                match = next((p for p in all_presets if p['name'] == preset_name), None)
                image_path = match.get('image_path') if match else None
                if image_path and os.path.exists(image_path):
                    overlays_dir = os.path.join(temp_dir, 'overlays')
                    os.makedirs(overlays_dir, exist_ok=True)
                    template_overlay_filename = os.path.basename(image_path)
                    shutil.copy2(image_path, os.path.join(overlays_dir, template_overlay_filename))
            except Exception:
                pass

        from services.auth_service import auth_service
        project_obj = db.get_project(project_id) or {}
        project_name = project_obj.get('name', f'Project {project_id}')
        project_upload_metadata = _build_project_upload_metadata(project_id, project_obj, p_settings)

        thumbnail_filename = None
        thumbnail_url = p_settings.get('thumbnail_url') or p_settings.get('thumbnail_path')
        thumbnail_local_path = _resolve_packaged_asset_path(thumbnail_url) if thumbnail_url else None
        if thumbnail_local_path and os.path.exists(thumbnail_local_path):
            thumb_ext = os.path.splitext(thumbnail_local_path)[1] or '.png'
            thumbnail_filename = f"thumbnail{thumb_ext.lower()}"
            shutil.copy2(thumbnail_local_path, os.path.join(temp_dir, thumbnail_filename))

        metadata = {
            'project_id': project_id,
            'project_name': project_name,
            'email': auth_service.get_user_email() or 'unknown',
            'use_subtitles': use_subtitles,
            'resolution': resolution,
            'aspect_ratio': project_aspect,
            'audio_filename': audio_filename,
            'audio_duration': tts_data.get('duration'),
            'images': final_images_filenames,
            'subtitles': subs,
            'render_settings': render_settings,
            'image_timing_starts': image_timing_starts,
            'image_effects': image_effects,
            'focal_point_ys': focal_point_ys,
            'bg_video_url': bg_video_url,
            'intro_filename': intro_filename,
            'template_overlay_filename': template_overlay_filename,
            'content_aspect_ratio': p_settings.get('aspect_ratio'),
            'app_mode': proj_mode,
            'thumbnail_filename': thumbnail_filename,
            'project_upload_metadata': project_upload_metadata,
        }

        with open(os.path.join(temp_dir, 'config.json'), 'w', encoding='utf-8') as f_conf:
            json.dump(metadata, f_conf, ensure_ascii=False, indent=4)

        zip_output_dir = os.path.join(config.OUTPUT_DIR, f'project_{project_id}')
        os.makedirs(zip_output_dir, exist_ok=True)
        zip_path = os.path.join(zip_output_dir, f'remote_render_pkg_{project_id}.zip')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, rel_path)

        return zip_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def remote_render_executor_func(task_id: str, temp_dir: str, use_gpu: bool = False):
    progress_file = os.path.join(temp_dir, 'progress.txt')

    def update_progress(percent: int, message: str):
        with open(progress_file, 'w', encoding='utf-8') as f_prog:
            f_prog.write(json.dumps({'progress': percent, 'message': message, 'timestamp': time.time()}))

    try:
        update_progress(5, 'Loading render package...')
        config_path = os.path.join(temp_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f_conf:
            metadata = json.load(f_conf)

        aspect_ratio = metadata.get('aspect_ratio', '16:9')
        resolution = metadata.get('resolution', '1080p')
        audio_filename = metadata.get('audio_filename')
        images_filenames = metadata.get('images', [])
        subs = _sanitize_subtitles_for_render(metadata.get('subtitles', []))
        render_settings = metadata.get('render_settings', {})
        image_timing_starts = metadata.get('image_timing_starts')
        image_effects = metadata.get('image_effects') or []
        focal_point_ys = metadata.get('focal_point_ys') or []

        if aspect_ratio == '9:16':
            target_resolution = (1080, 1920) if resolution == '1080p' else (720, 1280)
        else:
            target_resolution = (1920, 1080) if resolution == '1080p' else (1280, 720)

        audio_path = os.path.join(temp_dir, 'audio', audio_filename) if audio_filename else None
        if not audio_path or not os.path.exists(audio_path):
            raise Exception('TTS audio file was not found.')

        update_progress(15, 'Reading audio metadata...')
        audio_duration = float(metadata.get('audio_duration') or 0.0)
        if audio_duration <= 0:
            try:
                from moviepy import AudioFileClip
            except ImportError:
                from moviepy.editor import AudioFileClip
            audio_clip = AudioFileClip(audio_path)
            audio_duration = float(audio_clip.duration)
            audio_clip.close()

        images = []
        for fname in images_filenames:
            if fname:
                path_img = os.path.join(temp_dir, 'images', fname)
                images.append(path_img if os.path.exists(path_img) else '')
            else:
                images.append('')

        update_progress(30, 'Building render inputs...')
        if not any(images):
            raise Exception('No image resources were found for remote rendering.')

        durations = _compute_image_durations(image_timing_starts, len(images), audio_duration)
        template_overlay_filename = metadata.get('template_overlay_filename')
        template_overlay_path = os.path.join(temp_dir, 'overlays', template_overlay_filename) if template_overlay_filename else None
        intro_filename = metadata.get('intro_filename')
        intro_video_path = os.path.join(temp_dir, intro_filename) if intro_filename else None

        from services.video_service import video_service

        update_progress(50, 'Rendering with local slideshow engine...')
        remote_output_name = f'remote_task_{task_id}.mp4'
        rendered_path = video_service.create_slideshow(
            images=images,
            audio_path=audio_path,
            output_filename=remote_output_name,
            duration_per_image=durations,
            fps=24,
            resolution=target_resolution,
            project_id=metadata.get('project_id'),
            subtitles=subs if metadata.get('use_subtitles') else [],
            subtitle_settings=render_settings,
            template_overlay_path=template_overlay_path if template_overlay_path and os.path.exists(template_overlay_path) else None,
            intro_video_path=intro_video_path if intro_video_path and os.path.exists(intro_video_path) else None,
            focal_point_ys=focal_point_ys,
            image_effects=image_effects,
            content_aspect_ratio=metadata.get('content_aspect_ratio'),
        )

        output_file_path = os.path.join(temp_dir, 'output.mp4')
        update_progress(90, 'Copying final video...')
        if rendered_path != output_file_path:
            shutil.copy2(rendered_path, output_file_path)
        update_progress(100, 'Completed')
    except Exception as err:
        update_progress(-1, f'Error: {str(err)}')
        raise err
