export type VideoModel = { id: string; name: string; model: string; endpoint: string; has_key: boolean; provider?: 'fal'|'replicate'|'unconfigured'; image_field?:string; duration_field?:string; duration_type?:'string'|'number'; extra_input?:Record<string,unknown> }
export type VideoModelSettings = { models: VideoModel[]; active_id: string | null }

export function validateVideoModel(value: any): Omit<VideoModel, 'has_key'> {
    const id = String(value?.id || '')
    const name = String(value?.name || '').trim()
    const model = String(value?.model || '').trim()
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(id) || !name || name.length > 100 || !model || model.length > 200) throw new Error('이름과 모델 ID를 확인해 주세요.')
    let url: URL
    try { url = new URL(value.endpoint) } catch { throw new Error('올바른 API 주소를 입력해 주세요.') }
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('API 주소는 인증정보나 쿼리가 없는 HTTPS 주소여야 합니다.')
    const provider=value.provider || 'unconfigured'
    if (!['fal','replicate','unconfigured'].includes(provider)) throw new Error('지원하는 영상 API 방식을 선택해 주세요.')
    if (provider==='fal' && (url.hostname!=='queue.fal.run' || url.pathname !== '/'+model || !/^[a-zA-Z0-9_/-]+$/.test(model))) throw new Error('fal API 주소는 https://queue.fal.run/모델ID 형식이어야 합니다.')
    if (provider==='replicate' && (url.hostname!=='api.replicate.com' || url.pathname !== `/v1/models/${model}/predictions` || !/^[a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+$/.test(model))) throw new Error('Replicate API 주소와 owner/model ID를 확인해 주세요.')
    if (url.port) throw new Error('기본 HTTPS 포트만 사용할 수 있습니다.')
    const image_field=String(value.image_field || (provider==='fal'?'image_url':'image')),duration_field=String(value.duration_field || 'duration')
    if (![image_field,duration_field].every(v=>/^[a-z][a-z0-9_]{0,63}$/i.test(v)) || ['prompt','model'].includes(image_field) || [image_field,'prompt','model'].includes(duration_field)) throw new Error('이미지·길이 입력 필드를 확인해 주세요.')
    const extra_input=value.extra_input || {}
    if (!extra_input || Array.isArray(extra_input) || typeof extra_input!=='object' || JSON.stringify(extra_input).length>4000 || Object.keys(extra_input).some(k=>/key|secret|token|password|authorization/i.test(k))) throw new Error('추가 입력 JSON에는 인증정보를 넣지 마세요.')
    return { id, name, model, endpoint: url.toString(),provider,image_field,duration_field,duration_type:value.duration_type==='number'?'number':'string',extra_input }
}
