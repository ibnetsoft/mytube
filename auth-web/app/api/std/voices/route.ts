import { NextResponse } from 'next/server'
import { getConfiguredElevenLabsKeys } from '@/lib/elevenLabsKeys'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

const ELEVENLABS_PRESET_VOICES = [
    {
        id: 'CwhRBWXzGAHq8TQ4Fs17',
        name: 'Roger - Laid-Back, Casual, Resonant',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Easy going and perfect for casual conversations.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/CwhRBWXzGAHq8TQ4Fs17/58ee3ff5-f6f2-4628-93b8-e38eb31806b0.mp3',
    },
    {
        id: 'EXAVITQu4vr4xnSDxMaL',
        name: 'Sarah - Mature, Reassuring, Confident',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Young adult woman with a confident and warm, mature quality and a reassuring, professional tone.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/EXAVITQu4vr4xnSDxMaL/01a3e33c-6e99-4ee7-8543-ff2216a32186.mp3',
    },
    {
        id: 'FGY2WhTYpPnrIDTdsKH5',
        name: 'Laura - Enthusiast, Quirky Attitude',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'This young adult female voice delivers sunny enthusiasm with a quirky attitude.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/FGY2WhTYpPnrIDTdsKH5/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI2NzM0MTc1OS1hZDA4LTQxYTUtYmU2ZS1kZTEyZmU0NDg2MTgubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'IKne3meq5aSn9XLyUdCD',
        name: 'Charlie - Deep, Confident, Energetic',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A young Australian male with a confident and energetic voice.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/IKne3meq5aSn9XLyUdCD/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIxMDJkZTZmMi0yMmVkLTQzZTAtYTFmMS0xMTFmYTc1YzU0ODEubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'JBFqnCBsd6RMkjVDRZzb',
        name: 'George - Warm, Captivating Storyteller',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Warm resonance that instantly captivates listeners.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/JBFqnCBsd6RMkjVDRZzb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiJlNjIwNmQxYS0wNzIxLTQ3ODctYWFmYi0wNmE2ZTcwNWNhYzUubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'N2lVS1w4EtoT3dr4eOWO',
        name: 'Callum - Husky Trickster',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Deceptively gravelly, yet unsettling edge.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/N2lVS1w4EtoT3dr4eOWO/ac833bd8-ffda-4938-9ebc-b0f99ca25481.mp3',
    },
    {
        id: 'SAz9YHcvj6GT2YYXdXww',
        name: 'River - Relaxed, Neutral, Informative',
        gender: 'neutral',
        category: 'premade',
        language: 'ko',
        description: 'A relaxed, neutral voice ready for narrations or conversational projects.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/SAz9YHcvj6GT2YYXdXww/e6c95f0b-2227-491a-b3d7-2249240decb7.mp3',
    },
    {
        id: 'SOYHLrjzK2X1ezoPC6cr',
        name: 'Harry - Fierce Warrior',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'An animated warrior ready to charge forward.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/SOYHLrjzK2X1ezoPC6cr/86d178f6-f4b6-4e0e-85be-3de19f490794.mp3',
    },
    {
        id: 'TX3LPaxmHKxFdv7VOQHJ',
        name: 'Liam - Energetic, Social Media Creator',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A young adult with energy and warmth - suitable for reels and shorts.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/TX3LPaxmHKxFdv7VOQHJ/63148076-6363-42db-aea8-31424308b92c.mp3',
    },
    {
        id: 'Xb7hH8MSUJpSbSDYk0k2',
        name: 'Alice - Clear, Engaging Educator',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Clear and engaging, friendly woman with a British accent suitable for e-learning.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/Xb7hH8MSUJpSbSDYk0k2/d10f7534-11f6-41fe-a012-2de1e482d336.mp3',
    },
    {
        id: 'XrExE9yKIg1WjnnlVkGX',
        name: 'Matilda - Knowledgable, Professional',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'A professional woman with a pleasing alto pitch. Suitable for many use cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/XrExE9yKIg1WjnnlVkGX/b930e18d-6b4d-466e-bab2-0ae97c6d8535.mp3',
    },
    {
        id: 'bIHbv24MWmeRgasZH58o',
        name: 'Will - Relaxed Optimist',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Conversational and laid back.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/bIHbv24MWmeRgasZH58o/8caf8f3d-ad29-4980-af41-53f20c72d7a4.mp3',
    },
    {
        id: 'cgSgspJ2msm6clMCkdW9',
        name: 'Jessica - Playful, Bright, Warm',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Young and popular, this playful American female voice is perfect for trendy content.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/cgSgspJ2msm6clMCkdW9/56a97bf8-b69b-448f-846c-c3a11683d45a.mp3',
    },
    {
        id: 'cjVigY5qzO86Huf0OWal',
        name: 'Eric - Smooth, Trustworthy',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A smooth tenor pitch from a man in his 40s - perfect for agentic use cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/cjVigY5qzO86Huf0OWal/d098fda0-6456-4030-b3d8-63aa048c9070.mp3',
    },
    {
        id: 'hpp4J3VqNfWAUOO0d1Us',
        name: 'Bella - Professional, Bright, Warm',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'This voice is warm, bright, and professional, characterized by a Standard American accent and a polished, narrative quality. It features a medium-high pitch with crisp diction and a deliberate, rhythmic pace that makes it highly intelligible and engaging for long-form listening.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/hpp4J3VqNfWAUOO0d1Us/dab0f5ba-3aa4-48a8-9fad-f138fea1126d.mp3',
    },
    {
        id: 'iP95p4xoKVk53GoZ742B',
        name: 'Chris - Charming, Down-to-Earth',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Natural and real, this down-to-earth voice is great across many use-cases.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/iP95p4xoKVk53GoZ742B/3f4bde72-cc48-40dd-829f-57fbf906f4d7.mp3',
    },
    {
        id: 'nPczCjzI2devNBz1zQrb',
        name: 'Brian - Deep, Resonant and Comforting',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Middle-aged man with a resonant and comforting tone. Great for narrations and advertisements.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/nPczCjzI2devNBz1zQrb/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiIyZGQzZTcyYy00ZmQzLTQyZjEtOTNlYS1hYmM1ZDRlNWFhMWQubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'onwK4e9ZLuTAKqWW03F9',
        name: 'Daniel - Steady Broadcaster',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A strong voice perfect for delivering a professional broadcast or news story.',
        preview_url: 'https://api.us.elevenlabs.io/v1/voices/onwK4e9ZLuTAKqWW03F9/previews/audio?payload=eyJ2b2ljZV9zb3VyY2UiOiJwcmVtYWRlIiwiZmlsZW5hbWUiOiI3ZWVlMDIzNi0xYTcyLTRiODYtYjMwMy01ZGNhZGMwMDdiYTkubXAzIiwidGltZXN0YW1wIjoxNzg3MTA4NDAwMDAwMDAwfQ%3D%3D',
    },
    {
        id: 'pFZP5JQG7iQjIQuC4Bku',
        name: 'Lily - Velvety Actress',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: 'Velvety British female voice delivers news and narrations with warmth and clarity.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pFZP5JQG7iQjIQuC4Bku/89b68b35-b3dd-4348-a84a-a3c13a3c2b30.mp3',
    },
    {
        id: 'pNInz6obpgDQGcFmaJgB',
        name: 'Adam - Dominant, Firm',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'A bright tenor pitch that immediately cuts through. The delivery is brash and openly confident, speaking with unwavering certainty and a slightly aggressive self-assurance.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pNInz6obpgDQGcFmaJgB/d6905d7a-dd26-4187-bfff-1bd3a5ea7cac.mp3',
    },
    {
        id: 'pqHfZKP75CvOlQylNhV4',
        name: 'Bill - Wise, Mature, Balanced',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: 'Friendly and comforting voice ready to narrate your stories.',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/premade/voices/pqHfZKP75CvOlQylNhV4/d782b3ff-84ba-4029-848c-acf01285524d.mp3',
    },
]

