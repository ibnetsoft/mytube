import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 120

const SCRIPT_WRITER_PROMPT = `당신은 최고 시청률의 유튜브 롱폼 다큐멘터리 및 토크쇼 메인 작가(Anthropic Claude)입니다.
구글 노트북LM(Gemini)이 심층 조사하여 정리한 [팩트 연구 브리프]를 바탕으로, 한국어 특유의 흡입력과 몰입감을 극대화한 최고 품질의 유튜브 롱폼 대본과 53개 씬(Scene) 구성을 작성하세요.

[요청 설정]
- 카테고리: {{category}}
- 목표 영상 분량: {{duration_minutes}}분 (약 4,000자~6,000자 대본 분량)
- 대본 포맷 모드: {{mode_instruction}}

[팩트 연구 브리프 (Gemini NotebookLM Grounding Research)]
"""
{{research_summary}}
"""

[원문 참고 자료 발췌]
"""
{{source_text}}
"""

[작성 지침]
1. {{mode_specific_rules}}
2. 문장력 및 흡입력: 시청자가 15~20분 동안 이탈하지 않도록 문장 끝맺음, 감정의 완급 조절, 생생한 구어체를 적용하세요.
3. 씬 구성(Scenes): 유튜브 롱폼 영상에 맞게 총 50개~53개의 씬으로 분할하세요.
   - 각 씬마다:
     * scene_number: 1, 2, ...
     * speaker: 대사를 말하는 화자 이름 (2인 대화 모드면 "진행자1" 또는 "진행자2", 1인 모드면 "나레이터")
     * scene_text: 해당 씬에서 읽을 대사 (2~3문장)
     * image_prompt: 해당 씬에 어울리는 구체적인 영어 이미지 프롬프트 (Cinematic lighting, 8k, photorealistic style)
     * visual_type: 1~12씬은 "video" (초반 훅 5초 비디오), 13~53씬은 "image"

[반환 JSON 스키마 - 반드시 순수 JSON만 반환하세요]
{
  "title": "시청자를 사로잡는 강력한 유튜브 롱폼 제목",
  "hook": "초반 1분 시청 지속률을 극대화하는 도입부 훅 요약",
  "category": "{{category}}",
  "mode": "{{mode}}",
  "dialogue_mode": {{is_dialogue_json}},
  "speakers": {{speakers_json}},
  "full_script": "전체 대본 전문 (화자 이름 포함)...",
  "scenes": [
    {
      "scene_number": 1,
      "speaker": "{{default_speaker_1}}",
      "scene_text": "첫 번째 씬 대사...",
      "image_prompt": "Cinematic visual description in English...",
      "visual_type": "video"
    }
  ]
}
`

