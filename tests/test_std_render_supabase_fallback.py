from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = (ROOT / "auth-web" / "lib" / "stdRenderQueue.ts").read_text(encoding="utf-8")


def test_std_render_manifest_records_storage_fallback_locations():
    assert "function storageSourceForAsset(asset: any)" in QUEUE
    assert "supabase_bucket: audioStorage.bucket" in QUEUE
    assert "supabase_bucket: assetStorage.bucket" in QUEUE
    assert "supabase_bucket: bgmStorage.bucket" in QUEUE
    assert "supabase_bucket: sfxStorage.bucket" in QUEUE
    assert "supabase_config: { bucket: 'content-assets', path: configStoragePath }" in QUEUE
    assert ".upload(configStoragePath" in QUEUE
