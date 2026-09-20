from pathlib import Path
import unittest

GLOBAL_SETTINGS_ROUTE = Path("auth-web/app/api/admin/settings/global/route.ts").read_text(encoding="utf-8")
GCS_STORAGE_LIB = Path("auth-web/lib/gcsStorage.ts").read_text(encoding="utf-8")
INIT_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/init/route.ts").read_text(encoding="utf-8")
COMPLETE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/complete/route.ts").read_text(encoding="utf-8")
FILE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/file/route.ts").read_text(encoding="utf-8")
UPLOAD_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/assets/upload/route.ts").read_text(encoding="utf-8")
STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")
DASHBOARD_CONTENT = Path("auth-web/components/DashboardContent.tsx").read_text(encoding="utf-8")
STD_RENDER_QUEUE = Path("auth-web/lib/stdRenderQueue.ts").read_text(encoding="utf-8")
ADMIN_RENDER_QUEUE = Path("auth-web/app/api/admin/render-queue/route.ts").read_text(encoding="utf-8")
CONFIG_PY = Path("config.py").read_text(encoding="utf-8")
WEB_ADMIN_CLIENT = Path("services/web_admin_client.py").read_text(encoding="utf-8")
REMOTE_DRIVE_WORKER = Path("remote_drive_worker.py").read_text(encoding="utf-8")
ENV_EXAMPLE = Path(".env.example").read_text(encoding="utf-8")
AUTH_WEB_ENV_EXAMPLE = Path("auth-web/.env.example").read_text(encoding="utf-8")
TTS_GENERATE_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts").read_text(encoding="utf-8")
SEGMENT_CACHE_LIB = Path("auth-web/lib/stdSegmentAudioCache.ts").read_text(encoding="utf-8")
PROJECT_DETAIL_ROUTE = Path("auth-web/app/api/std/projects/[projectId]/route.ts").read_text(encoding="utf-8")
STD_MEDIA_LOADING = Path("auth-web/lib/stdMediaLoading.ts").read_text(encoding="utf-8")


