import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'
import { getDriveFileJson, updateDriveFileJson, createDriveJsonFile } from '@/lib/googleDrive'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 렌더큐 작업의 유튜브 업로드 메타데이터(metadata.json, Google Drive)를 조회한다.
export async function GET(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const sb = getAdmin()
        const { data: task, error } = await sb
            .from('remote_render_queue')
            .select('metadata')
            .eq('id', id)
            .single()

        if (error) throw error
        const fileId = task?.metadata?.result_metadata_file_id
        if (!fileId) {
            return NextResponse.json({
                success: true,
                exists: false,
                title: task?.metadata?.title || '',
                description: '',
                tags: [],
            })
        }

        const json = await getDriveFileJson(fileId)
        return NextResponse.json({
            success: true,
            exists: true,
            title: json.title || '',
            description: json.description || '',
            tags: Array.isArray(json.tags) ? json.tags : [],
        })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PATCH: title/description/tags를 수정해 Drive의 metadata.json에 반영한다.
// 이 파일은 나중에 실제 유튜브 업로드 시 제목/설명/태그의 1순위 소스로 쓰인다
// (services/drive_bundle_service.py get_project_bundle 참고) - 즉 여기서 고친
// 내용이 그대로 실제 업로드에 반영된다.
export async function PATCH(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const { title, description, tags } = await req.json()

        const sb = getAdmin()
        const { data: task, error } = await sb
            .from('remote_render_queue')
            .select('*')
            .eq('id', id)
            .single()

        if (error) throw error

        const meta = task?.metadata || {}
        const fileId = meta.result_metadata_file_id

        let existingJson: any = {}
        if (fileId) {
            try {
                existingJson = await getDriveFileJson(fileId)
            } catch (e) {
                // 파일이 지워졌거나 접근 불가 - 새로 만드는 셈 치고 계속 진행
                existingJson = {}
            }
        }

        const nextJson = {
            ...existingJson,
            title: title ?? existingJson.title ?? '',
            description: description ?? existingJson.description ?? '',
            tags: Array.isArray(tags) ? tags : (existingJson.tags || []),
        }

        let finalFileId = fileId
        if (fileId) {
            await updateDriveFileJson(fileId, nextJson)
        } else {
            const folderId = meta.result_folder_id
            if (!folderId) {
                return NextResponse.json({ error: '이 작업에는 아직 업로드된 Drive 폴더가 없어 메타데이터를 저장할 수 없습니다.' }, { status: 400 })
            }
            finalFileId = await createDriveJsonFile(folderId, 'metadata.json', nextJson)
            const { error: patchError } = await sb
                .from('remote_render_queue')
                .update({ metadata: { ...meta, result_metadata_file_id: finalFileId } })
                .eq('id', id)
            if (patchError) throw patchError
        }

        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
