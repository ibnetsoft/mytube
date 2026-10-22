// Use persisted category IDs; titles and video language do not identify a genre.
export async function attachStdProjectCategories(db: any, projects: any[]) {
    const ids = [...new Set(projects.map(project => project.category_id).filter(id => id !== null && id !== undefined))]
    if (!ids.length) return projects.map(project => ({ ...project, category_name: null }))
    const { data, error } = await db.from('categories').select('id,name').in('id', ids)
    if (error) throw error
    const names = new Map((data || []).map((category: any) => [String(category.id), category.name]))
    return projects.map(project => ({ ...project, category_name: names.get(String(project.category_id)) || null }))
}
