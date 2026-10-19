export type VideoModel = { id: string; name: string; model: string; endpoint: string; has_key: boolean }
export type VideoModelSettings = { models: VideoModel[]; active_id: string | null }

export function validateVideoModel(value: any): Omit<VideoModel, 'has_key'> {
    const id = String(value?.id || '')
    const name = String(value?.name || '').trim()
    const model = String(value?.model || '').trim()
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(id) || !name || name.length > 100 || !model || model.length > 200) throw new Error('이름과 모델 ID를 확인해 주세요.')
    let url: URL
    try { url = new URL(value.endpoint) } catch { throw new Error('올바른 API 주소를 입력해 주세요.') }
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('API 주소는 인증정보나 쿼리가 없는 HTTPS 주소여야 합니다.')
    return { id, name, model, endpoint: url.toString() }
}
