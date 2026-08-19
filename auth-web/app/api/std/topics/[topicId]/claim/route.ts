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
                structure: topic.pregenerated_structure || {},
                image_grid_prompts: imageGridPrompts,
                publish_metadata: topic.publish_metadata || topic.progress_payload?.publish_metadata || {},
                audio_url: topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url || null,
                tts_url: topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url || null,
                tts_provider: (topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url) ? 'voicebox' : null,
            },
            progress_payload: {
                scene_count: summary.scene_count,
                image_grid_prompt_count: imageGridPrompts.length,
                ready_scene_count: 0,
                has_tts_audio: Boolean(topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url),
                tts_completed: Boolean(topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url),
                tts_provider: (topic.pregenerated_audio_url || topic.progress_payload?.pregenerated_audio_url) ? 'voicebox' : null,
            },
        })
        .select('*')
        .single()

    if (projectError) {
        return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    }

    const scenes = buildStdScenes(topic).map((scene: any) => ({
        ...scene,
        project_id: project.id,
    }))

    if (scenes.length > 0) {
        const { error: scenesError } = await supabaseAdmin.from('std_project_scenes').insert(scenes)
        if (scenesError) {
            return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
        }
    }

    try {
        await syncStdProjectToLegacy(project.id)
    } catch (syncError: any) {
        console.error('[STD Claim] legacy sync failed:', syncError?.message)
    }

    return NextResponse.json({ success: true, project, scene_count: scenes.length })
}
