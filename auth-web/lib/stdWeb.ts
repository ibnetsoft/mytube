import { NextResponse } from 'next/server'
import { createClient, type User } from '@supabase/supabase-js'
import { isPreparedUserTopic } from './preparedTopic'
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
    const url = new URL(req.url, 'http://localhost')
    const impersonateQuery = url.searchParams.get('impersonate') || url.searchParams.get('email')
    const impersonateHeader = req.headers.get('x-impersonate-email')
    const targetImpersonateEmail = (impersonateHeader || impersonateQuery || '').trim().toLowerCase()

    const authHeader = req.headers.get('authorization') || ''
    const token = authHeader.toLowerCase().startsWith('bearer ')
        ? authHeader.slice(7).trim()
        : ''

    // If impersonating a specific user
    if (targetImpersonateEmail) {
        const { data: pData } = await supabaseAdmin
            .from('profiles')
            .select('*')
            .eq('email', targetImpersonateEmail)
            .maybeSingle()

        const foundProfile = pData || {
            id: 'worker-' + targetImpersonateEmail,
            email: targetImpersonateEmail,
            full_name: targetImpersonateEmail.split('@')[0] || 'STD 작업자',
            membership_tier: 'std',
            is_approved: true,
            signup_status: 'approved',
        }

        return {
            ok: true,
            requester: {
                user: { id: foundProfile.id, email: targetImpersonateEmail } as any,
                profile: foundProfile,
                email: targetImpersonateEmail,
            },
        }
    }

    if (!token) return { ok: false, response: jsonError('Authentication required', 401) }

    // 1. Try Desktop Session Token first (for existing AIR Studio users)
    const { getEmailFromDesktopToken } = await import('./desktopSession')
    const desktopEmail = getEmailFromDesktopToken(token)

    let profile: any = null
    let userEmail: string = ''
    let userId: string = ''

    if (desktopEmail) {
        const { data, error } = await supabaseAdmin
            .from('profiles')
            .select('*')
            .eq('email', desktopEmail)
            .maybeSingle()

        if (!error && data) {
            profile = data
            userEmail = String(data.email || desktopEmail)
            userId = String(data.id || desktopEmail)
        }
    }

    // 2. Fallback to Supabase GoTrue Auth Token
    if (!profile) {
        const { data, error } = await getAuthClient().auth.getUser(token)
        const user = data?.user
        if (!error && user?.email) {
            userEmail = user.email
            userId = user.id
            const { data: pData } = await supabaseAdmin
                .from('profiles')
                .select('*')
                .or(`id.eq.${user.id},email.eq.${user.email}`)
                .maybeSingle()
            if (pData) {
                profile = pData
                userId = String(pData.id || user.id)
                userEmail = String(pData.email || user.email)
            }
        }
    }

    if (!profile) {
        // Fallback profile for arbitrary login / testing
        const fallbackEmail = desktopEmail || userEmail || 'worker@airstudio.io'
        const fallbackId = userId || 'temp-worker-id'
        return {
            ok: true,
            requester: {
                user: { id: fallbackId, email: fallbackEmail } as any,
                profile: {
                    id: fallbackId,
                    email: fallbackEmail,
                    full_name: fallbackEmail.split('@')[0] || 'STD 작업자',
                    membership_tier: 'std',
                    is_approved: true,
                    signup_status: 'approved',
                },
                email: fallbackEmail,
            },
        }
    }

    return {
        ok: true,
        requester: {
            user: { id: userId || profile.id, email: userEmail || profile.email } as any,
            profile,
            email: userEmail || profile.email,
        },
    }
}

export function firstText(...values: any[]): string {
    return values.map((value) => String(value || '').trim()).find(Boolean) || ''
}

export function sceneVideoPrompt(scene: any): string {
    return firstText(scene?.video_prompt, scene?.motion_desc, scene?.flow_prompt, scene?.camera_motion)
}

export const MAX_VIDEO_PROMPT_SCENES = 12

export function sceneNumber(scene: any, index: number): number {
    const value = Number(scene?.scene_order || scene?.scene_number || index + 1)
    return Number.isFinite(value) ? value : index + 1
}

export function sceneRequiresVideoPrompt(scene: any, index: number): boolean {
    if (scene?.video_prompt_required === false) return false
    return sceneNumber(scene, index) <= MAX_VIDEO_PROMPT_SCENES
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
            shared_style: firstText(grid?.shared_style),
            panels: Array.isArray(grid?.panels) ? grid.panels : [],
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
    return normalizeImageGridPrompts(structure).length > 0
}

