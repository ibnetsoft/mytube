import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, isHermesWorker, logWorkerAuditEvent, readJsonBodyWithLimit } from '@/lib/workerAuth'
import { DEFAULT_QUALITY_POLICY, normalizeQualityPolicy, QUALITY_POLICY_KEY } from '@/lib/qualityPolicy'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response
    if (!isHermesWorker(auth.worker)) return NextResponse.json({ error: 'forbidden' }, { status: 403 })
    const { data, error } = await supabaseAdmin
        .from('quality_policies')
        .select('policy_key, version, policy, updated_by, updated_at')
        .eq('policy_key', QUALITY_POLICY_KEY)
        .maybeSingle()
    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })
    return NextResponse.json(data || {
        policy_key: QUALITY_POLICY_KEY, version: 0, policy: DEFAULT_QUALITY_POLICY,
        updated_by: 'bundled-default', updated_at: null,
    })
}

export async function PUT(req: NextRequest) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response
    if (!isHermesWorker(auth.worker)) return NextResponse.json({ error: 'forbidden' }, { status: 403 })
    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const expectedVersion = Number(bodyResult.body?.expected_version)
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) {
        return NextResponse.json({ error: 'invalid_request', detail: 'expected_version is required' }, { status: 400 })
    }
    const policy = normalizeQualityPolicy(bodyResult.body?.policy)
    const updatedBy = `worker:${auth.worker.worker_id}`
    const { data, error } = await supabaseAdmin
        .from('quality_policies')
        .update({ policy, version: expectedVersion + 1, updated_by: updatedBy, updated_at: new Date().toISOString() })
        .eq('policy_key', QUALITY_POLICY_KEY)
        .eq('version', expectedVersion)
        .select('policy_key, version, policy, updated_by, updated_at')
        .maybeSingle()
    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })
    if (!data) return NextResponse.json({ error: 'version_conflict', detail: 'Policy changed. Reload and retry.' }, { status: 409 })
    await logWorkerAuditEvent({
        worker_id: auth.worker.worker_id, event_type: 'quality_policy_updated',
        detail: { policy_key: QUALITY_POLICY_KEY, from_version: expectedVersion, to_version: data.version },
    })
    return NextResponse.json(data)
}
