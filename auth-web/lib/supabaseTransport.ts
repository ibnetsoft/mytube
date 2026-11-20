// Per-process protection during database outages. Never replay a write: a lost
// response does not tell us whether Postgres committed it.
export function createSupabaseTransport(options: {
    fetch?: typeof fetch; now?: () => number; timeoutMs?: number; cooldownMs?: number
} = {}): typeof fetch {
    const send = options.fetch || fetch
    const now = options.now || Date.now
    const timeoutMs = options.timeoutMs ?? 10_000
    const cooldownMs = options.cooldownMs ?? 30_000
    let openUntil = 0
    let probing = false
    const unavailable = () => new Response(JSON.stringify({
        code: 'SUPABASE_TEMPORARILY_UNAVAILABLE',
        message: '데이터베이스 연결이 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요.',
    }), { status: 503, headers: { 'Content-Type': 'application/json', 'Retry-After': String(Math.ceil(cooldownMs / 1000)) } })

    return async (input, init) => {
        if (openUntil && (now() < openUntil || probing)) return unavailable()
        const probe = openUntil !== 0
        if (probe) probing = true
        const callerSignal = init?.signal || (input instanceof Request ? input.signal : undefined)
        const controller = new AbortController()
        const cancel = () => controller.abort(callerSignal?.reason)
        if (callerSignal?.aborted) cancel()
        else callerSignal?.addEventListener('abort', cancel, { once: true })
        const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
        // Large project saves and render claims may legitimately take longer.
        // Bound interactive reads/auth without truncating those writes at 10s.
        const url = String(input instanceof Request ? input.url : input)
        const budget = options.timeoutMs ?? (['GET', 'HEAD'].includes(method) || url.includes('/auth/v1/') ? timeoutMs : 60_000)
        const timer = setTimeout(() => controller.abort(new DOMException('Database request timed out', 'TimeoutError')), budget)
        try {
            const response = await send(input, { ...init, cache: 'no-store', signal: controller.signal })
            if (response.status >= 500) openUntil = now() + cooldownMs
            else openUntil = 0
            return response
        } catch (error) {
            if (callerSignal?.aborted) throw error
            openUntil = now() + cooldownMs
            return unavailable()
        } finally {
            clearTimeout(timer)
            callerSignal?.removeEventListener('abort', cancel)
            if (probe) probing = false
        }
    }
}

export const supabaseTransport = createSupabaseTransport()
