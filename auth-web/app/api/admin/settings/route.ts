import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

// 이 API는 관리자가 설정한 전역 API 키를 Supabase의 전역 설정 테이블(예: 'global_settings')에 저장하거나
// 필요한 경우 다른 관리 작업을 수행합니다.
// 현재는 예시로 성공 응답만 반환합니다.

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { gemini, openai, pexels } = body

        // Supabase Admin Client (Service Role)
        const supabaseAdmin = createClient(
            process.env.NEXT_PUBLIC_SUPABASE_URL!,
            process.env.SUPABASE_SERVICE_ROLE_KEY!
        )

        // 여기에 DB 저장 로직 추가 (예: settings 테이블)
        // const { error } = await supabaseAdmin.from('system_settings').upsert({ id: 'api_keys', data: { gemini, openai, pexels } })

        return NextResponse.json({ success: true, message: 'Settings saved to cloud' })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
