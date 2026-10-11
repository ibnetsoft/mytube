export function youtubeVideoId(url: string): string {
    const u=new URL(url),parts=u.pathname.split('/').filter(Boolean)
    const id=u.hostname==='youtu.be'?parts[0]:u.pathname==='/watch'?u.searchParams.get('v'):parts[1]
    if(!['https:','http:'].includes(u.protocol)||!['youtu.be','youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(u.hostname)||u.username||u.password||u.port||!id||!/^[\w-]{11}$/.test(id))throw new Error('올바른 YouTube URL을 입력하세요.')
    return id
}
export function youtubeDurationSeconds(value: string): number {
    const m=/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(value || '')
    const seconds=m?Number(m[1]||0)*3600+Number(m[2]||0)*60+Number(m[3]||0):0
    if(!Number.isInteger(seconds)||seconds<60||seconds>3600)throw new Error('원본 영상 길이를 확인할 수 없거나 지원 범위(1~60분)를 벗어났습니다.')
    return seconds
}
export async function fetchYoutubeSourceDuration(url:string,keys:string[],fetcher:typeof fetch=fetch){
    const id=youtubeVideoId(url)
    for(const key of [...new Set(keys)].filter(Boolean).slice(0,3)){
        const api=new URL('https://www.googleapis.com/youtube/v3/videos');api.search=new URLSearchParams({part:'contentDetails,snippet',id,key}).toString()
        let res:Response
        try{res=await fetcher(api,{cache:'no-store',signal:AbortSignal.timeout(12000)})}catch{continue}
        if(!res.ok)continue
        const row=(await res.json()).items?.find((r:any)=>r.id===id)
        if(!row || row.snippet?.liveBroadcastContent==='live')throw new Error('공개된 녹화 영상의 길이를 확인해 주세요.')
        return {source_video_id:id,source_duration_seconds:youtubeDurationSeconds(row.contentDetails?.duration),source_duration_verified:true}
    }
    throw new Error('YouTube 원본 영상 길이를 확인하지 못했습니다. API 연결을 확인한 뒤 다시 등록하세요.')
}
