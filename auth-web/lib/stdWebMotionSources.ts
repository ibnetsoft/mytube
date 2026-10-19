/** Resolve reviewed PSD packages attached to existing scene image/video assets. */
export function linkedWebPsd(projectId:string,asset:any) {
    const psd=asset?.metadata?.psd_layer_asset
    if(!psd)return null
    if(String(asset.project_id)!==projectId||!['uploaded','assigned'].includes(asset.status)||!Number.isInteger(asset.scene_number)||asset.scene_number<1)throw Error('PSD의 프로젝트·씬 연결을 확인해 주세요.')
    if(psd.status!=='ready'||psd.qa_status!=='approved'||!/^[a-f0-9]{64}$/.test(psd.sha256||''))throw Error(`${asset.scene_number}번 씬 PSD의 원본 검수가 필요합니다.`)
    if(typeof psd.gcs_bucket!=='string'||!/^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$/.test(psd.gcs_bucket)||typeof psd.gcs_path!=='string'||!psd.gcs_path.startsWith(`std-projects/${projectId}/`)||!psd.gcs_path.toLowerCase().endsWith('.psd')||psd.gcs_path.split('/').some((s:string)=>s==='.'||s==='..'))throw Error('PSD 저장 위치가 현재 프로젝트와 다릅니다.')
    return {gcsBucket:psd.gcs_bucket,gcsPath:psd.gcs_path,sha256:psd.sha256}
}
export function linkedWebPsdSources(projectId:string,assets:any[],direct:Map<number,any>) {
    const result=new Map<number,any>()
    for(const asset of [...assets].sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||''))||String(b.id).localeCompare(String(a.id)))){
        if(direct.has(asset.scene_number)||result.has(asset.scene_number)||!asset.metadata?.psd_layer_asset)continue
        if(linkedWebPsd(projectId,asset))result.set(asset.scene_number,asset)
    }
    return result
}
