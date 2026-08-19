import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    try {
        const body = await req.json()
        const { project_id, script_text, category = '옛날이야기' } = body

        if (!script_text || !String(script_text).trim()) {
            return NextResponse.json({ success: false, error: '대본 텍스트가 필요합니다.' }, { status: 400 })
        }

        // Gemini API Key
        let geminiKey = process.env.GEMINI_API_KEY
        if (!geminiKey) {
            const { data: gSetting } = await supabaseAdmin
                .from('global_settings')
                .select('value')
                .eq('key', 'gemini')
                .maybeSingle()
            if (gSetting?.value) geminiKey = String(gSetting.value).trim()
        }

        if (!geminiKey) {
            return NextResponse.json({ success: false, error: 'Gemini API Key가 설정되어 있지 않습니다.' }, { status: 500 })
        }

        // 1. 대본에서 주인공 캐릭터 DNA 추출
        const extractPrompt = `당신은 영화/웹툰 캐릭터 비주얼 디렉터입니다.
아래 대본을 분석하여, 영상 전체를 이끌어갈 "주인공(Main Character)"의 시각적 고정 속성(캐릭터 DNA)을 추출하여 JSON으로 반환하세요.

[대본]
"""
${String(script_text).slice(0, 10000)}
"""

[반환 JSON 형식 - 순수 JSON만 반환]
{
  "name": "인물 이름 또는 호칭 (예: 만복 영감, 김민우 대리)",
  "gender": "male 또는 female",
  "age_group": "연령대 (예: 70s, 30s, 50s)",
  "role": "역할 (예: 주인공, 늙은 남편, 사연 제보자)",
  "visual_dna_en": "영어 캐릭터 정밀 묘사 프롬프트 (예: a 72-year-old Korean elderly man with deep wrinkles, grey messy hair, warm yet sorrowful eyes, wearing a weathered traditional Korean grey cotton hanbok jacket)",
  "tags": ["70대 한국인 남성", "백발", "소박한 한복", "슬픈 눈빛"]
}
`

        const geminiRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${geminiKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: extractPrompt }] }],
                generationConfig: { temperature: 0.3, responseMimeType: 'application/json' }
            })
        })

        if (!geminiRes.ok) {
            throw new Error(`Gemini API Error: ${geminiRes.status}`)
        }

        const gData = await geminiRes.json()
        const rawJson = gData?.candidates?.[0]?.content?.parts?.[0]?.text || '{}'
        const cleanJson = rawJson.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/\s*```$/i, '').trim()
        const characterDna = JSON.parse(cleanJson)

        // 대표 앵커 이미지 프롬프트
        const anchorPrompt = `Masterpiece character portrait photograph of ${characterDna.visual_dna_en || 'a person'}, soft studio cinematic side lighting, realistic skin texture, highly detailed, 8k, photorealistic, cinematic shot, 1:1 square portrait framing`

        // 2. 이미지 생성 (Gemini 3.1 Flash Image Preview 또는 Imagen API)
        let imageUrl = ''
        try {
            const imgRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateImages?key=${geminiKey}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: anchorPrompt,
                    config: { numberOfImages: 1, aspectRatio: '1:1', outputMimeType: 'image/jpeg' }
                })
            })
            if (imgRes.ok) {
                const imgData = await imgRes.json()
                const b64 = imgData?.generatedImages?.[0]?.image?.imageBytes
                if (b64) {
                    imageUrl = `data:image/jpeg;base64,${b64}`
                }
            }
        } catch (imgErr) {
            console.warn('Anchor image generation fallback:', imgErr)
        }

        const characterResult = {
            ...characterDna,
            anchor_prompt: anchorPrompt,
            image_url: imageUrl,
            created_at: new Date().toISOString()
        }

        return NextResponse.json({
            success: true,
            character: characterResult
        })
    } catch (e: any) {
        console.error('Character anchor error:', e)
        return NextResponse.json({ success: false, error: e.message || '캐릭터 앵커 생성 실패' }, { status: 500 })
    }
}