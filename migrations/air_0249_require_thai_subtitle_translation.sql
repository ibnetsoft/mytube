-- AIR-0249: Require Thai subtitle translation as a default deliverable for
-- new Hermes topic generation and topic repair.
--
-- This updates the service-only quality policy consumed by workers. It does
-- not change schema. Runtime workers must treat Thai subtitle translation as
-- incomplete unless every Korean subtitle block has a matching Thai block with
-- the same index/source_text and a non-empty translated_text.

UPDATE public.quality_policies
SET
    version = version + 1,
    policy = jsonb_set(
        policy,
        '{subtitle_translation}',
        '{
          "enabled": true,
          "default_language": "th",
          "required_for_new_topics": true,
          "required_for_repairs": true,
          "storage_path": "project_payload.subtitle_translations.th.blocks",
          "preserve_block_count": true,
          "preserve_index": true,
          "preserve_source_text": true,
          "prohibit_merge_split_summary": true,
          "prohibit_empty_translation": true,
          "block_completion_on_missing_translation": true,
          "purpose": "Thai reviewer support for dialogue/narration verification"
        }'::jsonb,
        true
    ),
    updated_by = 'air_0249_require_thai_subtitle_translation',
    updated_at = now()
WHERE policy_key = 'hermes_generation';