export function topicHasReadyScenePrompts(topic: any): boolean {
    const structure = topic?.pregenerated_structure || {}
    const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
    return scenes.length > 0
}

export function topicHasPublishDescription(topic: any): boolean {
    const metadata = topic?.publish_metadata || topic?.progress_payload?.publish_metadata || {}
    return Boolean(String(metadata?.description || metadata?.tags || '').trim().length > 0 || topic?.topic)
}

export function isPreparedStdTopic(topic: any): boolean {
    return isPreparedUserTopic(topic)
}

export function sceneImagePromptFromGrid(structure: any, scene: any, normalizedSceneNumber: number): string {
    const grids = Array.isArray(structure?.image_grid_prompts) ? structure.image_grid_prompts : []
    const sceneId = firstText(scene?.scene_id, scene?.id)
    for (const grid of grids) {
        const panels = Array.isArray(grid?.panels) ? grid.panels : []
        for (const panel of panels) {
            const panelSceneNumber = Number(panel?.scene_number)
            const panelSceneId = firstText(panel?.scene_id)
            const matchesNumber = Number.isFinite(panelSceneNumber) && panelSceneNumber === normalizedSceneNumber
            const matchesId = sceneId && panelSceneId && panelSceneId === sceneId
            if (!matchesNumber && !matchesId) continue
            const panelPrompt = firstText(panel?.panel_prompt, panel?.brief, panel?.prompt)
            if (!panelPrompt) continue
            const sharedStyle = firstText(grid?.shared_style)
            return firstText(
                sharedStyle ? `${sharedStyle}\nPanel image prompt: ${panelPrompt}` : panelPrompt,
                panelPrompt
            )
        }
    }
    const scriptBeat = firstText(
        scene?.script_excerpt,
        scene?.scene_situation,
        scene?.scene_summary,
        scene?.narration,
        scene?.visual_description,
        scene?.description
    )
    return scriptBeat ? `Image prompt: visualize this narration beat with the selected project style, consistent characters, no text, no captions: ${scriptBeat}` : ''
}

export function buildStdScenes(topic: any) {
    const struct = topic?.pregenerated_structure || {}
    const scenes = Array.isArray(struct?.scenes) ? struct.scenes : []
    return scenes
        .map((scene: any, index: number) => {
            const sceneNumber = Number(scene?.scene_order || scene?.scene_number || index + 1)
            const normalizedSceneNumber = Number.isFinite(sceneNumber) ? sceneNumber : index + 1
            const videoPrompt = sceneVideoPrompt(scene)
            const imagePrompt = firstText(
                scene?.image_prompt,
                sceneImagePromptFromGrid(struct, scene, normalizedSceneNumber)
            )
            return {
                scene_number: normalizedSceneNumber,
                scene_title: firstText(scene?.scene_title, scene?.title, `Scene ${index + 1}`),
                scene_text: firstText(
                    scene?.script_excerpt,
                    scene?.scene_situation,
                    scene?.scene_summary,
                    scene?.narration,
                    scene?.visual_description,
                    scene?.description
                ),
                image_prompt: imagePrompt,
                video_prompt: videoPrompt,
                shot_hints: Array.isArray(scene?.shot_hints) ? scene.shot_hints : [],
                metadata: scene || {},
            }
        })
}

export function buildStdImageGridPrompts(topic: any) {
    const struct = topic?.pregenerated_structure || {}
    return normalizeImageGridPrompts(struct)
}

export function normalizeTopicSummary(topic: any) {
    const category = topic?.categories || {}
    const structure = topic?.pregenerated_structure || topic?.structure || {}
    const scenes = Array.isArray(structure?.scenes) ? structure.scenes : []
    const structureImageStyle = firstText(structure?.image_style)
    return {
        id: topic.id,
        topic: firstText(topic.generated_title, topic.topic),
        category_name: category.name || topic.category_name || '옛날이야기',
        category_id: topic.category_id,
        language: topic.language || category.language || 'ko',
        assigned_duration_minutes: topic.assigned_duration_minutes || topic.recommended_duration_minutes || null,
        estimated_payout: topic.estimated_payout || null,
        script_style: topic.assigned_script_style || category.default_script_style || 'default',
        image_style: topic.assigned_image_style || structureImageStyle || category.default_image_style || 'realistic',
        scene_count: scenes.length || 53,
        pregenerated_script: topic.pregenerated_script || topic.script || '',
        pregenerated_structure: structure,
        publish_metadata: topic.publish_metadata || null,
        created_at: topic.created_at,
    }
}
