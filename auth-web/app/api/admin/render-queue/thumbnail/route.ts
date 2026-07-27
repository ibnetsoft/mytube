import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'
import { updateDriveFileMedia, createDriveMediaFile } from '@/lib/googleDrive'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

const MAX_THUMBNAIL_BYTES = 5_000_000

// POST (multipart/form-data, field "file"): 렌더큐 작업의 썸네일 이미지를
// Google Drive에서 교체 업로드한다. 기존 파일 ID를 그대로 유지하며 내용만
// 바꾸므로, 이후 유튜브 업로드 단계(services/drive_bundle_service.py)가
// 참조하는 썸네일 파일도 자동으로 새 이미지를 가리키게 된다.
export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const form = await req.formData()
        const file = form.get('file')
        if (!(file instanceof File)) {
            return NextResponse.json({ error: '이미지 파일이 필요합니다.' }, { status: 400 })
        }
        if (file.size > MAX_THUMBNAIL_BYTES) {
            return NextResponse.json({ error: '이미지 용량이 너무 큽니다 (5MB 이하).' }, { status: 400 })
        }
        if (!file.type.startsWith('image/')) {
            return NextResponse.json({ error: '이미지 파일만 업로드할 수 있습니다.' }, { status: 400 })
        }

        const sb = getAdmin()
        const { data: task, error } = await sb
            .from('remote_render_queue')
            .select('metadata')
            .eq('id', id)
            .single()

        if (error) throw error

        const meta = task?.metadata || {}
        const fileId = meta.result_thumbnail_file_id
        const bytes = await file.arrayBuffer()

        let finalFileId = fileId
        if (fileId) {
            await updateDriveFileMedia(fileId, bytes, file.type)
        } else {
            const folderId = meta.result_folder_id
            if (!folderId) {
                return NextResponse.json({ error: '이 작업에는 아직 업로드된 Drive 폴더가 없어 썸네일을 저장할 수 없습니다.' }, { status: 400 })
            }
            finalFileId = await createDriveMediaFile(folderId, `thumbnail_${Date.now()}.${file.type.split('/')[1] || 'jpg'}`, bytes, file.type)
            const { error: patchError } = await sb
                .from('remote_render_queue')
                .update({ metadata: { ...meta, result_thumbnail_file_id: finalFileId } })
                .eq('id', id)
            if (patchError) throw patchError
        }

        return NextResponse.json({ success: true, thumbnail_file_id: finalFileId })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
