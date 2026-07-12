import { NextRequest } from 'next/server'
import { reportJobOutcome } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    return reportJobOutcome(req, params.jobId, true)
}
