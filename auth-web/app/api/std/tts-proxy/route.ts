import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const maxDuration = 60

const GOOGLE_CLIENTS = ['tw-ob', 'gtx', 'dict-chrome-ex']

async function fetchGoogleChunk(chunk: string, lang = 'ko'): Promise<Buffer> {
    const text = chunk.trim()
    if (!text) return Buffer.alloc(0)

    let lastError: any = null
    for (const client of GOOGLE_CLIENTS) {
        try {
            const url = new URL('https://translate.google.com/translate_tts')
            url.searchParams.set('ie', 'UTF-8')
            url.searchParams.set('client', client)
            url.searchParams.set('tl', lang)
            url.searchParams.set('q', text)

            const res = await fetch(url.toString(), {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    Referer: 'https://translate.google.com/',
                    Accept: 'audio/mpeg,*/*',
                },
            })

            if (res.ok) {
                const arrayBuf = await res.arrayBuffer()
                if (arrayBuf.byteLength > 0) {
                    return Buffer.from(arrayBuf)
                }
            } else {
                lastError = new Error(`Google TTS client ${client} failed with status ${res.status}`)
            }
        } catch (e: any) {
            lastError = e
        }
    }

    throw lastError || new Error('Google TTS generation failed')
}

export async function POST(req: Request) {
    try {
        const body = await req.json().catch(() => ({}))
        const lang = String(body?.lang || 'ko').trim()

        // 1. If batch of chunks is provided
        if (Array.isArray(body?.chunks) && body.chunks.length > 0) {
            const chunkList: string[] = body.chunks.map((c: any) => String(c || '').trim()).filter(Boolean)
            if (chunkList.length === 0) {
                return NextResponse.json({ success: false, error: 'Chunks are empty' }, { status: 400 })
            }

            // Fetch chunks concurrently (up to 10 chunks per batch)
            const buffers = await Promise.all(chunkList.map(chunk => fetchGoogleChunk(chunk, lang)))
            const combined = Buffer.concat(buffers.filter(b => b.length > 0))

            return new NextResponse(new Uint8Array(combined), {
                headers: {
                    'Content-Type': 'audio/mpeg',
                    'Content-Length': String(combined.length),
                    'Cache-Control': 'public, max-age=86400',
                },
            })
        }

        // 2. Single chunk / text
        const text = String(body?.text || body?.chunk || '').trim()
        if (!text) {
            return NextResponse.json({ success: false, error: 'Text is required' }, { status: 400 })
        }

        const buffer = await fetchGoogleChunk(text, lang)
        return new NextResponse(new Uint8Array(buffer), {
            headers: {
                'Content-Type': 'audio/mpeg',
                'Content-Length': String(buffer.length),
                'Cache-Control': 'public, max-age=86400',
            },
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'TTS proxy error' }, { status: 500 })
    }
}

export async function GET(req: Request) {
    const url = new URL(req.url)
    const text = String(url.searchParams.get('text') || url.searchParams.get('q') || '').trim()
    const lang = String(url.searchParams.get('lang') || url.searchParams.get('tl') || 'ko').trim()

    if (!text) {
        return NextResponse.json({ success: false, error: 'Text query parameter is required' }, { status: 400 })
    }

    try {
        const buffer = await fetchGoogleChunk(text, lang)
        return new NextResponse(new Uint8Array(buffer), {
            headers: {
                'Content-Type': 'audio/mpeg',
                'Content-Length': String(buffer.length),
                'Cache-Control': 'public, max-age=86400',
            },
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'TTS proxy error' }, { status: 500 })
    }
}