import { createClient } from '@supabase/supabase-js'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

async function getGlobalSetting(key: string): Promise<string> {
    const { data, error } = await getAdmin()
        .from('global_settings')
        .select('value')
        .eq('key', key)
        .maybeSingle()
    if (error) throw error
    return String(data?.value || '').trim()
}

const loadCustomVoices = async (): Promise<any[]> => {
    try {
        const sb = getAdmin()
        const { data, error } = await sb
            .from('global_settings')
            .select('value')
            .eq('key', 'custom_voices')
            .maybeSingle()
        if (error || !data?.value) return []
        const parsed = typeof data.value === 'string' ? JSON.parse(data.value) : data.value
        if (!Array.isArray(parsed)) return []
        return parsed.map((item: any) => ({
            id: String(item?.voice_id || item?.id || '').trim(),
            name: String(item?.name || '').trim(),
            gender: item?.gender === 'male' ? 'male' : 'female',
            category: String(item?.category || 'custom').trim(),
            language: String(item?.language || 'ko').trim(),
            description: String(item?.description || '').trim(),
            preview_url: String(item?.preview_url || '').trim(),
        })).filter(item => item.id && item.name)
    } catch {
        return []
    }
}

async function inspectKeyRemaining(apiKey: string) {
    try {
        const res = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
            headers: {
                'xi-api-key': apiKey,
                Accept: 'application/json',
            },
            cache: 'no-store',
        })
        if (!res.ok) return null
        const data = await res.json().catch(() => ({}))
        const limit = Number(data?.character_limit || 0)
        const used = Number(data?.character_count || 0)
        return Number.isFinite(limit) && Number.isFinite(used) && limit > 0
            ? Math.max(0, limit - used)
            : null
    } catch {
        return null
    }
}

