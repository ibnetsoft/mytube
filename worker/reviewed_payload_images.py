"""Resolve only source-bound approved artwork for motion workers."""
import re


def reviewed_payload_image(project, number):
    structure = ((project.get('project_payload') or {}).get('structure') or {})
    excluded = structure.get('excluded_image_cut_ids') or []
    scene = next((s for s in structure.get('scenes') or []
                  if int(s.get('scene_number') or s.get('scene_order') or 0) == number), None)
    if not scene or scene.get('cut_id') in excluded or scene.get('image_use_status') != 'approved':
        return None
    sha = str(scene.get('source_image_sha256') or '').lower()
    review = scene.get('anatomy_review') or {}
    if (not re.fullmatch(r'[a-f0-9]{64}', sha) or review.get('contract') != 'wuxia_anatomy_review/v1'
            or review.get('verdict') != 'pass' or str(review.get('source_sha256') or '').lower() != sha
            or (review.get('cut_id') and review.get('cut_id') != scene.get('cut_id'))
            or not scene.get('gcs_bucket') or not scene.get('gcs_path')):
        return None
    return {'id': f'reviewed-payload:{number}:{sha}', 'project_id': project['id'], 'asset_type': 'image',
            'status': 'assigned', 'scene_number': number, 'mime_type': 'image/png',
            'metadata': {'storage_provider': 'gcs', 'gcs_bucket': scene['gcs_bucket'],
                         'gcs_path': scene['gcs_path'], 'reviewed_source_sha256': sha}}
