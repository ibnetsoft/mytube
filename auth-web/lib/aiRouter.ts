import { GoogleGenAI } from '@google/genai'
import type { SupabaseClient } from '@supabase/supabase-js'

export function detectProvider(model: string): 'claude' | 'gemini' {
    return String(model || '').trim().toLowerCase().startsWith('claude') ? 'claude' : 'gemini'
}

const FALLBACK_GEMINI_MODEL = 'gemini-2.5-flash'

async function callClaude(supabaseAdmin: SupabaseClient, prompt: string, model: string): Promise<string> {
    let claudeApiKey = process.env.CLAUDE_API_KEY
    if (!claudeApiKey) {
        const { data } = await supabaseAdmin
            .from('global_settings')
            .select('value')
            .eq('key', 'sys_api_claude')
            .maybeSingle()
        claudeApiKey = data?.value
    }
    if (!claudeApiKey) throw new Error('Claude API key is not configured')

    const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'x-api-key': claudeApiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        body: JSON.stringify({
            model,
            max_tokens: 8192,
            messages: [{ role: 'user', content: prompt }],
        }),
    })
    if (!res.ok) {
        const errText = await res.text().catch(() => '')
        throw new Error(`Claude API error ${res.status}: ${errText.slice(0, 300)}`)
    }
    const json = await res.json()
    const text = json?.content?.[0]?.text
    if (!text) throw new Error('Claude API returned no text content')
    return text
}

async function callGemini(geminiApiKey: string, prompt: string, model: string = FALLBACK_GEMINI_MODEL): Promise<string> {
    const ai = new GoogleGenAI({ apiKey: geminiApiKey })
    const response = await ai.models.generateContent({
        model,
        contents: prompt,
        config: { responseMimeType: 'application/json' },
    })
    return response.text || '[]'
}

// AIR-0225: routes a JSON-generation prompt to whichever provider the admin
// selected via the "AI 모델 선택" dropdowns (e.g. sys_api_topic_generation_model),
// mirroring services/ai_router.py's Claude-prefix detection + Gemini fallback
// on the desktop app side. Without this, auth-web's own AI calls (topic
// generation, translation) silently ignored the admin's model selection and
// always used Gemini regardless of what was saved.
export async function generateJsonWithModelSetting(
    supabaseAdmin: SupabaseClient,
    prompt: string,
    modelSettingKey: string,
    geminiApiKey: string
): Promise<string> {
    const { data: settingRow } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', modelSettingKey)
        .maybeSingle()
    const selectedModel = String(settingRow?.value || '').trim()
    const provider = detectProvider(selectedModel)

    if (provider === 'claude') {
        try {
            console.log(`[AI Router] Using Claude for ${modelSettingKey} (model=${selectedModel})`)
            return await callClaude(supabaseAdmin, prompt, selectedModel)
        } catch (err) {
            console.warn(`[AI Router] Claude failed for ${modelSettingKey}, falling back to Gemini:`, err)
            return await callGemini(geminiApiKey, prompt)
        }
    }

    return await callGemini(geminiApiKey, prompt, selectedModel || FALLBACK_GEMINI_MODEL)
}
