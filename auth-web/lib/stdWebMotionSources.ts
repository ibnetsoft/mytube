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
/** Prepared scene originals already referenced by the owned project snapshot. */
export function preparedWebImage(project:any,scene:any){
 const number=Number(scene.scene_number);if(!Number.isInteger(number)||number<1||(scene.project_id&&scene.project_id!==project.id))return null
 const saved=(project.project_payload?.structure?.scenes||[]).find((s:any)=>Number(s.scene_number??s.scene_order)===number),image=saved?.metadata?.cowork_image_asset||scene.metadata?.metadata?.cowork_image_asset
 if(!image)return null
 const bucket=image.gcs_bucket||image.bucket,path=image.gcs_path,sha=image.sha256
 if(typeof bucket!=='string'||!/^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$/.test(bucket)||typeof path!=='string'||!/^[a-f0-9]{64}$/.test(sha||'')||!/^topics\/prepared\/[a-f0-9-]+\/images\//.test(path)||path.split('/').some((v:string)=>v==='.'||v==='..')||!path.endsWith(`scene-${String(number).padStart(3,'0')}-${sha.slice(0,16)}.png`))throw Error(`${number}번 저장 원화의 연결·해시를 확인해 주세요.`)
 return {id:`prepared-${number}-${sha}`,kind:'image',url:`/api/std/assets/gcs-file?bucket=${encodeURIComponent(bucket)}&path=${encodeURIComponent(path)}`,sha256:sha}
}