export async function POST(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    try {
        const body = await req.json()
        const {
            source_text,
            mode = 'dialogue_podcast',
            category = '옛날이야기',
            duration_minutes = 15,
            custom_title = ''
        } = body

        if (!source_text || !String(source_text).trim()) {
            return NextResponse.json({ success: false, error: '참고 자료(텍스트)를 입력해주세요.' }, { status: 400 })
        }

        // Gemini & Claude API Keys 확보 (환경변수 또는 global_settings)
        let geminiKey = process.env.GEMINI_API_KEY
        let claudeKey = process.env.CLAUDE_API_KEY

        if (!geminiKey || !claudeKey) {
            const { data: gSettings } = await supabaseAdmin
                .from('global_settings')
                .select('key, value')
                .in('key', ['gemini', 'claude'])
            
            gSettings?.forEach((item: any) => {
                if (item.key === 'gemini' && !geminiKey) geminiKey = String(item.value).trim()
                if (item.key === 'claude' && !claudeKey) claudeKey = String(item.value).trim()
            })
        }

        if (!geminiKey) {
            return NextResponse.json({ success: false, error: '시스템에 Gemini API Key가 설정되어 있지 않습니다.' }, { status: 500 })
        }

        // ──────────────────────────────────────────────────────────
        // 🚀 STEP 1: Google Gemini 1.5 - 심층 자료 분석 및 팩트 추출 (RAG / Research)
        // ──────────────────────────────────────────────────────────
        const researchPrompt = `당신은 구글 노트북LM(NotebookLM)의 핵심 연구 분석관입니다.
제공된 [참고 자료]를 꼼꼼히 정독하고, 유튜브 롱폼(${duration_minutes}분) 대본 집필에 필요한 핵심 팩트, 인물 관계, 타임라인, 가장 흥미로운 갈등/사연 포인트, 통계/인용구를 팩트 위주로 완벽하게 요약 정리(Research Brief)하세요.

[참고 자료]
"""
${String(source_text).slice(0, 30000)}
"""`

        let researchSummary = ''
        try {
            const geminiRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${geminiKey}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contents: [{ parts: [{ text: researchPrompt }] }],
                    generationConfig: { temperature: 0.2 }
                })
            })
            if (geminiRes.ok) {
                const gData = await geminiRes.json()
                researchSummary = gData?.candidates?.[0]?.content?.parts?.[0]?.text || ''
            }
        } catch (rErr) {
            console.warn('Gemini research step warning:', rErr)
        }

        if (!researchSummary) {
            researchSummary = String(source_text).slice(0, 5000)
        }

        // ──────────────────────────────────────────────────────────
        // 🚀 STEP 2: Claude 3.5 Haiku - 명품 대본 집필 & 53개 씬 생성 (Writer)
        // ──────────────────────────────────────────────────────────
        const isDialogue = (mode === 'dialogue_podcast')
        let modeInstruction = ''
        let modeSpecificRules = ''
        let isDialogueJson = 'false'
        let speakersJson = '["나레이터"]'
        let defaultSpeaker1 = '나레이터'

        if (isDialogue) {
            modeInstruction = '2인 대화형 팟캐스트 (노트북LM Audio Overview 스타일 - 남/여 진행자 티키타카 토크쇼)'
            modeSpecificRules = (
                '반드시 "진행자1" (호스트/질문자/남성)과 "진행자2" (전문 해설자/스토리텔러/여성)의 2인 대화체로 작성하세요. ' +
                '각 대사 줄 맨 앞에 "진행자1: 대사..." 또는 "진행자2: 대사..." 형식으로 화자를 명시하고, ' +
                '진행자1이 흥미로운 질문과 현실적 리액션을 던지면 진행자2가 깊이 있는 사연과 사료를 전달하는 환상의 호흡을 구성하세요.'
            )
            isDialogueJson = 'true'
            speakersJson = '["진행자1", "진행자2"]'
            defaultSpeaker1 = '진행자1'
        } else {
            modeInstruction = '1인 심층 내레이션 (단독 나레이터 몰입형 스토리텔링)'
            modeSpecificRules = (
                '차분하고 흡입력 있는 1인 다큐멘터리/이야기꾼 내레이션으로 작성하세요. ' +
                '시청자에게 말을 건네듯 생생한 현장감과 감정의 고조를 살려 집필하세요.'
            )
            isDialogueJson = 'false'
            speakersJson = '["나레이터"]'
            defaultSpeaker1 = '나레이터'
        }

        const finalWriterPrompt = SCRIPT_WRITER_PROMPT
            .replace(/\{\{category\}\}/g, category)
            .replace(/\{\{duration_minutes\}\}/g, String(duration_minutes))
            .replace(/\{\{mode\}\}/g, mode)
            .replace(/\{\{mode_instruction\}\}/g, modeInstruction)
            .replace(/\{\{mode_specific_rules\}\}/g, modeSpecificRules)
            .replace(/\{\{research_summary\}\}/g, researchSummary)
            .replace(/\{\{source_text\}\}/g, String(source_text).slice(0, 15000))
            .replace(/\{\{is_dialogue_json\}\}/g, isDialogueJson)
            .replace(/\{\{speakers_json\}\}/g, speakersJson)
            .replace(/\{\{default_speaker_1\}\}/g, defaultSpeaker1)

        let parsed: any = null
        let usedEngine = 'claude-3-5-haiku'

        // 1순위: Claude 3.5 Haiku 호출
        if (claudeKey) {
            try {
                const claudeRes = await fetch('https://api.anthropic.com/v1/messages', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-api-key': claudeKey,
                        'anthropic-version': '2023-06-01'
                    },
                    body: JSON.stringify({
                        model: 'claude-3-5-haiku-20241022',
                        max_tokens: 8192,
                        temperature: 0.7,
                        messages: [
                            { role: 'user', content: finalWriterPrompt }
                        ]
                    })
                })

                if (claudeRes.ok) {
                    const cData = await claudeRes.json()
                    const rawContent = cData?.content?.[0]?.text || ''
                    const cleanJsonStr = rawContent.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/\s*```$/i, '').trim()
                    parsed = JSON.parse(cleanJsonStr)
                } else {
                    console.warn('Claude Haiku call failed, falling back to Gemini:', await claudeRes.text())
                }
            } catch (cErr) {
                console.warn('Claude Haiku error, falling back to Gemini:', cErr)
            }
        }

        // 2순위 (폴백): Gemini 2.5 Flash로 대본 집필
        if (!parsed) {
            usedEngine = 'gemini-2.5-flash'
            const geminiPayload = {
                contents: [{ parts: [{ text: finalWriterPrompt }] }],
                generationConfig: {
                    temperature: 0.7,
                    responseMimeType: 'application/json'
                }
            }
            const gRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${geminiKey}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(geminiPayload)
            })
            if (!gRes.ok) {
                throw new Error(`대본 생성 실패: ${gRes.status}`)
            }
            const gData = await gRes.json()
            const raw = gData?.candidates?.[0]?.content?.parts?.[0]?.text || '{}'
            const clean = raw.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/\s*```$/i, '').trim()
            parsed = JSON.parse(clean)
        }

        const finalTitle = custom_title?.trim() || parsed.title || `${category} - 노트북LM 심층 기획`

        // 프로젝트 생성 및 저장
        const projectId = `proj_nlm_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`
        const projectPayload = {
            id: projectId,
            title: finalTitle,
            category: category,
            language: 'ko',
            duration_minutes: duration_minutes,
            dialogue_mode: isDialogue,
            ai_engine: usedEngine,
            script: parsed.full_script || parsed.scenes?.map((s: any) => `${s.speaker ? `${s.speaker}: ` : ''}${s.scene_text}`).join('\n\n') || '',
            scenes: (parsed.scenes || []).map((s: any, idx: number) => ({
                id: idx + 1,
                scene_num: idx + 1,
                speaker: s.speaker || (isDialogue ? (idx % 2 === 0 ? '진행자1' : '진행자2') : '나레이터'),
                text: s.scene_text || '',
                prompt: s.image_prompt || '',
                visual_type: s.visual_type || (idx < 12 ? 'video' : 'image'),
                image_url: '',
                video_url: '',
                audio_url: '',
                duration: 5.0,
            })),
            suggested_voices: isDialogue ? {
                '진행자1': { gender: 'male', name: 'Roger - 남성 진행자' },
                '진행자2': { gender: 'female', name: 'Sarah - 여성 스토리텔러' },
            } : {
                '나레이터': { gender: 'female', name: 'Sarah - 차분한 나레이션' }
            },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
        }

        try {
            await supabaseAdmin.from('std_projects').insert({
                id: projectId,
                employee_email: auth.requester.email,
                title: finalTitle,
                status: 'image_prompted',
                language: 'ko',
                assigned_duration_minutes: duration_minutes,
                estimated_payout: 4.0,
                progress_payload: projectPayload,
                updated_at: new Date().toISOString(),
            })
        } catch (dbErr) {
            console.warn('[NotebookLM] Failed to insert std_projects:', dbErr)
        }

        return NextResponse.json({
            success: true,
            project: {
                id: projectId,
                title: finalTitle,
                status: 'image_prompted',
                project_payload: projectPayload,
            },
            dialogue_mode: isDialogue,
            engine: usedEngine,
            raw: parsed
        })

    } catch (e: any) {
        console.error('NotebookLM generation error:', e)
        return NextResponse.json({
            success: false,
            error: e.message || '노트북LM 대본 생성 중 오류가 발생했습니다.'
        }, { status: 500 })
    }
}