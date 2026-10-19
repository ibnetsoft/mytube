import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import StdMotionStudio from '../../components/StdMotionStudio'
import {motionScene, MotionDraft} from '../../lib/stdMotionStudio'

function Fixture(){
    const [draft,setDraft]=useState<MotionDraft>({version:1,enabled:true,aspect:'16:9',fps:24,scenes:{'1':motionScene()}})
    const image='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#29445c"/><circle cx="320" cy="120" r="45" fill="#f2c8a1"/><path d="M250 180h140v150H250z" fill="#26a5a8"/><path d="M0 300h640v60H0z" fill="#324d48"/></svg>')
    return <main style={{maxWidth:1280,margin:'32px auto',fontFamily:'sans-serif',background:'#101722',color:'white',padding:24}}><h1>Motion Studio 검증용 독립 소스</h1><StdMotionStudio projectId="fixture" headers={{}} value={draft} scenes={[{id:'fixture',scene_number:1,scene_title:'원본 인물 · 제한 모션',image_url:image}]} disabled={false} onSave={async value=>{setDraft(value);(window as any).savedMotion=value}} onUpload={async()=>{}}/><pre id="saved-draft">{JSON.stringify(draft,null,2)}</pre></main>
}
createRoot(document.getElementById('root')!).render(<Fixture/> )
