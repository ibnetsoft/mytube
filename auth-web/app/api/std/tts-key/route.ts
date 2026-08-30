import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { getConfiguredElevenLabsKeys } from '@/lib/elevenLabsKeys'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const elevenLabsKeys = await getConfiguredElevenLabsKeys()

    if (!elevenLabsKeys.length) {
        return NextResponse.json({ success: false, error: 'ElevenLabs API key not configured' }, { status: 500 })
    }

    return NextResponse.json({
        success: true,
        elevenlabs_key: elevenLabsKeys[0],
        elevenlabs_key_count: elevenLabsKeys.length,
    })
}