async function loadElevenLabsVoicesForKey(apiKey: string) {
    const res = await fetch('https://api.elevenlabs.io/v1/voices?show_legacy=true', {
        headers: { 'xi-api-key': apiKey },
        cache: 'no-store',
    })
    if (!res.ok) return []
    const data = await res.json().catch(() => ({}))
    return (data.voices || []).map((v: any) => {
        const labels = v.labels || {}
        const g = labels.gender || (['mina', 'sian', 'yooni', 'sarah', 'bella', 'alice', 'lily', 'laura', 'jessica', 'selly', 'saori'].some(w => (v.name || '').toLowerCase().includes(w)) ? 'female' : 'male')
        return {
            id: v.voice_id,
            name: v.name,
            gender: g,
            category: v.category || 'premade',
            language: 'ko',
            description: labels.description || v.description || '',
            preview_url: v.preview_url || '',
        }
    }).filter((voice: any) => voice.id && voice.name)
}

export async function GET(req: Request) {
    // Voices list is safe for both authenticated users and initial guest preview

    const customVoices = await loadCustomVoices()
    const requestUrl = new URL(req.url)
    const requiredChars = Math.max(0, Number.parseInt(requestUrl.searchParams.get('requiredChars') || '0', 10) || 0)
    const requiredBufferChars = requiredChars > 0 ? Math.ceil(requiredChars * 1.03) : 0

    let apiVoices: any[] = []
    const usableVoiceIds = new Set<string>()
    const keyStatus: Array<{ keySlot: number; remaining: number | null; usable: boolean; voice_count: number }> = []
    try {
        const apiKeys = await getConfiguredElevenLabsKeys()
        for (const [index, apiKey] of apiKeys.entries()) {
            const remaining = await inspectKeyRemaining(apiKey)
            const usable = requiredBufferChars <= 0 || remaining == null || remaining >= requiredBufferChars
            if (!usable) {
                keyStatus.push({ keySlot: index + 1, remaining, usable: false, voice_count: 0 })
                continue
            }
            const voices = await loadElevenLabsVoicesForKey(apiKey)
            for (const voice of voices) {
                const id = String(voice.id || '').trim()
                if (!id || usableVoiceIds.has(id)) continue
                usableVoiceIds.add(id)
                apiVoices.push(voice)
            }
            keyStatus.push({ keySlot: index + 1, remaining, usable: true, voice_count: voices.length })
        }
    } catch (e) {
        console.error('Failed to fetch dynamic ElevenLabs voices:', e)
    }

    const FREE_ALTERNATIVE_VOICES = [
        {
            id: 'google_kr',
            name: 'Google 한국어 (무료 TTS)',
            gender: 'neutral',
            category: 'google',
            language: 'ko',
            description: '무료 Google 한국어 TTS입니다. 긴 대본은 자동 분할 초고속 생성됩니다.',
            preview_url: '/api/std/tts-proxy?text=%EC%95%88%EB%85%95%ED%95%98%EC%84%B8%EC%9A%94.+Google+%ED%95%9C%EA%B5%AD%EC%96%B4+%EB%AC%B4%EB%A3%8C+TTS+%EC%9E%85%EB%8B%88%EB%8B%A4.',
        },
    ]

    const hasRequiredTextFilter = requiredBufferChars > 0
    const hasConfiguredKeyResult = keyStatus.length > 0
    const baseList = apiVoices.length > 0
        ? apiVoices
        : (hasRequiredTextFilter && hasConfiguredKeyResult ? [] : ELEVENLABS_PRESET_VOICES)
    const accessibleVoiceIds = new Set(apiVoices.map(voice => String(voice.id || '').trim()))
    const availableCustomVoices = apiVoices.length > 0
        ? customVoices.filter(voice => accessibleVoiceIds.has(String(voice.id || '').trim()))
        : []

    // Account-specific custom voices must disappear when the configured primary key changes.
    const combinedMap = new Map<string, any>()
    for (const fv of FREE_ALTERNATIVE_VOICES) {
        if (!combinedMap.has(fv.id)) {
            combinedMap.set(fv.id, fv)
        }
    }
    for (const bv of baseList) {
        if (!combinedMap.has(bv.id)) {
            combinedMap.set(bv.id, bv)
        }
    }
    for (const cv of availableCustomVoices) {
        const liveVoice = combinedMap.get(cv.id)
        combinedMap.set(cv.id, {
            ...cv,
            ...liveVoice,
            name: liveVoice?.name || cv.name,
            description: liveVoice?.description || cv.description,
            preview_url: liveVoice?.preview_url || cv.preview_url,
        })
    }

    const mergedVoices = Array.from(combinedMap.values())

    return NextResponse.json({
        success: true,
        provider: 'elevenlabs',
        model_id: 'eleven_multilingual_v2',
        required_chars: requiredChars,
        key_status: keyStatus,
        voices: mergedVoices.length > 0 ? mergedVoices : FREE_ALTERNATIVE_VOICES,
    })
}