class TestGcsStorageIntegrationContract(unittest.TestCase):
    def test_global_settings_supports_gcs(self):
        self.assertIn("'gcs_bucket_name'", GLOBAL_SETTINGS_ROUTE)
        self.assertIn("'gcs_project_id'", GLOBAL_SETTINGS_ROUTE)
        self.assertIn("'gcs_client_email'", GLOBAL_SETTINGS_ROUTE)
        self.assertIn("'gcs_private_key'", GLOBAL_SETTINGS_ROUTE)

    def test_gcs_storage_library_has_core_functions(self):
        self.assertIn("export async function getGcsConfig", GCS_STORAGE_LIB)
        self.assertIn("export async function isGcsConfiguredAsync", GCS_STORAGE_LIB)
        self.assertIn("export async function createGcsSignedReadUrl", GCS_STORAGE_LIB)
        self.assertIn("export async function uploadGcsBuffer", GCS_STORAGE_LIB)
        self.assertIn("export async function downloadGcsObject", GCS_STORAGE_LIB)
        self.assertIn("export async function archiveSupabaseAssetToGcs", GCS_STORAGE_LIB)
        self.assertIn("export function isGcsStorageConfigured", GCS_STORAGE_LIB)

    def test_asset_init_route_keeps_supabase_primary_and_gcs_secondary(self):
        self.assertIn("storage_provider: 'supabase'", INIT_ROUTE)
        self.assertIn("secondary_storage_provider: isGcsStorageConfigured() ? 'gcs' : null", INIT_ROUTE)

    def test_asset_complete_and_upload_routes_archive_to_gcs(self):
        self.assertIn("archiveSupabaseAssetToGcs(project, asset)", COMPLETE_ROUTE)
        self.assertIn("uploadGcsBuffer", UPLOAD_ROUTE)

    def test_asset_file_streaming_route_priority(self):
        # 1st Supabase -> 2nd GCS (Range streaming supported) -> 3rd Drive
        self.assertIn("supabaseAdmin.storage.from(storageBucket).download(storagePath)", FILE_ROUTE)
        self.assertIn("downloadGcsObject", FILE_ROUTE)
        self.assertIn("downloadGcsObjectViaSignedUrl", FILE_ROUTE)
        self.assertIn("downloadStdDriveFile", FILE_ROUTE)
        self.assertIn("206", FILE_ROUTE)
        self.assertIn("Content-Range", FILE_ROUTE)

    def test_tts_narration_and_segment_audio_archiving(self):
        self.assertIn("uploadGcsBuffer", TTS_GENERATE_ROUTE)
        self.assertIn("isGcsConfiguredAsync", TTS_GENERATE_ROUTE)
        self.assertIn("uploadGcsBuffer", SEGMENT_CACHE_LIB)
        self.assertIn("isGcsConfiguredAsync", SEGMENT_CACHE_LIB)

    def test_dashboard_ui_shows_gcs_settings_and_status(self):
        self.assertIn("gcs_bucket_name", DASHBOARD_CONTENT)
        self.assertIn("gcs_project_id", DASHBOARD_CONTENT)
        self.assertIn("gcs_client_email", DASHBOARD_CONTENT)
        self.assertIn("gcs_private_key", DASHBOARD_CONTENT)
        self.assertIn("스토리지 (GCS/Drive)", DASHBOARD_CONTENT)
        self.assertIn("연동 완료 (GCS Active)", DASHBOARD_CONTENT)

    def test_std_render_queue_generates_gcs_manifest_and_async_builder(self):
        self.assertIn("async function buildDriveFolderRenderConfig", STD_RENDER_QUEUE)
        self.assertIn("async function storageManifestFields", STD_RENDER_QUEUE)
        self.assertIn("gcs_signed_url: gcsSignedUrl", STD_RENDER_QUEUE)
        self.assertIn("uploadGcsBuffer", STD_RENDER_QUEUE)
        # Verify scene archiving uses GCS and optional Drive
        self.assertIn("ensureStdGeneratedSceneAssetsArchived", STD_RENDER_QUEUE)
        self.assertIn("worker_generated_supabase_then_gcs_archive", STD_RENDER_QUEUE)

    def test_admin_render_queue_supports_direct_http_links(self):
        self.assertIn("if (fileId.startsWith('http://') || fileId.startsWith('https://')) return fileId", ADMIN_RENDER_QUEUE)
        self.assertIn("result_view_link: metadata.result_public_url || buildDriveViewLink(row?.result_file_id)", ADMIN_RENDER_QUEUE)

    def test_config_py_and_web_admin_client(self):
        self.assertIn("GCS_BUCKET_NAME", CONFIG_PY)
        self.assertIn("GCS_PROJECT_ID", CONFIG_PY)
        self.assertIn("GCS_CLIENT_EMAIL", CONFIG_PY)
        self.assertIn("GCS_PRIVATE_KEY", CONFIG_PY)
        self.assertIn('"sys_api_gcs_bucket_name": "GCS_BUCKET_NAME"', WEB_ADMIN_CLIENT)
        self.assertIn('"sys_api_gcs_project_id": "GCS_PROJECT_ID"', WEB_ADMIN_CLIENT)

    def test_remote_drive_worker_has_three_tier_storage(self):
        self.assertIn("def _download_from_supabase_storage", REMOTE_DRIVE_WORKER)
        self.assertIn("def _download_from_gcs_storage", REMOTE_DRIVE_WORKER)
        self.assertIn("def _upload_to_supabase_storage", REMOTE_DRIVE_WORKER)
        self.assertIn("def _upload_to_gcs_storage", REMOTE_DRIVE_WORKER)
        self.assertIn("# 1st Priority: Supabase Storage", REMOTE_DRIVE_WORKER)
        self.assertIn("# 2nd Priority: Google Cloud Storage", REMOTE_DRIVE_WORKER)
        self.assertIn("# 3rd Priority: Google Drive", REMOTE_DRIVE_WORKER)
        self.assertIn('"storage_direct"', REMOTE_DRIVE_WORKER)

    def test_env_examples_contain_gcs_variables(self):
        self.assertIn("GCS_BUCKET_NAME=", ENV_EXAMPLE)
        self.assertIn("GCS_PROJECT_ID=", ENV_EXAMPLE)
        self.assertIn("GCS_CLIENT_EMAIL=", ENV_EXAMPLE)
        self.assertIn("GCS_PRIVATE_KEY=", ENV_EXAMPLE)

        self.assertIn("GCS_BUCKET_NAME=", AUTH_WEB_ENV_EXAMPLE)
        self.assertIn("GCS_PROJECT_ID=", AUTH_WEB_ENV_EXAMPLE)
        self.assertIn("GCS_CLIENT_EMAIL=", AUTH_WEB_ENV_EXAMPLE)
        self.assertIn("GCS_PRIVATE_KEY=", AUTH_WEB_ENV_EXAMPLE)

    def test_direct_storage_url_and_fallback_hierarchy(self):
        # 1st GCS signed/public -> 2nd Supabase public CDN (for existing projects) -> 3rd proxy
        self.assertIn("metadata?.gcs_signed_url", STD_MEDIA_LOADING)
        self.assertIn("metadata?.storage_public_url", STD_MEDIA_LOADING)
        self.assertIn("resolveFastAssetUrl", STD_MEDIA_LOADING)

    def test_project_detail_route_enriches_gcs_and_supabase_direct_cdn(self):
        self.assertIn("assetFastMediaUrl", PROJECT_DETAIL_ROUTE)
        self.assertIn("gcs_signed_url", PROJECT_DETAIL_ROUTE)
        self.assertIn("createGcsSignedReadUrl", PROJECT_DETAIL_ROUTE)
        self.assertIn("storagePublicUrl", PROJECT_DETAIL_ROUTE)

    def test_std_page_prioritizes_direct_cdn_urls(self):
        self.assertIn("sanitizeAssetUrl(directStorageUrl(imageAsset)) || sanitizeAssetUrl(scene?.image_url", STD_PAGE)
        self.assertIn("sanitizeAssetUrl(directStorageUrl(thumbnailAsset))", STD_PAGE)


if __name__ == "__main__":
    unittest.main()

