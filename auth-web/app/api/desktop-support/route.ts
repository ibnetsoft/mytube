import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// 유저 -> 웹어드민 문의 시스템의 데스크톱 브릿지. desktop-referrals와 동일한
// email + HMAC session_token 스킴으로 인증하고, user_id는 세션 email로부터
// 서버가 직접 해석한다 (클라이언트 제공 값 불신 - 이 세션에서 계속 써온 패턴).
//
// AI 초안(ai_draft_reply)은 이 브릿지의 list 응답에 절대 포함하지 않는다 -
// 사용자에게는 어드민이 확정 발송한 admin_reply만 보인다.

const RATE_LIMIT_WINDOW_MINUTES = 10
const RATE_LIMIT_MAX_MESSAGES = 5
const MAX_BODY_LENGTH = 4000

async function resolveUserId(email: string): Promise<string | null> {
    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data.id
}

async function getGeminiApiKey(): Promise<string | null> {
    if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', 'sys_api_gemini')
        .maybeSingle()
    return data?.value || null
}

// 최근 답변 완료된 문의를 few-shot 컨텍스트로 사용 - 시간이 지날수록
// 어드민이 실제로 확정한 답변 스타일/정책을 AI 초안이 참고하게 된다
// (Hermes 같은 별도 학습 워커 없이, 과거 답변을 프롬프트에 실어 나르는
// 방식으로 "점점 나아지는 답변"을 구현).
async function fetchPastAnsweredExamples(limit = 5) {
    const { data } = await supabaseAdmin
        .from('support_messages')
        .select('body, admin_reply, detected_language')
        .eq('status', 'ANSWERED')
        .not('admin_reply', 'is', null)
        .order('replied_at', { ascending: false })
        .limit(limit)
    return data || []
}

async function generateAiDraftReply(body: string): Promise<{ draft: string; language: string; model: string } | null> {
    try {
        const apiKey = await getGeminiApiKey()
        if (!apiKey) return null

        const examples = await fetchPastAnsweredExamples()
        const examplesText = examples.length
            ? examples.map((ex, i) => `예시 ${i + 1} (언어: ${ex.detected_language || '미상'})\n문의: ${ex.body}\n답변: ${ex.admin_reply}`).join('\n\n')
            : '(참고할 과거 답변 없음)'

        const model = 'gemini-2.5-flash'
        const prompt = `당신은 AI 영상 제작 플랫폼의 고객 지원 담당자를 돕는 어시스턴트입니다.
아래 사용자 문의에 대한 답장 "초안"을 작성하세요. 이 초안은 상담원이 검토/수정 후에만 발송됩니다 - 사용자에게 직접 나가지 않습니다.

[매우 중요] 문의가 작성된 언어를 정확히 감지하고, 반드시 그 언어와 동일한 언어로 답변을 작성하세요.
예: 태국어로 질문하면 태국어로, 베트남어로 질문하면 베트남어로 답하세요. 절대 한국어로 임의 번역하지 마세요.

[과거에 실제로 발송된 답변 예시 - 톤과 정책을 참고하세요]
${examplesText}

[이번 문의]
${body}

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{"detected_language": "ISO 639-1 코드 (ko/en/th/vi 등)", "draft_reply": "문의와 동일한 언어로 작성된 답변 초안"}`

        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: { temperature: 0.3, responseMimeType: 'application/json' },
            }),
        })
        const result = await res.json()
        const text = result?.candidates?.[0]?.content?.parts?.[0]?.text
        if (!text) return null
        const parsed = JSON.parse(text)
        if (!parsed.draft_reply) return null
        return {
            draft: String(parsed.draft_reply),
            language: String(parsed.detected_language || '').toLowerCase().slice(0, 8),
            model,
        }
    } catch (err: any) {
        console.error('[DesktopSupport] AI draft generation failed:', err?.message)
        return null
    }
}

async function actionSend(userId: string, body: any) {
    const subject = String(body.subject || '').trim().slice(0, 200)
    const messageBody = String(body.body || '').trim().slice(0, MAX_BODY_LENGTH)
    if (!messageBody) {
        return { success: false, error: '문의 내용을 입력해주세요.' }
    }

    // 스팸/비용 폭증 방지: 최근 N분 내 문의 건수 제한
    const windowStart = new Date(Date.now() - RATE_LIMIT_WINDOW_MINUTES * 60 * 1000).toISOString()
    const { count } = await supabaseAdmin
        .from('support_messages')
        .select('id', { count: 'exact', head: true })
        .eq('user_id', userId)
        .gte('created_at', windowStart)
    if ((count || 0) >= RATE_LIMIT_MAX_MESSAGES) {
        return { success: false, error: '문의를 너무 자주 보내셨습니다. 잠시 후 다시 시도해주세요.' }
    }

    const { data: inserted, error } = await supabaseAdmin
        .from('support_messages')
        .insert({ user_id: userId, subject, body: messageBody, status: 'OPEN' })
        .select('id')
        .maybeSingle()
    if (error || !inserted) {
        return { success: false, error: '문의 저장에 실패했습니다.' }
    }

    // AI 초안은 소프트 디펜던시 - 실패해도 문의 접수 자체는 성공으로 처리한다.
    // Vercel 서버리스는 응답 반환 직후 실행이 끊길 수 있으므로 await 필수
    // (/api/logs의 커미션 정산에서 이미 확인된 패턴).
    const draft = await generateAiDraftReply(messageBody)
    if (draft) {
        await supabaseAdmin
            .from('support_messages')
            .update({
                ai_draft_reply: draft.draft,
                ai_draft_model: draft.model,
                detected_language: draft.language || null,
                status: 'AI_DRAFTED',
            })
            .eq('id', inserted.id)
    }

    return { success: true, message_id: inserted.id }
}

async function actionList(userId: string) {
    // ai_draft_reply는 절대 포함하지 않는다 - 사용자에게는 확정 답장만 노출.
    const { data, error } = await supabaseAdmin
        .from('support_messages')
        .select('id, subject, body, status, admin_reply, replied_at, created_at')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .limit(50)
    if (error) {
        return { success: false, error: '문의 목록 조회에 실패했습니다.' }
    }
    return { success: true, messages: data || [] }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, action } = body

        if (!email || !session_token || !action) {
            return NextResponse.json({ success: false, error: 'Missing email, session_token or action' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        if (!verifyDesktopSessionToken(normalizedEmail, String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        const userId = await resolveUserId(normalizedEmail)
        if (!userId) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        switch (String(action)) {
            case 'send':
                return NextResponse.json(await actionSend(userId, body))
            case 'list':
                return NextResponse.json(await actionList(userId))
            default:
                return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 })
        }
    } catch (error: any) {
        console.error('[DesktopSupport] Error:', error?.message)
        return NextResponse.json({ success: false, error: '문의 서버 오류' }, { status: 500 })
    }
}
