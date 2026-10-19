import type { VideoModel } from './stdVideoModels'
export type ProviderRequest={id:string;status_url:string;response_url?:string}
export function providerUrl(value:string,provider:string) {
    const url=new URL(value),host=provider==='fal'?'queue.fal.run':'api.replicate.com'
    if(url.protocol!=='https:'||url.hostname!==host||url.username||url.password||url.port||url.hash)throw new Error('영상 API 응답 주소가 유효하지 않습니다.')
    return url.toString()
}
export function outputVideoUrl(value:any) {
    const raw=value?.video?.url || value?.output?.video?.url || (Array.isArray(value?.output)?value.output[0]:value?.output)
    const url=new URL(String(raw||''))
    if(url.protocol!=='https:'||url.username||url.password||url.port||!['fal.media','replicate.delivery'].some(h=>url.hostname===h||url.hostname.endsWith('.'+h)))throw new Error('지원하는 제공자 영상 URL이 필요합니다.')
    return url.toString()
}
async function jsonRequest(url:string,secret:string,provider:string,body?:any) {
    const response=await fetch(providerUrl(url,provider),{method:body?'POST':'GET',headers:{Authorization:`${provider==='fal'?'Key':'Bearer'} ${secret}`,'Content-Type':'application/json'},
        ...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(25000),redirect:'error',cache:'no-store'})
    if(!response.ok)throw new Error(`영상 API 요청 실패 (HTTP ${response.status}).`)
    return response.json()
}
export async function createProviderVideo(config:Omit<VideoModel,'has_key'>,secret:string,plan:{prompt:string;duration:number},imageUrl:string):Promise<ProviderRequest> {
    const input={...config.extra_input,prompt:plan.prompt,[config.image_field!]:imageUrl,[config.duration_field!]:config.duration_type==='number'?plan.duration:String(plan.duration)}
    const data=await jsonRequest(config.endpoint,secret,config.provider!,config.provider==='fal'?input:{input})
    const id=config.provider==='fal'?data.request_id:data.id
    if(typeof id!=='string'||!/^[a-zA-Z0-9_-]{1,200}$/.test(id))throw new Error('영상 API 작업 ID를 받지 못했습니다.')
    const status_url=providerUrl(config.provider==='fal'?data.status_url:data.urls?.get,config.provider!)
    const response_url=config.provider==='fal'?providerUrl(data.response_url,config.provider!):undefined
    return {id,status_url,...(response_url?{response_url}:{})}
}
export async function pollProviderVideo(config:Omit<VideoModel,'has_key'>,secret:string,request:ProviderRequest) {
    const data=await jsonRequest(request.status_url,secret,config.provider!)
    if(data.error||['failed','canceled'].includes(data.status))throw new Error('영상 제공자가 생성 실패를 반환했습니다.')
    if(config.provider==='fal'&&data.status==='COMPLETED')return {state:'complete',url:outputVideoUrl(await jsonRequest(request.response_url!,secret,config.provider!))}
    if(config.provider==='replicate'&&data.status==='succeeded')return {state:'complete',url:outputVideoUrl(data)}
    return {state:'pending'}
}
