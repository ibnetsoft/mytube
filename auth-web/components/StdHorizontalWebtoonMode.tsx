'use client'
import StdHorizontalWebtoon from './StdHorizontalWebtoon'

export default function StdHorizontalWebtoonMode({project,headers}:{project:any;headers:Record<string,string>;onSaved?:()=>Promise<unknown>}) {
 const saved=project.project_payload?.render_settings?.motion
 if(saved?.edit_mode!=='horizontal_webtoon')return null
 const disabled=Boolean(project.submitted_at)||['approved','canceled'].includes(project.status)
 return <StdHorizontalWebtoon projectId={project.id} headers={headers} disabled={disabled}/>
}
