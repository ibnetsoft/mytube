import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
import ae_scene_production as production


def test_boundary_uses_frozen_comic_image_instead_of_available_video(tmp_path, monkeypatch):
    image = {'id': 'image', 'asset_type': 'image', 'metadata': {'gcs_path': 'image.png'}}
    video = {'id': 'video', 'asset_type': 'video', 'metadata': {'gcs_path': 'different.mp4'}}
    selected = []
    def download(source, path):
        selected.append(source)
        return path
    monkeypatch.setattr(production, '_download_asset', download)
    path, is_video, kind = production._boundary_source(
        {'number': 1, 'image': image, 'original_video': video, 'selected_media': image}, {}, tmp_path)
    assert selected == [image]
    assert is_video is False and kind == 'original_image' and path.suffix == '.png'


def test_boundary_uses_reviewed_derived_video_selected_for_final_composition(tmp_path, monkeypatch):
    original = {'id': 'original', 'asset_type': 'video', 'metadata': {'gcs_path': 'original.mp4'}}
    reviewed = {'asset_type': 'video', 'metadata': {'gcs_path': 'reviewed.mp4', 'render_sha256': 'a' * 64}}
    monkeypatch.setattr(production, '_download_asset', lambda source, path: pathlib.Path(source['metadata']['gcs_path']))
    path, video, _ = production._boundary_source(
        {'number': 1, 'original_video': original, 'selected_media': reviewed}, {}, tmp_path)
    assert video is True and path.name == 'reviewed.mp4'


def test_explicit_missing_frozen_source_never_falls_back_to_unreviewed_video(tmp_path):
    with pytest.raises(ValueError, match='no actual visual evidence'):
        production._boundary_source({'number': 1, 'original_video': {'id': 'video'}, 'selected_media': None}, {}, tmp_path)
