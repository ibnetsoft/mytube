import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'
import { getDriveFileJson, updateDriveFileJson } from '@/lib/googleDrive'
import { loadRenderPublishContext, resolveRenderPublishMetadata } from '@/lib/renderQueuePublishMetadata'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// Read saved web metadata and explicit admin edits, with legacy file support.
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
            .select('*')
            .eq('id', id)
            .single()

        if (error) throw error
        const { project, topic } = await loadRenderPublishContext(sb, task)
        const fileId = task?.metadata?.result_metadata_file_id
        let file = null
        if (fileId) {
            try { file = await getDriveFileJson(fileId) }
            catch (error) {
                if (!project && !topic && !task.metadata?.publish_metadata) throw error
            }
        }
        const metadata = resolveRenderPublishMetadata(task, project, topic, file)
        return NextResponse.json({ success: true, exists: Boolean(metadata.title || metadata.description || metadata.tags.length), ...metadata })

    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// Save edits for both the web project and the upload request; retain legacy file support.
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

        if ((title !== undefined && typeof title !== 'string')
            || (description !== undefined && typeof description !== 'string')
            || (tags !== undefined && (!Array.isArray(tags) || tags.some((tag: any) => typeof tag !== 'string')))) {
            return NextResponse.json({ error: 'Invalid title, description or tags' }, { status: 400 })
        }
        const meta = task?.metadata || {}
        const { project, topic } = await loadRenderPublishContext(sb, task)
        let file: any = {}
        if (meta.result_metadata_file_id) file = await getDriveFileJson(meta.result_metadata_file_id)
        const existing = resolveRenderPublishMetadata(task, project, topic, file)
        const nextJson = { ...file, ...existing, title: title ?? existing.title,
            description: description ?? existing.description, tags: tags ?? existing.tags }

        if (meta.result_metadata_file_id) await updateDriveFileJson(meta.result_metadata_file_id, nextJson)
        if (project) {
            const { error: projectError } = await sb.from('std_projects').update({
                project_payload: { ...project.project_payload, publish_metadata: {
                    ...project.project_payload?.publish_metadata, title: nextJson.title,
                    description: nextJson.description, tags: nextJson.tags,
                } },
            }).eq('id', project.id)
            if (projectError) throw projectError
        }
        const { error: patchError } = await sb.from('remote_render_queue').update({ metadata: {
            ...meta, publish_metadata: nextJson, title: nextJson.title,
            description: nextJson.description, tags: nextJson.tags,
        } }).eq('id', id)
        if (patchError) throw patchError

        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
