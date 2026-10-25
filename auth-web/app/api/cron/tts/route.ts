import { timingSafeEqual } from 'crypto'
import { NextResponse } from 'next/server'
import { processTtsJobs } from '@/lib/stdTtsJobs'
export const dynamic = 'force-dynamic'
export const maxDuration = 300
export async function GET(req: Request) {
    const expected = process.env.CRON_SECRET ? `Bearer ${process.env.CRON_SECRET}` : ''
    const actual = req.headers.get('authorization') || ''
    if (!expected || actual.length !== expected.length || !timingSafeEqual(Buffer.from(actual), Buffer.from(expected))) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json(await processTtsJobs())
}
