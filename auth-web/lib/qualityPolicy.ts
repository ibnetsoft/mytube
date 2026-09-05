export const QUALITY_POLICY_KEY = 'hermes_generation'

export const DEFAULT_QUALITY_POLICY = {
    schema_version: 1,
    topic: { enabled: true, min_title_chars: 12 },
    plan: { enabled: true, min_scenes: 1, require_media_status_ready: true },
    script: {
        enabled: true, min_quality_score: 78, min_hangul_chars: 1000,
        max_latin_ratio: 0.05, max_repeated_paragraph_opener: 2,
        prohibit_fallback: true, prohibit_off_category: true,
    },
    media: {
        enabled: true, min_image_prompt_chars: 120, min_video_prompt_chars: 260,
        max_video_prompt_scenes: 12, required_camera_movements: 1,
        require_video_guardrails: true, prohibit_duplicate_prompts: true,
        require_image_grids: true,
    },
    publish: {
        enabled: true, min_description_chars: 120,
        require_language_match: true, prohibit_internal_terms: true,
    },
    delivery: {
        enabled: true, require_all_prior_stages: true,
        require_quality_report_pass: true, block_scene_count_mismatch: true,
    },
} as const

type JsonObject = Record<string, unknown>
const object = (value: unknown): JsonObject => value && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {}
const bool = (value: unknown, fallback: boolean) => typeof value === 'boolean' ? value : fallback
const number = (value: unknown, fallback: number, min: number, max: number) => {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : fallback
}

export function normalizeQualityPolicy(value: unknown) {
    const root = object(value)
    const topic = object(root.topic)
    const plan = object(root.plan)
    const script = object(root.script)
    const media = object(root.media)
    const publish = object(root.publish)
    const delivery = object(root.delivery)
    return {
        schema_version: 1,
        topic: { enabled: bool(topic.enabled, true), min_title_chars: number(topic.min_title_chars, 12, 1, 300) },
        plan: {
            enabled: bool(plan.enabled, true), min_scenes: number(plan.min_scenes, 1, 1, 500),
            require_media_status_ready: bool(plan.require_media_status_ready, true),
        },
        script: {
            enabled: bool(script.enabled, true), min_quality_score: number(script.min_quality_score, 78, 0, 100),
            min_hangul_chars: number(script.min_hangul_chars, 1000, 0, 200000),
            max_latin_ratio: number(script.max_latin_ratio, 0.05, 0, 1),
            max_repeated_paragraph_opener: number(script.max_repeated_paragraph_opener, 2, 1, 100),
            prohibit_fallback: true,
            prohibit_off_category: bool(script.prohibit_off_category, true),
        },
        media: {
            enabled: bool(media.enabled, true), min_image_prompt_chars: number(media.min_image_prompt_chars, 120, 1, 10000),
            min_video_prompt_chars: number(media.min_video_prompt_chars, 260, 1, 10000),
            max_video_prompt_scenes: number(media.max_video_prompt_scenes, 12, 0, 500),
            required_camera_movements: number(media.required_camera_movements, 1, 0, 10),
            require_video_guardrails: bool(media.require_video_guardrails, true),
            prohibit_duplicate_prompts: bool(media.prohibit_duplicate_prompts, true),
            require_image_grids: bool(media.require_image_grids, true),
        },
        publish: {
            enabled: bool(publish.enabled, true), min_description_chars: number(publish.min_description_chars, 120, 0, 10000),
            require_language_match: bool(publish.require_language_match, true),
            prohibit_internal_terms: bool(publish.prohibit_internal_terms, true),
        },
        delivery: {
            enabled: bool(delivery.enabled, true), require_all_prior_stages: true,
            require_quality_report_pass: true,
            block_scene_count_mismatch: bool(delivery.block_scene_count_mismatch, true),
        },
    }
}
