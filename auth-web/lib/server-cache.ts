type CacheEntry = {
    value: unknown
    expiresAt: number
}

const memoryCache = new Map<string, CacheEntry>()

const redisUrl = process.env.UPSTASH_REDIS_REST_URL
const redisToken = process.env.UPSTASH_REDIS_REST_TOKEN

function isRedisEnabled() {
    return Boolean(redisUrl && redisToken)
}

async function redisCommand(args: unknown[]) {
    if (!isRedisEnabled()) return null

    try {
        const res = await fetch(`${redisUrl}/pipeline`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${redisToken}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify([args]),
            cache: 'no-store',
        })

        if (!res.ok) return null
        const payload = await res.json()
        return Array.isArray(payload) ? payload[0]?.result : null
    } catch {
        return null
    }
}

export async function getServerCache<T>(key: string): Promise<T | null> {
    const now = Date.now()
    const memoryEntry = memoryCache.get(key)
    if (memoryEntry && memoryEntry.expiresAt > now) {
        return memoryEntry.value as T
    }
    if (memoryEntry) memoryCache.delete(key)

    const raw = await redisCommand(['GET', key])
    if (!raw || typeof raw !== 'string') return null

    try {
        return JSON.parse(raw) as T
    } catch {
        return null
    }
}

export async function setServerCache<T>(key: string, value: T, ttlSeconds: number) {
    const expiresAt = Date.now() + ttlSeconds * 1000
    memoryCache.set(key, { value, expiresAt })

    const serialized = JSON.stringify(value)
    await redisCommand(['SET', key, serialized, 'EX', ttlSeconds])
}

export async function deleteServerCache(key: string) {
    memoryCache.delete(key)
    await redisCommand(['DEL', key])
}
