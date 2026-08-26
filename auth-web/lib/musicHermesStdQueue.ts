import type { SupabaseClient } from '@supabase/supabase-js'

const MUSIC_MISSION_CATEGORY_NAME = 'Music Hermes Missions'
const DEFAULT_SCRIPT_STYLE = 'bgm'
const DEFAULT_IMAGE_STYLE = 'realistic'

function text(value: any, fallback = ''): string {
    const normalized = String(value ?? '').trim()
    return normalized || fallback
}

function intValue(value: any, fallback: number): number {
    const parsed = Number.parseInt(String(value ?? ''), 10)
    return Number.isFinite(parsed) ? parsed : fallback
}

function arrayOfStrings(value: any): string[] {
    if (!Array.isArray(value)) return []
    return value.map((item) => String(item ?? '').trim()).filter(Boolean)
}

function buildTrackPrompt(track: any, index: number, fallbackDuration: number) {
    const title = text(track?.title, `Track ${index + 1}`)
    const genre = text(track?.genre, 'instrumental')
    const mood = text(track?.mood, 'focused')
    const prompt = text(track?.prompt, `Original ${genre} instrumental track, ${mood}, loopable, no vocals.`)
    const durationSeconds = Math.max(30, intValue(track?.duration_seconds, fallbackDuration))
    const negativeRules = arrayOfStrings(track?.negative_rules)
    return {
        title,
        genre,
        mood,
        prompt,
        duration_seconds: durationSeconds,
        negative_rules: negativeRules,
    }
}

function buildMissionScript(pack: any, tracks: any[]): string {
    const concept = text(pack?.playlist_concept, 'Music Hermes prompt pack')
    const targetMarket = text(pack?.target_market, 'Thailand')
    const lyricsDirection = text(pack?.lyrics_direction)
    const tagCandidates = arrayOfStrings(pack?.tag_candidates)
    const header = [
        `Mission: Build a ${tracks.length}-track longform music video package for ${targetMarket}.`,
        `Playlist concept: ${concept}`,
        lyricsDirection ? `Lyrics direction: ${lyricsDirection}` : '',
        tagCandidates.length ? `Suggested tags: ${tagCandidates.join(', ')}` : '',
        'Use the track prompts below as the source of truth for Suno generation and upload packaging.',
    ].filter(Boolean).join('\n')

    const lines = tracks.map((track, index) => {
        const negatives = track.negative_rules.length
            ? `Negative rules: ${track.negative_rules.join(', ')}`
            : 'Negative rules: no artist imitation, no copyrighted melody, no watermark'
        return [
            `Track ${index + 1}: ${track.title}`,
            `Genre: ${track.genre}`,
            `Mood: ${track.mood}`,
            `Duration seconds: ${track.duration_seconds}`,
            `Prompt: ${track.prompt}`,
            negatives,
        ].join('\n')
    })

    return `${header}\n\n${lines.join('\n\n')}`.trim()
}

function buildGridPrompt(concept: string, scenes: any[], tracks: any[]): string {
    const detailLines = scenes.map((scene: any, idx: number) => {
        const track = tracks[idx]
        const position = ['Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right'][idx] || `Panel-${idx + 1}`
        return [
            `Position: ${position}`,
            `Scene number: ${scene.scene_number}`,
            `Track title: ${track.title}`,
            `Genre and mood: ${track.genre}; ${track.mood}`,
            `Prompt direction: ${track.prompt}`,
            `Visual instruction: Show a polished music mission card, warm editorial typography, atmospheric playlist art, and clear production cues for this track without using logos or copyrighted art.`,
        ].join('\n')
    }).join('\n\n')

    return [
        `Create a strict 2x2 production-board image for the playlist concept "${concept}".`,
        'No borders, no logos, no watermark, no subtitles, no UI chrome, no copyrighted characters.',
        'The canvas must read like a premium mission board for a Thai music creator receiving a 3-hour playlist assignment.',
        'Use cinematic color, clean card composition, and distinct atmosphere for each quadrant while keeping the same overall brand language.',
        'Every quadrant should feel actionable and production-ready, showing environment, mood, and track identity with consistent art direction.',
        detailLines,
    ].join('\n\n')
}

