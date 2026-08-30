import { supabaseAdmin } from '@/lib/supabaseAdmin'

export function isUsableElevenLabsKey(value: string): boolean {
    const normalized = String(value || '').trim()
    if (!normalized) return false
    if (/^[•*]+$/.test(normalized)) return false
    return !['undefined', 'null', '(미설정)', '(unset)'].includes(normalized.toLowerCase())
}

export function normalizeElevenLabsKeyPool(...values: string[]): string[] {
    const keys: string[] = []
    for (const raw of values) {
        for (const part of String(raw || '').split(/[\s,;\r\n]+/)) {
            const key = part.trim()
            if (isUsableElevenLabsKey(key) && !keys.includes(key)) keys.push(key)
            if (keys.length >= 4) return keys
        }
    }
    return keys
}

export async function getConfiguredElevenLabsKeys(): Promise<string[]> {
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', ['sys_api_elevenlabs', 'sys_api_elevenlabs_keys'])

    const settings = Object.fromEntries((data || []).map(row => [row.key, String(row.value || '')]))
    const adminKeys = normalizeElevenLabsKeyPool(
        settings.sys_api_elevenlabs,
        settings.sys_api_elevenlabs_keys,
    )

    // Once an administrator has configured keys, stale deployment variables must not join the pool.
    if (adminKeys.length > 0) return adminKeys

    return normalizeElevenLabsKeyPool(
        process.env.ELEVENLABS_API_KEY || '',
        process.env.ELEVENLABS_API_KEYS || '',
    )
}
