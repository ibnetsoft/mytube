export async function loadSpeakerCoordinateAssets(db: any, projectIds: string[]) {
    if (!projectIds.length) return []
    const assets: any[] = []
    for (let start = 0; ; start += 500) {
        const result = await db.from('std_project_assets')
            .select('id,project_id,asset_type,status,scene_number,metadata,created_at,updated_at')
            .in('project_id', projectIds)
            .in('status', ['uploaded', 'assigned'])
            .or('asset_type.in.(image,video),metadata->>kind.in.(ae_speaker_coordinates,speaker_coordinate_confirmation,speaker_coordinate_draft)')
            .order('created_at', { ascending: false }).order('id', { ascending: false })
            .range(start, start + 499)
        if (result.error) throw result.error
        assets.push(...(result.data || []))
        if ((result.data || []).length < 500) return assets
    }
}
