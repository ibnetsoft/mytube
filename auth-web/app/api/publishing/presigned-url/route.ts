
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

// [AIR-0225B] 예전에는 body의 userId(UUID)만 믿고 videos/{userId}/... 경로에
// 대한 서명 업로드 URL을 발급했다 - UUID만 알면 타인 스토리지 경로에 쓰기가
// 가능한 구멍이었다. 이제 email + HMAC session_token 을 검증하고, 업로드
// 경로의 user_id 는 세션 email 로부터 서버가 직접 해석한다.
async function resolveUserId(admin: any, email: string): Promise<string | null> {
    const { data, error } = await admin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return (data as { id: string }).id
}

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey)

    try {
        const { email, session_token, fileName } = await req.json()

        if (!email || !session_token) {
            return NextResponse.json({ error: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!(await verifyApprovedDesktopSession(String(email), String(session_token)))) {
            return NextResponse.json({ error: 'invalid_or_expired_session' }, { status: 401 })
        }
        if (!fileName) {
            return NextResponse.json({ error: 'Missing fileName' }, { status: 400 })
        }

        const userId = await resolveUserId(supabaseAdmin, String(email))
        if (!userId) {
            return NextResponse.json({ error: 'Invalid user' }, { status: 401 })
        }

        // 1. Path: publishing/{userId}/{timestamp}_{fileName}
        const timestamp = Date.now()
        const filePath = `${userId}/${timestamp}_${fileName}`

        // 2. Create Signed URL for Upload (valid for 15 mins)
        // Note: For 'upload', we use storage.from().createSignedUploadUrl()
        const { data, error } = await supabaseAdmin
            .storage
            .from('videos') // Make sure 'videos' bucket exists
            .createSignedUploadUrl(filePath)

        if (error) throw error

        return NextResponse.json({
            success: true,
            uploadUrl: data.signedUrl,
            path: filePath,
            token: data.token // Required for some SDK versions, but signedUrl usually sufficient
        })
    } catch (error: any) {
        console.error('Signed URL Error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
