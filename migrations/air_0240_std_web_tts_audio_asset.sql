-- AIR-0240: Allow web STD generated TTS audio assets.
--
-- 0239 created std_project_assets before web-side TTS existed, so the
-- asset_type check did not include audio. Keep the storage model unchanged:
-- generated audio is still a Drive file reference recorded in std_project_assets.

ALTER TABLE public.std_project_assets
    DROP CONSTRAINT IF EXISTS std_project_assets_type_check;

ALTER TABLE public.std_project_assets
    ADD CONSTRAINT std_project_assets_type_check CHECK (
        asset_type IN ('image', 'video', 'audio', 'thumbnail', 'original', 'other')
    );
