import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import {
    buildStdImageGridPrompts,
    buildStdScenes,
    firstText,
    isPreparedStdTopic,
    normalizeTopicSummary,
    requireStdUser,
} from '@/lib/stdWeb'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'

export const dynamic = 'force-dynamic'

function toProjectSceneRow(scene: any, projectId: string) {
    const sceneNumber = Number(scene?.scene_number || scene?.scene_order || 0)
    const metadata = {
        ...(scene?.metadata && typeof scene.metadata === 'object' ? scene.metadata : {}),
        scene_id: scene?.scene_id || scene?.id || null,
        scene_order: scene?.scene_order || sceneNumber || null,
        duration_seconds: scene?.duration_seconds || scene?.target_duration || null,
        target_duration: scene?.target_duration || null,
        video_prompt_required: scene?.video_prompt_required ?? null,
        scene_summary: scene?.scene_summary || null,
        scene_situation: scene?.scene_situation || null,
        scene_emotion: scene?.scene_emotion || null,
        scene_purpose: scene?.scene_purpose || null,
        retention_hook: scene?.retention_hook || null,
        media_prompt_status: scene?.media_prompt_status || null,
        image_url: scene?.image_url || null,
    }
    return {
        project_id: projectId,
        scene_number: Number.isFinite(sceneNumber) && sceneNumber > 0 ? sceneNumber : 1,
        scene_title: firstText(scene?.scene_title, scene?.scene_summary, scene?.title),
        scene_text: firstText(scene?.scene_text, scene?.narration, scene?.script_excerpt, scene?.description),
        image_prompt: firstText(scene?.image_prompt),
        video_prompt: firstText(scene?.video_prompt),
        shot_hints: Array.isArray(scene?.shot_hints) ? scene.shot_hints : [],
        asset_status: ['missing', 'partial', 'ready', 'needs_review'].includes(String(scene?.asset_status || ''))
            ? String(scene.asset_status)
            : 'missing',
        metadata,
    }
}

async function ensureProjectScenes(projectId: string, topic: any) {
    const { data: existingScenes, error: existingScenesError } = await supabaseAdmin
        .from('std_project_scenes')
        .select('id')
        .eq('project_id', projectId)
        .limit(1)
    if (existingScenesError) throw existingScenesError
    if (existingScenes && existingScenes.length > 0) {
        return { sceneCount: existingScenes.length, inserted: false }
    }

    const scenes = buildStdScenes(topic).map((scene: any) => toProjectSceneRow(scene, projectId))
    if (scenes.length > 0) {
        const { error: scenesError } = await supabaseAdmin.from('std_project_scenes').insert(scenes)
        if (scenesError) throw scenesError
    }
    return { sceneCount: scenes.length, inserted: true }
}

