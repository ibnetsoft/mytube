import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function buildDriveOpenLink(fileId?: string | null) {
    if (!fileId) return null
    return `https://drive.google.com/file/d/${fileId}/view`
}

function buildDriveFolderLink(folderId?: string | null) {
    if (!folderId) return null
    return `https://drive.google.com/drive/folders/${folderId}`
}

function buildDriveThumbnailPreview(fileId?: string | null) {
    if (!fileId) return null
    return `https://drive.google.com/thumbnail?id=${fileId}&sz=w512`
}

function normalizePublishingRequest(request: any) {
    const metadata = request?.metadata || {}
    const title =
        metadata.title ||
        metadata.project_name ||
        metadata.topic ||
        'Untitled Video'

    const driveFolderId = metadata.drive_folder_id || metadata.result_folder_id || null
    const driveVideoFileId = metadata.drive_video_file_id || metadata.result_video_file_id || null
    const driveThumbnailFileId = metadata.drive_thumbnail_file_id || metadata.result_thumbnail_file_id || null
    const driveMetadataFileId = metadata.drive_metadata_file_id || metadata.result_metadata_file_id || null
    const projectId = metadata.project_id || null
    const publishError = metadata.publish_error || null
    const trackDurations = Array.isArray(metadata.track_durations) ? metadata.track_durations : []
    const totalDurationSeconds =
        Number(metadata.total_duration_seconds || 0) ||
        trackDurations.reduce((sum: number, item: any) => sum + (Number(item || 0) || 0), 0) ||
        null
    const trackCount =
        Number(metadata.track_count || 0) ||
        (trackDurations.length ? trackDurations.length : null)

    return {
        ...request,
        metadata: {
            ...metadata,
            project_id: projectId,
            title,
            drive_folder_id: driveFolderId,
            drive_video_file_id: driveVideoFileId,
            drive_thumbnail_file_id: driveThumbnailFileId,
            drive_metadata_file_id: driveMetadataFileId,
            drive_folder_link: buildDriveFolderLink(driveFolderId),
            drive_video_link: buildDriveOpenLink(driveVideoFileId),
            drive_thumbnail_link: buildDriveOpenLink(driveThumbnailFileId),
            drive_metadata_link: buildDriveOpenLink(driveMetadataFileId),
            drive_thumbnail_preview_url:
                metadata.thumbnail_preview_url ||
                buildDriveThumbnailPreview(driveThumbnailFileId),
            youtube_url: metadata.videoId ? `https://youtu.be/${metadata.videoId}` : null,
            has_drive_bundle: Boolean(driveFolderId || driveVideoFileId || driveMetadataFileId),
            track_count: trackCount,
            total_duration_seconds: totalDurationSeconds,
            publish_error: publishError,
            published_at: metadata.published_at || null,
            failed_at: metadata.failed_at || null,
            is_invalid_request: !projectId,
        },
    }
}

export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { searchParams } = new URL(req.url)
        const userId = searchParams.get('userId')

        // join이 실패할 수 있으므로 간단하게 조회 후 필터링하거나, 관계가 확실할때만 사용
        // 여기서는 안전을 위해 단순 조회를 먼저 시도합니다.
        let query = supabase
            .from('publishing_requests')
            .select('*')
            .order('created_at', { ascending: false })

        if (userId) {
            query = query.eq('user_id', userId)
        }

        const { data: requests, error } = await query
        if (error) throw error

        // 수동으로 이메일 매핑 (선택 사항 - UI에서 유저 리스트와 매칭 가능하므로 일단 단순 반환)
        const normalized = (requests || []).map(normalizePublishingRequest)
        return NextResponse.json({ requests: normalized })
    } catch (error: any) {
        console.error("Publishing API Error:", error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const payload = await req.json()
        const userId = payload?.user_id || payload?.userId
        const videoUrl = payload?.video_url || payload?.videoUrl
        const metadata = payload?.metadata || {}
        const projectId = metadata?.project_id || payload?.project_id || null

        if (!userId || !videoUrl || !projectId) {
            return NextResponse.json({ error: 'Missing user_id, video_url, or metadata.project_id' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('publishing_requests')
            .select('id, metadata, status')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })

        if (existingError) throw existingError

        const existingRow = (existing || []).find((row: any) => {
            const rowProjectId = row?.metadata?.project_id
            return String(rowProjectId || '') === String(projectId)
        })

        if (existingRow) {
            const { data, error } = await supabase
                .from('publishing_requests')
                .update({
                    video_url: videoUrl,
                    metadata,
                    status: 'pending',
                })
                .eq('id', existingRow.id)
                .select()
                .single()

            if (error) throw error
            return NextResponse.json({ success: true, request: normalizePublishingRequest(data), updated: true })
        }

        const { data, error } = await supabase
            .from('publishing_requests')
            .insert({
                user_id: userId,
                video_url: videoUrl,
                metadata,
                status: 'pending',
            })
            .select()
            .single()

        if (error) throw error
        return NextResponse.json({ success: true, request: normalizePublishingRequest(data), created: true })
    } catch (error: any) {
        console.error("Publishing POST Error:", error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function PATCH(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { requestId, status, publish_visibility } = await req.json()
        if (!requestId || !status) return NextResponse.json({ error: 'Missing parameters' }, { status: 400 })

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('publishing_requests')
            .select('id, metadata, status, user_id')
            .eq('id', requestId)
            .single()

        if (existingError) throw existingError
        if ((status === 'approved' || status === 'to_be_published') && !existing?.metadata?.project_id) {
            return NextResponse.json({ error: 'Missing project_id in publishing request metadata' }, { status: 400 })
        }

        const nextMetadata = {
            ...(existing?.metadata || {}),
            ...(publish_visibility ? { publish_visibility } : {}),
        }

        const { data, error } = await supabase
            .from('publishing_requests')
            .update({ status, metadata: nextMetadata })
            .eq('id', requestId)
            .select()

        if (error) throw error

        // [NEW] Referral Reward Logic
        if (status === 'approved' && existing?.status !== 'approved' && existing?.user_id) {
            // Check if user has a referrer
            const { data: profile } = await supabase
                .from('profiles')
                .select('referred_by')
                .eq('id', existing.user_id)
                .single()

            if (profile?.referred_by) {
                // Count approved videos
                const { count } = await supabase
                    .from('publishing_requests')
                    .select('id', { count: 'exact', head: true })
                    .eq('user_id', existing.user_id)
                    .eq('status', 'approved')

                if (count === 2) {
                    // Reward the referrer
                    const { data: referrerProfile } = await supabase
                        .from('profiles')
                        .select('id')
                        .eq('id', profile.referred_by)
                        .single()
                    
                    if (referrerProfile) {
                        const { data: existingReward } = await supabase
                            .from('referral_rewards_log')
                            .select('id')
                            .eq('referred_user_id', existing.user_id)
                            .single()
                        
                        if (!existingReward) {
                            await supabase.rpc('increment_usdt_balance', {
                                uid: referrerProfile.id,
                                amount_to_add: 20
                            })
                            await supabase.from('referral_rewards_log').insert({
                                referrer_id: referrerProfile.id,
                                referred_user_id: existing.user_id,
                                amount: 20
                            })
                        }
                    }
                }
            }
        }

        return NextResponse.json({ success: true, data: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
