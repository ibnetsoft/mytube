import { createHash } from 'crypto'
import { supabaseAdmin as db } from './supabaseAdmin'
import { readYoutubeCredentials } from './stdYoutubeChannelOAuth'
import { validateVideoModel } from './stdVideoModels'
export async function selectedVideoModel(email: string, id?:string) {
    const key='std_video_models_'+createHash('sha256').update(email.trim().toLowerCase()).digest('hex')
    const row=await db.from('global_settings').select('value').eq('key',key).maybeSingle()
    if(row.error)throw row.error
    if(!row.data?.value)throw new Error('설정에서 영상 모델을 등록하고 적용해 주세요.')
    const catalog=readYoutubeCredentials(row.data.value,process.env.VIDEO_MODEL_ENCRYPTION_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY!)
    const stored=catalog.models.find((m:any)=>m.id===(id || catalog.active_id))
    if(!stored?.secret)throw new Error('적용한 영상 모델과 API 키가 없습니다.')
    const config=validateVideoModel(stored)
    if(config.provider==='unconfigured')throw new Error('설정에서 fal 또는 Replicate API 방식을 지정해 주세요.')
    return { config, secret:stored.secret, fingerprint:createHash('sha256').update(JSON.stringify(config)).digest('hex') }
}
