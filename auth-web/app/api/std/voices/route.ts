import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export const ELEVENLABS_PRESET_VOICES = [
    {
        id: 'n2fbxG88jqAoaVPUy3IG',
        name: 'Yooni (한국어 여성 · 자연스럽고 맑은 전달력)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '차분하고 또렷한 한국어 스토리텔링 및 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/n2fbxG88jqAoaVPUy3IG.mp3',
    },
    {
        id: 'aiUUgjHa4mpHf6UenZuf',
        name: 'Mina (한국어 여성 · 따뜻하고 감성적인 톤)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '감동적인 이야기, 회상, 따뜻한 전기수 낭독',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/aiUUgjHa4mpHf6UenZuf.mp3',
    },
    {
        id: '5n5gqmaQi9Ewevrz7bOS',
        name: 'Sian (한국어 여성 · 다정하고 부드러운 목소리)',
        gender: 'female',
        category: 'professional',
        language: 'ko',
        description: '친절하고 차분한 어조의 드라마 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/5n5gqmaQi9Ewevrz7bOS.mp3',
    },
    {
        id: 'JBFqnCBsd6RMkjVDRZzb',
        name: 'George (한국어/다국어 남성 · 옛날이야기 구연동화 추천)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '몰입감 넘치는 전통 이야기꾼, 전기수 스타일',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/JBFqnCBsd6RMkjVDRZzb.mp3',
    },
    {
        id: '7p1Ofvcwsv7UBPoFNcpI',
        name: 'Julian (한국어/다국어 남성 · 중후하고 깊은 목소리)',
        gender: 'male',
        category: 'professional',
        language: 'ko',
        description: '다큐멘터리 및 웅장한 역사 드라마 나레이션',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/7p1Ofvcwsv7UBPoFNcpI.mp3',
    },
    {
        id: 'nPczCjzI2devNBz1zQrb',
        name: 'Brian (한국어/다국어 남성 · 편안하고 신뢰감 있는 톤)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '안정적이고 편안한 휴먼 드라마 톤',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/nPczCjzI2devNBz1zQrb.mp3',
    },
    {
        id: 'EXAVITQu4vr4xnSDxMaL',
        name: 'Sarah (한국어/다국어 여성 · 성숙하고 자신감 있는 어조)',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: '지적이고 안정된 전문 성우 톤',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/EXAVITQu4vr4xnSDxMaL.mp3',
    },
    {
        id: 'hpp4J3VqNfWAUOO0d1Us',
        name: 'Bella (한국어/다국어 여성 · 밝고 프로페셔널한 톤)',
        gender: 'female',
        category: 'premade',
        language: 'ko',
        description: '경쾌하고 생동감 넘치는 대사 및 해설',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/hpp4J3VqNfWAUOO0d1Us.mp3',
    },
    {
        id: 'pNInz6obpgDQGcFmaJgB',
        name: 'Adam (한국어/다국어 남성 · 무게감 있고 단호한 톤)',
        gender: 'male',
        category: 'premade',
        language: 'ko',
        description: '강렬한 씬 전환 및 카리스마 있는 목소리',
        preview_url: 'https://storage.googleapis.com/eleven-public-prod/previews/pNInz6obpgDQGcFmaJgB.mp3',
    },
]

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    return NextResponse.json({
        success: true,
        provider: 'elevenlabs',
        model_id: 'eleven_multilingual_v2',
        voices: ELEVENLABS_PRESET_VOICES,
    })
}