function buildPreparedStructure(pack: any, tracks: any[]) {
    const concept = text(pack?.playlist_concept, 'Music Hermes prompt pack')
    const scenes = tracks.map((track, index) => ({
        scene_number: index + 1,
        scene_order: index + 1,
        scene_title: track.title,
        title: track.title,
        script_excerpt: `Track ${index + 1}. ${track.title}. Genre ${track.genre}. Mood ${track.mood}. Prompt: ${track.prompt}`,
        scene_text: `Track ${index + 1}. ${track.title}. Genre ${track.genre}. Mood ${track.mood}. Prompt: ${track.prompt}`,
        image_prompt: `Album-cover style key art for "${track.title}", ${track.genre}, ${track.mood}, premium music mission card, no text, no logo, no watermark.`,
        shot_hints: ['music mission card', 'album art', 'atmospheric cover'],
        metadata: {
            track_title: track.title,
            track_genre: track.genre,
            track_mood: track.mood,
            music_prompt: track.prompt,
            negative_rules: track.negative_rules,
            duration_seconds: track.duration_seconds,
        },
    }))

    const imageGridPrompts: any[] = []
    for (let i = 0; i < scenes.length; i += 4) {
        const chunkScenes = scenes.slice(i, i + 4)
        const chunkTracks = tracks.slice(i, i + 4)
        while (chunkScenes.length < 4 && chunkScenes.length > 0) {
            chunkScenes.push(chunkScenes[chunkScenes.length - 1])
            chunkTracks.push(chunkTracks[chunkTracks.length - 1])
        }
        imageGridPrompts.push({
            grid_number: Math.floor(i / 4) + 1,
            template: 'strict_2x2_v1',
            panel_count: 4,
            scene_numbers: chunkScenes.map((scene: any) => scene.scene_number),
            panels: chunkScenes.map((scene: any, idx: number) => ({
                scene_number: scene.scene_number,
                scene_id: `music-track-${scene.scene_number}`,
                brief: `${chunkTracks[idx].title} / ${chunkTracks[idx].genre} / ${chunkTracks[idx].mood}`,
                panel_prompt: chunkTracks[idx].prompt,
            })),
            shared_style: `Premium music playlist mission board for "${concept}" with cohesive editorial mood.`,
            prompt: buildGridPrompt(concept, chunkScenes, chunkTracks),
        })
    }

    return {
        title: concept,
        image_style: DEFAULT_IMAGE_STYLE,
        image_grid_prompt_status: 'ready',
        scene_count: scenes.length,
        scenes,
        image_grid_prompts: imageGridPrompts,
        music_prompt_pack: pack,
    }
}

function buildPublishMetadata(pack: any, tracks: any[]) {
    const concept = text(pack?.playlist_concept, 'Music Hermes prompt pack')
    const targetMarket = text(pack?.target_market, 'Thailand')
    const tags = arrayOfStrings(pack?.tag_candidates)
    return {
        title: concept,
        description: [
            `${concept} mission package for ${targetMarket}.`,
            `Track count: ${tracks.length}.`,
            'This queue item contains the full prompt pack, track-by-track Suno guidance, and packaging notes for the assigned creator.',
        ].join(' '),
        tags: tags.join(', '),
        target_market: targetMarket,
        playlist_concept: concept,
    }
}

async function ensureMusicMissionCategory(
    supabase: SupabaseClient,
    targetEmail: string,
): Promise<any> {
    const { data: existing, error: existingError } = await supabase
        .from('categories')
        .select('id,name,default_script_style,default_image_style,assigned_employee_email,language')
        .eq('name', MUSIC_MISSION_CATEGORY_NAME)
        .eq('assigned_employee_email', targetEmail)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()

    if (existingError) throw existingError
    if (existing) return existing

    const payload = {
        name: MUSIC_MISSION_CATEGORY_NAME,
        keywords: 'music, hermes, suno, playlist, thailand, lofi, ambient',
        assigned_employee_email: targetEmail,
        default_script_style: DEFAULT_SCRIPT_STYLE,
        default_image_style: DEFAULT_IMAGE_STYLE,
        language: 'en',
    }

    const { data: inserted, error } = await supabase
        .from('categories')
        .insert(payload)
        .select('id,name,default_script_style,default_image_style,assigned_employee_email,language')
        .single()

    if (error) throw error
    return inserted
}

export async function findThaiMusicQueueCandidates(supabase: SupabaseClient) {
    const { data, error } = await supabase
        .from('profiles')
        .select('id,email,full_name,is_approved,preferred_languages,nationality,country_code,referral_country,created_at')
        .eq('is_approved', true)
        .not('email', 'is', null)
        .order('created_at', { ascending: true })

    if (error) throw error

    const rows = (data || []).filter((row: any) => {
        const country = text(row?.referral_country || row?.country_code).toUpperCase()
        const nationality = text(row?.nationality).toLowerCase()
        const langs = arrayOfStrings(row?.preferred_languages).map((lang) => lang.toLowerCase())
        return (
            country === 'TH'
            || nationality.includes('thai')
            || nationality.includes('thailand')
            || nationality.includes('태국')
            || langs.includes('th')
        )
    })

    return rows.map((row: any) => ({
        id: row.id,
        email: text(row.email),
        full_name: text(row.full_name),
        preferred_languages: arrayOfStrings(row.preferred_languages),
        country_code: text(row.referral_country || row.country_code).toUpperCase(),
    }))
}

