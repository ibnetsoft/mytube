/** Serial polling: hidden tabs pause; slow requests cannot overlap; errors back off. */
export function startVisiblePolling(task: (signal: AbortSignal) => Promise<number | void>, intervalMs: number) {
    let stopped = false, running = false, failures = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    const run = async () => {
        if (stopped || running || document.hidden) return
        running = true
        controller = new AbortController()
        const timeout = setTimeout(() => controller?.abort(), 20000)
        let delay = intervalMs
        try {
            const nextDelay = await task(controller.signal)
            failures = 0
            if (typeof nextDelay === 'number') delay = Math.max(intervalMs, nextDelay)
        } catch {
            failures++
            delay = Math.min(120000, intervalMs * 2 ** Math.min(failures, 5))
        } finally {
            clearTimeout(timeout)
            running = false
            if (!stopped && !document.hidden) timer = setTimeout(() => void run(), delay)
        }
    }
    const visibility = () => {
        clearTimeout(timer)
        if (!document.hidden) void run()
    }
    document.addEventListener('visibilitychange', visibility)
    void run()
    return () => {
        stopped = true
        clearTimeout(timer)
        controller?.abort()
        document.removeEventListener('visibilitychange', visibility)
    }
}
