import { NextRequest, NextResponse } from 'next/server'
import { POST as register } from '../../internal/worker/register/route'
import { POST as heartbeat } from '../../internal/worker/heartbeat/route'
import { POST as claim } from '../../internal/worker/jobs/claim/route'
import { POST as complete } from '../../internal/worker/jobs/[jobId]/complete/route'
import { POST as fail } from '../../internal/worker/jobs/[jobId]/fail/route'
import { POST as progress } from '../../internal/worker/jobs/[jobId]/progress/route'
import { POST as renew } from '../../internal/worker/jobs/[jobId]/renew/route'

export const dynamic = 'force-dynamic'

type RouteContext = { params: { path: string[] } }

export async function POST(req: NextRequest, { params }: RouteContext) {
    const segments = params.path || []
    const route = segments.join('/')

    if (route === 'register') return register(req)
    if (route === 'heartbeat') return heartbeat(req)
    if (route === 'jobs/claim') return claim(req)

    if (segments.length === 3 && segments[0] === 'jobs') {
        const jobContext = { params: { jobId: segments[1] } }
        if (segments[2] === 'complete') return complete(req, jobContext)
        if (segments[2] === 'fail') return fail(req, jobContext)
        if (segments[2] === 'progress') return progress(req, jobContext)
        if (segments[2] === 'renew') return renew(req, jobContext)
    }

    return NextResponse.json({ error: 'not_found' }, { status: 404 })
}