export async function dispatchMusicPromptPackToStdQueue(
    supabase: SupabaseClient,
    pack: any,
    targetEmail: string,
) {
    const normalizedTargetEmail = text(targetEmail).toLowerCase()
    if (!normalizedTargetEmail) {
        throw new Error('Target user email is required')
    }

    const tracks = (Array.isArray(pack?.tracks) ? pack.tracks : []).map((track: any, index: number) =>
        buildTrackPrompt(track, index, intValue(pack?.track_duration_seconds, 180))
    )
    if (tracks.length === 0) {
        throw new Error('Prompt pack has no tracks to dispatch')
    }

    const category = await ensureMusicMissionCategory(supabase, normalizedTargetEmail)
    const concept = text(pack?.playlist_concept, 'Music Hermes prompt pack')
    const publishMetadata = buildPublishMetadata(pack, tracks)
    const preparedStructure = buildPreparedStructure(pack, tracks)
    const missionScript = buildMissionScript(pack, tracks)
    const title = `[Music Hermes] ${concept}`
    const nowIso = new Date().toISOString()
    const durationMinutes = Math.max(15, Math.ceil((tracks.length * Math.max(30, intValue(pack?.track_duration_seconds, 180))) / 60))
    const dedupeKey = `music-hermes:${text(pack?.target_market, 'Thailand').toLowerCase()}:${concept.toLowerCase()}:${tracks.length}`

    const { data: existingTopic, error: existingError } = await supabase
        .from('topics_queue')
        .select('id,status,assigned_employee_email,generated_title')
        .eq('category_id', category.id)
        .eq('assigned_employee_email', normalizedTargetEmail)
        .eq('generated_title', title)
        .contains('progress_payload', { music_dispatch_key: dedupeKey })
        .in('status', ['pending', 'assigned'])
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()

    if (existingError) throw existingError
    if (existingTopic) {
        return { reused: true, topic: existingTopic, category, recommendation_inserted: false }
    }

    const progressPayload = {
        prepared_topic_ready: true,
        prepared_topic_ready_at: nowIso,
        music_dispatch_key: dedupeKey,
        music_prompt_pack: pack,
        music_prompt_pack_tracks: tracks,
        music_prompt_pack_type: 'suno_prompt_mission',
        publish_metadata: publishMetadata,
        has_tts_audio: false,
        tts_completed: false,
    }

    const insertPayload: any = {
        category_id: category.id,
        topic: title,
        generated_title: title,
        assigned_employee_email: normalizedTargetEmail,
        status: 'pending',
        language: 'en',
        assigned_script_style: DEFAULT_SCRIPT_STYLE,
        assigned_image_style: DEFAULT_IMAGE_STYLE,
        pregenerated_script: missionScript,
        pregenerated_script_status: 'ready',
        pregenerated_structure: preparedStructure,
        pregenerated_structure_status: 'ready',
        publish_metadata: publishMetadata,
        progress_payload: progressPayload,
        assigned_duration_minutes: durationMinutes,
        recommended_duration_minutes: durationMinutes,
        estimated_payout: null,
        difficulty_level: 'normal',
        total_scenes: tracks.length,
        image_scenes: tracks.length,
        video_scenes: 0,
        asset_mix_summary: 'music_prompt_pack',
    }

    const { data: insertedTopic, error: insertError } = await supabase
        .from('topics_queue')
        .insert(insertPayload)
        .select('id,status,assigned_employee_email,generated_title,created_at')
        .single()

    if (insertError) throw insertError

    let recommendationInserted = false
    const { data: profile } = await supabase
        .from('profiles')
        .select('id,email')
        .eq('email', normalizedTargetEmail)
        .maybeSingle()

    const recommendationPayload = {
        user_id: profile?.id || null,
        employee_email: normalizedTargetEmail,
        topic_queue_id: insertedTopic.id,
        topic: title,
        language: 'en',
        recommended_duration_minutes: durationMinutes,
        estimated_payout: null,
        script_style: DEFAULT_SCRIPT_STYLE,
        image_style: DEFAULT_IMAGE_STYLE,
        category_id: category.id,
        category_name: category.name,
        payout_multiplier: 1,
        is_claimed: false,
        expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    }

    const { error: recDeleteError } = await supabase
        .from('user_topic_recommendations')
        .delete()
        .eq('employee_email', normalizedTargetEmail)
        .eq('topic_queue_id', insertedTopic.id)

    if (recDeleteError) {
        console.warn('[musicHermesStdQueue] recommendation cleanup failed:', recDeleteError.message)
    }

    const { error: recInsertError } = await supabase
        .from('user_topic_recommendations')
        .insert(recommendationPayload)

    if (recInsertError) {
        console.warn('[musicHermesStdQueue] recommendation insert failed:', recInsertError.message)
    } else {
        recommendationInserted = true
    }

    return {
        reused: false,
        topic: insertedTopic,
        category,
        recommendation_inserted: recommendationInserted,
    }
}
