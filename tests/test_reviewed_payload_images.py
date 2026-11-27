from worker.reviewed_payload_images import reviewed_payload_image


def test_reviewed_source_and_exclusion_are_bound():
    sha = 'a' * 64
    scene = {'scene_number': 18, 'cut_id': 'C018', 'image_use_status': 'approved',
             'source_image_sha256': sha, 'gcs_bucket': 'bucket', 'gcs_path': 'scene.png',
             'anatomy_review': {'contract': 'wuxia_anatomy_review/v1', 'verdict': 'pass', 'source_sha256': sha}}
    project = {'id': 'p', 'project_payload': {'structure': {'scenes': [scene]}}}
    image = reviewed_payload_image(project, 18)
    assert image['id'] == f'reviewed-payload:18:{sha}'
    scene['image_use_status'] = 'review_candidate'
    assert reviewed_payload_image(project, 18) is None
    scene['image_use_status'] = 'approved'
    scene['anatomy_review']['source_sha256'] = 'b' * 64
    assert reviewed_payload_image(project, 18) is None
    scene['anatomy_review']['source_sha256'] = sha
    project['project_payload']['structure']['excluded_image_cut_ids'] = ['C018']
    assert reviewed_payload_image(project, 18) is None
