import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { generateVoiceStudioMp3 } from '@/lib/stdVoiceStudio'
export const maxDuration=240
export async function POST(req:Request){
    const auth=await requireStdUser(req)
    if(!auth.ok)return auth.response
    try{
        const body=await req.json()
        const audio=await generateVoiceStudioMp3({voiceId:String(body.voice_id||''),text:'조용한 아침, 창문 사이로 햇살이 들어왔다. 그는 천천히 문을 열고 새로운 하루를 맞이했다.'})
        return new NextResponse(new Uint8Array(audio),{headers:{'Content-Type':'audio/mpeg','Cache-Control':'private, max-age=86400'}})
    }catch(e:any){return NextResponse.json({error:e.message||'샘플 생성 실패'},{status:400})}
}