export async function POST(req: Request, { params }: { params: { topicId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const topicId = Number(params.topicId)
    if (!Number.isFinite(topicId)) {
        return NextResponse.json({ success: false, error: 'Invalid topic id' }, { status: 400 })
    }

    const { requester } = auth
    const { data: topicRows, error: topicError } = await supabaseAdmin
        .from('topics_queue')
        .select('*, categories(*)')
        .eq('id', topicId)
        .limit(1)

    if (topicError) return NextResponse.json({ success: false, error: topicError.message }, { status: 500 })
    const topic = (topicRows || [])[0]
    if (!topic) return NextResponse.json({ success: false, error: 'Topic not found' }, { status: 404 })

    const { data: existingProject, error: existingProjectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('topic_queue_id', topicId)
        .limit(1)
        .maybeSingle()
    if (existingProjectError) {
        return NextResponse.json({ success: false, error: existingProjectError.message }, { status: 500 })
    }
    if (existingProject) {
        if (String(existingProject.employee_email || '').toLowerCase() === requester.email.toLowerCase()) {
            try {
                const sceneResult = await ensureProjectScenes(existingProject.id, topic)
                return NextResponse.json({ success: true, project: existingProject, scene_count: sceneResult.sceneCount, recovered: sceneResult.inserted })
            } catch (recoverError: any) {
                return NextResponse.json({ success: false, error: recoverError.message || 'Failed to recover existing project scenes' }, { status: 500 })
            }
        }
        return NextResponse.json({
            success: false,
            error: 'Topic already claimed',
            project_id: existingProject.id,
            employee_email: existingProject.employee_email,
        }, { status: 409 })
    }
    if (!isPreparedStdTopic(topic)) {
        return NextResponse.json({ success: false, error: 'Topic is not ready for STD web claim' }, { status: 409 })
    }

    const imageGridPrompts = buildStdImageGridPrompts(topic)
    const { data: patchedRows, error: patchError } = await supabaseAdmin
        .from('topics_queue')
        .update({
            status: 'assigned',
            assigned_employee_email: requester.email,
            assigned_at: new Date().toISOString(),
        })
        .eq('id', topicId)
        .eq('status', 'pending')
        .select('id')

    if (patchError) return NextResponse.json({ success: false, error: patchError.message }, { status: 500 })
    if (!patchedRows || patchedRows.length === 0) {
        return NextResponse.json({ success: false, error: 'Topic already claimed' }, { status: 409 })
    }

    const summary = normalizeTopicSummary(topic)
    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .insert({
            topic_queue_id: topic.id,
            user_id: requester.user.id,
            employee_email: requester.email,
            title: summary.topic,
            category_id: topic.category_id,
            language: summary.language,
            status: 'claimed',
            assigned_duration_minutes: summary.assigned_duration_minutes,
            estimated_payout: summary.estimated_payout,
            script_style: summary.script_style,
            image_style: summary.image_style,
            source_payload: topic,
            project_payload: {
                script: firstText(topic.pregenerated_script),
                original_worker_script: firstText(topic.pregenerated_script),
                structure: topic.pregenerated_structure || {},
                image_grid_prompts: imageGridPrompts,
                image_style: summary.image_style,
                main_character: topic.progress_payload?.main_character || topic.pregenerated_structure?.main_character || null,
                publish_metadata: topic.publish_metadata || topic.progress_payload?.publish_metadata || {},
                audio_url: topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url || null,
                tts_url: topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url || null,
                tts_provider: null,
                tts_speed: topic.progress_payload?.tts_speed || 1,
                thumbnail_hook_texts: topic.progress_payload?.thumbnail_hook_texts || [],
                thumbnail_hook_reasoning: topic.progress_payload?.thumbnail_hook_reasoning || '',
                thumbnail_image_prompt: topic.progress_payload?.thumbnail_image_prompt || '',
                thumbnail_bg_url: topic.progress_payload?.thumbnail_bg_url || '',
            },
            progress_payload: {
                scene_count: summary.scene_count,
                image_grid_prompt_count: imageGridPrompts.length,
                ready_scene_count: 0,
                main_character: topic.progress_payload?.main_character || topic.pregenerated_structure?.main_character || null,
                has_tts_audio: Boolean(topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url),
                tts_completed: Boolean(topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url),
                tts_provider: null,
                tts_speed: topic.progress_payload?.tts_speed || 1,
                thumbnail_hook_texts: topic.progress_payload?.thumbnail_hook_texts || [],
                thumbnail_hook_reasoning: topic.progress_payload?.thumbnail_hook_reasoning || '',
                thumbnail_image_prompt: topic.progress_payload?.thumbnail_image_prompt || '',
                thumbnail_bg_url: topic.progress_payload?.thumbnail_bg_url || '',
            },
        })
        .select('*')
        .single()

    if (projectError) {
        await supabaseAdmin
            .from('topics_queue')
            .update({
                status: 'pending',
                assigned_employee_email: '',
                assigned_at: null,
            })
            .eq('id', topicId)
            .eq('assigned_employee_email', requester.email)
        return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    }

    await supabaseAdmin
        .from('user_topic_recommendations')
        .update({ is_claimed: true, claimed_at: new Date().toISOString() })
        .eq('topic_queue_id', topicId)

    let sceneCount = 0
    try {
        const sceneResult = await ensureProjectScenes(project.id, topic)
        sceneCount = sceneResult.sceneCount
    } catch (scenesError: any) {
        return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
    }

    try {
        await syncStdProjectToLegacy(project.id)
    } catch (syncError: any) {
        console.error('[STD Claim] legacy sync failed:', syncError?.message)
    }

    return NextResponse.json({ success: true, project, scene_count: sceneCount })
}
