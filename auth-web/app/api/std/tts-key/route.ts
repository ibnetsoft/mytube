import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { getConfiguredElevenLabsKeys } from '@/lib/elevenLabsKeys'

export const dynamic = 'force-dynamic'

async function getElevenLabsRemaining(apiKey: string): Promise<number | null> {
    try {
        const res = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
            headers: { 'xi-api-key': apiKey },
            cache: 'no-store',
        })
        if (!res.ok) return null
        const data = await res.json().catch(() => null)
        const used = Number(data?.character_count)
        const limit = Number(data?.character_limit)
        if (!Number.isFinite(used) || !Number.isFinite(limit)) return null
        return Math.max(0, limit - used)
    } catch {
        return null
    }
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const requiredChars = Math.max(0, Number.parseInt(url.searchParams.get('requiredChars') || '0', 10) || 0)
    const requiredBufferChars = requiredChars > 0 ? Math.ceil(requiredChars * 1.03) : 0
    const elevenLabsKeys = await getConfiguredElevenLabsKeys()

    if (!elevenLabsKeys.length) {
        return NextResponse.json({ success: false, error: 'ElevenLabs API key not configured' }, { status: 500 })
    }

    const keyStatus = []
    for (const [index, apiKey] of elevenLabsKeys.entries()) {
        const remaining = await getElevenLabsRemaining(apiKey)
        const usable = remaining == null || requiredBufferChars <= 0 || remaining >= requiredBufferChars
        keyStatus.push({ keySlot: index + 1, remaining, usable })
        if (usable) {
            return NextResponse.json({
                success: true,
                elevenlabs_key: apiKey,
                elevenlabs_key_slot: index + 1,
                elevenlabs_key_count: elevenLabsKeys.length,
                elevenlabs_key_remaining: remaining,
                key_status: keyStatus,
            }, {
                headers: { 'Cache-Control': 'no-store, max-age=0' },
            })
        }
    }

    return NextResponse.json({
        success: false,
        error: 'ElevenLabs 사용 가능한 키가 없습니다. 워커 설정의 ElevenLabs 키를 충전하거나 사용 가능한 키로 교체해주세요.',
        elevenlabs_key_count: elevenLabsKeys.length,
        key_status: keyStatus,
    }, { status: 503 })
}
