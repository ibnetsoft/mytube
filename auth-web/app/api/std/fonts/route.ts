import { NextResponse } from 'next/server'

const subtitleFonts = [
    'GmarketSansBold',
    'TmonMonsori',
    'Jalnan',
    'Pretendard-Bold',
    'NanumSquareExtraBold',
    'BinggraeMelona-Bold',
    'NetmarbleB',
    'ChosunIlboMyungjo',
    'MapoFlowerIsland',
    'S-CoreDream-6Bold',
    'Gungsuh',
]

export function GET() {
    return NextResponse.json(
        { success: true, fonts: subtitleFonts },
        { headers: { 'Cache-Control': 'public, max-age=3600' } },
    )
}
