export type PublishMetadata = { title: string; description: string; tags: string[] }
const object = (value: any): Record<string, any> => value && typeof value === 'object' && !Array.isArray(value) ? value : {}
const tags = (value: any): string[] => (Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : [])
    .map((tag: any) => String(tag).trim()).filter(Boolean)

export function resolveRenderPublishMetadata(task: any, project?: any, topic?: any, file?: any): PublishMetadata {
    const meta = object(task?.metadata)
    const sources = [file, project?.project_payload?.publish_metadata, project?.progress_payload?.publish_metadata,
        topic?.publish_metadata, topic?.progress_payload?.publish_metadata, meta.project_upload_metadata, meta].map(object)
    const result = {
        title: sources.map(s => String(s.title || s.titles?.[0] || '').trim()).find(Boolean)
            || project?.title || topic?.generated_title || task?.project_name || '',
        description: sources.map(s => String(s.description || '').trim()).find(Boolean) || '',
        tags: sources.map(s => tags(s.tags)).find(value => value.length > 0) || [],
    }
    // Explicit admin edits, including an intentionally emptied description/tags, win.
    const edited = object(meta.publish_metadata)
    return {
        title: typeof edited.title === 'string' ? edited.title : result.title,
        description: typeof edited.description === 'string' ? edited.description : result.description,
        tags: Array.isArray(edited.tags) ? tags(edited.tags) : result.tags,
    }
}

export async function loadRenderPublishContext(db: any, task: any) {
    const meta = object(task?.metadata)
    let project: any = null, topic: any = null
    if (meta.std_web_project_id) {
        const result = await db.from('std_projects').select('id,title,topic_queue_id,project_payload,progress_payload')
            .eq('id', meta.std_web_project_id).maybeSingle()
        if (result.error) throw result.error
        project = result.data
    }
    const topicId = project?.topic_queue_id || meta.topic_queue_id
    if (topicId || task?.project_id != null) {
        const query = db.from('topics_queue').select('id,generated_title,publish_metadata,progress_payload,categories(upload_channel_id,upload_channel_name,upload_channel_handle)')
        const result = await (topicId ? query.eq('id', topicId) : query.eq('local_project_id', task.project_id)).maybeSingle()
        if (result.error) throw result.error
        topic = result.data
    }
    return { project, topic }
}
