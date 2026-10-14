import { createCipheriv, createDecipheriv, createHash, createHmac, randomBytes, timingSafeEqual } from 'crypto'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from './supabaseAdmin'
import { getGoogleDriveConfig, type GoogleDriveConfig } from './googleDriveConfig'

const CALLBACK = '/api/admin/google-drive/oauth/callback'
const PREFIX = 'std_youtube_oauth_state_'
const CHANNEL_PREFIX = 'std_youtube_channel_'
const SCOPE = 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'

export function protectYoutubeCredentials(value: any, secret: string): string {
    const iv = randomBytes(12)
    const cipher = createCipheriv('aes-256-gcm', createHash('sha256').update(secret).digest(), iv)
    const data = Buffer.concat([cipher.update(JSON.stringify(value), 'utf8'), cipher.final()])
    return [iv, cipher.getAuthTag(), data].map(b => b.toString('base64url')).join('.')
}
export function readYoutubeCredentials(value: string, secret: string): any {
    const [iv, tag, data] = value.split('.').map(s => Buffer.from(s, 'base64url'))
    const decipher = createDecipheriv('aes-256-gcm', createHash('sha256').update(secret).digest(), iv)
    decipher.setAuthTag(tag)
    return JSON.parse(Buffer.concat([decipher.update(data), decipher.final()]).toString('utf8'))
}

export async function startYoutubeChannelOAuth(origin: string, categoryId: number, localChannelId: number) {
    const config = await getGoogleDriveConfig()
    if (!config.clientId || !config.clientSecret) throw new Error('Google OAuth 설정이 없습니다.')
    const category = await supabaseAdmin.from('categories').select('id,upload_channel_handle').eq('id', categoryId).single()
    if (category.error) throw category.error
    const handle = String(category.data.upload_channel_handle || '').trim()
    if (!handle.startsWith('@')) throw new Error('카테고리의 YouTube 채널 핸들을 먼저 저장해 주세요.')
    const nonce = randomBytes(32).toString('hex'), issuedAt = Date.now()
    const context = { categoryId, localChannelId, handle, origin, issuedAt }
    const stored = await supabaseAdmin.from('global_settings').insert({ key: PREFIX + nonce, value: JSON.stringify(context) })
    if (stored.error) throw stored.error
    const payload = `yt_${nonce}.${issuedAt}`
    const state = `${payload}.${createHmac('sha256', config.clientSecret).update(payload).digest('hex')}`
    const url = new URL('https://accounts.google.com/o/oauth2/v2/auth')
    url.search = new URLSearchParams({ client_id: config.clientId, redirect_uri: origin + CALLBACK,
        response_type: 'code', scope: SCOPE, access_type: 'offline', prompt: 'consent', state }).toString()
    return url.toString()
}

export async function completeYoutubeChannelOAuth(req: Request, config: GoogleDriveConfig) {
    const url = new URL(req.url), state = url.searchParams.get('state') || ''
    const destination = new URL('/dashboard', url.origin)
    const redirect = (result: string) => { destination.searchParams.set('youtube_oauth', result); return NextResponse.redirect(destination) }
    const match = state.match(/^yt_([a-f0-9]{64})\.(\d{13})\.([a-f0-9]{64})$/)
    if (!match || Date.now() - Number(match[2]) > 10 * 60_000 || Number(match[2]) > Date.now()) return redirect('state_mismatch')
    const expected = createHmac('sha256', config.clientSecret).update(`yt_${match[1]}.${match[2]}`).digest()
    if (!timingSafeEqual(expected, Buffer.from(match[3], 'hex'))) return redirect('state_mismatch')
    // Consume the server-created state exactly once, before exchanging a code.
    const claimed = await supabaseAdmin.from('global_settings').delete().eq('key', PREFIX + match[1]).select('value').maybeSingle()
    if (claimed.error || !claimed.data) return redirect('state_mismatch')
    try {
        const context = JSON.parse(claimed.data.value)
        if (context.origin !== url.origin || context.issuedAt !== Number(match[2])) return redirect('state_mismatch')
        if (url.searchParams.get('error')) return redirect('approval_cancelled')
        const code = url.searchParams.get('code')
        if (!code) return redirect('missing_code')
        const tokenResponse = await fetch('https://oauth2.googleapis.com/token', { method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, cache: 'no-store',
            body: new URLSearchParams({ code, client_id: config.clientId, client_secret: config.clientSecret,
                redirect_uri: url.origin + CALLBACK, grant_type: 'authorization_code' }) })
        const token = await tokenResponse.json()
        if (!tokenResponse.ok || !token.refresh_token || !token.access_token) return redirect('token_exchange_failed')
        const scopes = String(token.scope || '').split(/\s+/)
        if (!scopes.includes('https://www.googleapis.com/auth/youtube.upload')
            || !scopes.includes('https://www.googleapis.com/auth/youtube.readonly')) return redirect('scope_missing')
        const response = await fetch('https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true', {
            headers: { Authorization: `Bearer ${token.access_token}` }, cache: 'no-store' })
        const channels = await response.json()
        if (!response.ok) return redirect('channel_lookup_failed')
        const channel = channels.items?.find((c: any) => String(c.snippet?.customUrl || '').toLowerCase() === context.handle.toLowerCase())
        if (!channel) return redirect('wrong_channel')
        const saved = await supabaseAdmin.from('global_settings').upsert({ key: CHANNEL_PREFIX + context.localChannelId,
            value: JSON.stringify({ id: context.localChannelId, name: channel.snippet.title, handle: context.handle,
                youtube_channel_id: channel.id, connected_at: new Date().toISOString(),
                credentials: protectYoutubeCredentials({ client_id: config.clientId, client_secret: config.clientSecret,
                    refresh_token: token.refresh_token, scopes }, config.clientSecret) }) }, { onConflict: 'key' })
        if (saved.error) throw saved.error
        const bound = await supabaseAdmin.from('categories').update({ upload_channel_id: context.localChannelId,
            upload_channel_name: channel.snippet.title, upload_channel_handle: context.handle })
            .eq('id', context.categoryId).eq('upload_channel_handle', context.handle).select('id').single()
        if (bound.error) throw bound.error
        return redirect('connected')
    } catch { return redirect('connection_failed') }
}

export async function youtubeConnectedChannels() {
    const rows = await supabaseAdmin.from('global_settings').select('value').like('key', CHANNEL_PREFIX + '%')
    if (rows.error) throw rows.error
    return (rows.data || []).flatMap(row => { try {
        const value = JSON.parse(row.value)
        return [{ id: value.id, name: value.name, handle: value.handle, connected_at: value.connected_at,
            youtube_channel_id: value.youtube_channel_id }]
    } catch { return [] } })
}
