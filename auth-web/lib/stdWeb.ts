import { NextResponse } from 'next/server'
import { createClient, type User } from '@supabase/supabase-js'
import { supabaseAdmin } from './supabaseAdmin'

const getAuthClient = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false, autoRefreshToken: false } }
)

export type StdRequester = {
    user: User
    profile: any
    email: string
}

export type StdAuthResult =
    | { ok: true; requester: StdRequester }
    | { ok: false; response: NextResponse }

function jsonError(error: string, status: number) {
    return NextResponse.json({ success: false, error }, { status })
}

export async function requireStdUser(req: Request): Promise<StdAuthResult> {
    const authHeader = req.headers.get('authorization') || ''
    const token = authHeader.toLowerCase().startsWith('bearer ')
        ? authHeader.slice(7).trim()
        : ''
    if (!token) return { ok: false, response: jsonError('Authentication required', 401) }

    const { data, error } = await getAuthClient().auth.getUser(token)
    const user = data.user
    if (error || !user?.email) return { ok: false, response: jsonError('Invalid session', 401) }

    const { data: profile, error: profileError } = await supabaseAdmin
        .from('profiles')
        .select('id,email,membership,membership_tier,is_approved,preferred_languages,preferred_video_length,preferred_category_ids,full_name')
        .eq('id', user.id)
        .maybeSingle()

    if (profileError || !profile) return { ok: false, response: jsonError('Profile not found', 404) }
    if (profile.is_approved !== true) return { ok: false, response: jsonError('Account is not approved', 403) }

    const membership = String(profile.membership_tier || profile.membership || 'std').toLowerCase()
    if (!['std', 'standard'].includes(membership)) {
        return { ok: false, response: jsonError('STD membership required', 403) }
    }

    return {
        ok: true,
        requester: {
            user,
            profile,
            email: String(profile.email || user.email),
        },
    }
}

export function firstText(...values: any[]): string {
    return values.map((value) => String(value || '').trim()).find(Boolean) || ''
}

export function sceneVideoPrompt(scene: any): string {
    return firstText(scene?.video_prompt, scene?.motion_desc, scene?.flow_prompt, scene?.camera_motion)
}

export function normalizeImageGridPrompts(structure: any): any[] {
    const grids = Array.isArray(structure?.image_grid_prompts) ? structure.image_grid_prompts : []
    return grids
        .map((grid: any, index: number) => ({
            grid_number: grid?.grid_number || index + 1,
            template: grid?.template || 'strict_2x2_v1',
            scene_numbers: Array.isArray(grid?.scene_numbers) ? grid.scene_numbers : [],
            scene_ids: Array.isArray(grid?.scene_ids) ? grid.scene_ids : [],
            panel_count: Number(grid?.panel_count || 4),
            prompt: firstText(grid?.prompt, grid?.grid_prompt),
        }))
        .filter((grid: any) =>
            grid.prompt
            && grid.panel_count === 4
            && grid.scene_numbers.length === 4
        )
}

export function topicHasReadyImageGridPrompts(topic: any): boolean {
    const structure = topic?.pregenerated_structure || {}
    const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
    if (scenes.length < 4) return false
    if (String(structure?.image_grid_prompt_status || '') !== 'ready') return false

    const expectedGridCount = Math.floor(scenes.length / 4) + (scenes.length % 4 ? 1 : 0)
    const grids = normalizeImageGridPrompts(structure)
    if (grids.length !== expectedGridCount) return false

    const promptSet = new Set<string>()
    const covered = new Set<string>()
    for (const grid of grids) {
        if (promptSet.has(grid.prompt)) return false
        promptSet.add(grid.prompt)
        for (const sceneNumber of grid.scene_numbers) covered.add(String(sceneNumber))
    }

    return scenes.every((scene: any, index: number) => {
        const sceneNumber = Number(scene?.scene_order || scene?.scene_number || index + 1)
        return covered.has(String(Number.isFinite(sceneNumber) ? sceneNumber : index + 1))
    })
}

export function topicHasReadyScenePrompts(topic: any): boolean {
    const structure = topic?.pregenerated_structure || {}
    const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
    if (topic?.pregenerated_structure_status !== 'ready' || scenes.length === 0) return false
    if (String(structure?.media_prompt_status || '') !== 'ready') return false
    const seenVideoPrompts = new Set<string>()
    const scenesReady = scenes.every((scene: any) => {
        const videoPrompt = sceneVideoPrompt(scene)
        if (!videoPrompt) return false
        if (seenVideoPrompts.has(videoPrompt)) return false
        seenVideoPrompts.add(videoPrompt)
        return (
        String(scene?.media_prompt_status || '') === 'ready'
            && videoPrompt
        )
    })
    return scenesReady && topicHasReadyImageGridPrompts(topic)
}

export function topicHasPublishDescription(topic: any): boolean {
    const metadata = topic?.publish_metadata || topic?.progress_payload?.publish_metadata || {}
    return String(metadata?.description || '').trim().length > 0
}

export function isPreparedStdTopic(topic: any): boolean {
    return Boolean(topic?.status === 'pending'
        && firstText(topic?.generated_title, topic?.topic)
        && topic?.category_id != null
        && topic?.pregenerated_script_status === 'ready'
        && firstText(topic?.pregenerated_script)
        && topicHasReadyScenePrompts(topic)
        && topicHasPublishDescription(topic))
}

export function buildStdScenes(topic: any) {
    const scenes = Array.isArray(topic?.pregenerated_structure?.scenes)
        ? topic.pregenerated_structure.scenes
        : []
    return scenes
        .map((scene: any, index: number) => {
            const sceneNumber = Number(scene?.scene_order || scene?.scene_number || index + 1)
            return {
                scene_number: Number.isFinite(sceneNumber) ? sceneNumber : index + 1,
                scene_title: firstText(scene?.scene_title, scene?.title, `Scene ${index + 1}`),
                scene_text: firstText(
                    scene?.scene_situation,
                    scene?.scene_summary,
                    scene?.narration,
                    scene?.visual_description,
                    scene?.description
                ),
                image_prompt: '',
                video_prompt: sceneVideoPrompt(scene),
                shot_hints: Array.isArray(scene?.shot_hints) ? scene.shot_hints : [],
                metadata: scene || {},
            }
        })
        .filter((scene: any) => scene.video_prompt)
}

export function buildStdImageGridPrompts(topic: any) {
    return normalizeImageGridPrompts(topic?.pregenerated_structure || {})
}

export function normalizeTopicSummary(topic: any) {
    const category = topic?.categories || {}
    const structureImageStyle = firstText(topic?.pregenerated_structure?.image_style)
    return {
        id: topic.id,
        topic: firstText(topic.generated_title, topic.topic),
        category_name: category.name || '',
        category_id: topic.category_id,
        language: topic.language || category.language || 'ko',
        assigned_duration_minutes: topic.assigned_duration_minutes || topic.recommended_duration_minutes || null,
        estimated_payout: topic.estimated_payout || null,
        script_style: topic.assigned_script_style || category.default_script_style || 'default',
        image_style: topic.assigned_image_style || structureImageStyle || category.default_image_style || 'realistic',
        scene_count: Array.isArray(topic?.pregenerated_structure?.scenes) ? topic.pregenerated_structure.scenes.length : 0,
        created_at: topic.created_at,
    }
}
