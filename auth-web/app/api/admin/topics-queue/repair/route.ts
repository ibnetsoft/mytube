import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function toBoundedInt(value: any, min: number, max: number, fallback: number): number {
    const parsed = Number.parseInt(String(value ?? ''), 10)
    if (!Number.isFinite(parsed)) return fallback
    return Math.max(min, Math.min(max, parsed))
}

function objectOrEmpty(value: any): Record<string, any> {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

export async function POST(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json().catch(() => ({}))
        const topicId = String(body.topicId || body.topic_id || body.id || '').trim()
        if (!topicId) {
            return NextResponse.json({ error: 'Missing topicId' }, { status: 400 })
        }

        const targetMinutes = toBoundedInt(body.targetMinutes ?? body.target_minutes, 1, 180, 15)
        const targetSceneCount = toBoundedInt(body.targetSceneCount ?? body.target_scene_count, 1, 400, 53)
        const targetDurationSeconds = targetMinutes * 60
        const now = new Date().toISOString()
        const supabase = getAdmin()

        const { data: topic, error: topicError } = await supabase
            .from('topics_queue')
            .select(`
                id,
                category_id,
                topic,
                generated_title,
                status,
                assigned_at,
                assigned_duration_minutes,
                assigned_script_style,
                assigned_image_style,
                language,
                progress_payload,
                publish_metadata,
                benchmark_analysis,
                pregenerated_structure,
                pregenerated_script,
                narrative_blueprint,
                script_quality_report
            `)
            .eq('id', topicId)
            .maybeSingle()

        if (topicError) throw topicError
        if (!topic) {
            return NextResponse.json({ error: 'Topic not found' }, { status: 404 })
        }
        if (topic.status !== 'pending' || String(topic.assigned_at || '').trim()) {
            return NextResponse.json({ error: 'Only unclaimed pending topics can be repaired' }, { status: 409 })
        }

        const progressPayload = objectOrEmpty(topic.progress_payload)
        const previousStructure = objectOrEmpty(topic.pregenerated_structure)
        const previousScript = String(topic.pregenerated_script || '').trim()
        const titleGeneration = objectOrEmpty(progressPayload.title_generation)
        const uploadTitle = String(topic.generated_title || titleGeneration.generated_title || topic.topic || '').trim()
        const benchmarkAnalysis = objectOrEmpty(topic.benchmark_analysis).script_analysis
            ? objectOrEmpty(topic.benchmark_analysis)
            : objectOrEmpty(progressPayload.benchmark_analysis)

        const jobPayload = {
            topic_queue_id: topicId,
            topic: uploadTitle || String(topic.topic || '').trim(),
            original_topic: String(topic.topic || '').trim(),
            upload_title: uploadTitle,
            title_generation: titleGeneration,
            repair_mode: true,
            repair_requested_by: requester.user.email,
            repair_requested_at: now,
            repair_source_script: previousScript,
            previous_structure: previousStructure,
            previous_scene_count: Array.isArray(previousStructure.scenes)
                ? previousStructure.scenes.length
                : Number(previousStructure.scene_count || 0),
            target_duration_seconds: targetDurationSeconds,
            target_scene_count: targetSceneCount,
            script_style: topic.assigned_script_style || 'default',
            image_style: topic.assigned_image_style || previousStructure.image_style || '',
            language: topic.language || 'ko',
            benchmark_analysis: Object.keys(benchmarkAnalysis).length ? benchmarkAnalysis : null,
            narration_pace: 'senior',
            require_scene_planner_success: true,
            repair_instruction: [
                'Repair this incomplete prepared topic for senior-paced narration.',
                'Reuse the existing title, story premise, and useful draft details, but regenerate the scene plan and script as a complete longform video.',
                `Target duration: ${targetMinutes} minutes (${targetDurationSeconds} seconds).`,
                `Target scene count: exactly ${targetSceneCount} scenes.`,
                'Do not include planning notes, prompt labels, beat labels, camera instructions, or meta text inside the final narration script.',
                'Regenerate image-grid prompts from the repaired scene plan so every scene is covered.'
            ].join(' ')
        }

        const { data: job, error: jobError } = await supabase
            .from('remote_hermes_queue')
            .insert({
                job_type: 'script_plan_generate',
                category_id: topic.category_id ? String(topic.category_id) : null,
                payload: jobPayload,
                status: 'pending',
            })
            .select('id, job_type, status, created_at')
            .single()

        if (jobError) throw jobError

        const nextProgressPayload = {
            ...progressPayload,
            prepared_topic_ready: false,
            repair_status: 'queued',
            repair_requested_by: requester.user.email,
            repair_requested_at: now,
            repair_target_duration_minutes: targetMinutes,
            repair_target_scene_count: targetSceneCount,
            repair_source_script_chars: previousScript.length,
            repair_job_id: job?.id || null,
            pregenerated_structure_status: 'queued',
            pregenerated_script_status: 'queued',
            publish_metadata: null,
        }

        const { error: updateError } = await supabase
            .from('topics_queue')
            .update({
                assigned_duration_minutes: targetMinutes,
                total_scenes: targetSceneCount,
                pregenerated_structure_status: 'queued',
                pregenerated_script_status: 'queued',
                publish_metadata: null,
                progress_payload: nextProgressPayload,
            })
            .eq('id', topicId)

        if (updateError) throw updateError

        await supabase
            .from('user_topic_recommendations')
            .delete()
            .eq('topic_queue_id', topicId)

        return NextResponse.json({
            success: true,
            topic_id: topicId,
            target_minutes: targetMinutes,
            target_scene_count: targetSceneCount,
            job,
        })
    } catch (e: any) {
        console.error('[topics-queue/repair] Failed to queue topic repair:', e)
        return NextResponse.json({ error: e?.message || 'Failed to queue topic repair' }, { status: 500 })
    }
}
