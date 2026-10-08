import { loadSpeakerCoordinateAssets } from './stdSpeakerCoordinateAssets'
import { speakerWorkInfo } from './stdSpeakerCoordinateOverview'

// Batch reads avoid one request per topic. Paginate assets: a project can have
// more than the Data API's default row limit, especially after repeated edits.
export async function attachTopicWorkInfo(db: any, topics: any[]) {
    const info = new Map<string, any>()
    const ids = topics.map(topic => topic.id)
    for (let offset = 0; offset < ids.length; offset += 20) {
        const batch = ids.slice(offset, offset + 20)
        try {
            const { data, error } = await db.from('std_projects')
                .select('id,topic_queue_id,employee_email,project_payload,updated_at')
                .in('topic_queue_id', batch).neq('status', 'canceled')
                .order('updated_at', { ascending: false })
            if (error) throw error
            const projects = (data || []).filter((project: any, index: number, all: any[]) =>
                all.findIndex(other => String(other.topic_queue_id) === String(project.topic_queue_id)) === index)
            if (!projects.length) continue
            const assets = await loadSpeakerCoordinateAssets(db, projects.map((project: any) => project.id))
            const byProject = new Map<string, any[]>()
            for (const asset of assets) {
                const list = byProject.get(asset.project_id) || []
                list.push(asset)
                byProject.set(asset.project_id, list)
            }
            for (const project of projects) {
                info.set(String(project.topic_queue_id), speakerWorkInfo(project, byProject.get(project.id) || []))
            }
        } catch (error) {
            console.error('Failed to load topic work info:', error)
            for (const id of batch) info.set(String(id), { error: true })
        }
    }
    return topics.map(topic => ({ ...topic, work_info: info.get(String(topic.id)) || null }))
}
