import { supabaseAdmin } from '@/lib/supabaseAdmin'

export type GoogleDriveConfig = {
    clientId: string
    clientSecret: string
    refreshToken: string
    rootFolderId: string
    source: 'admin' | 'environment'
}

const ADMIN_KEYS = [
    'sys_api_google_drive_client_id',
    'sys_api_google_drive_client_secret',
    'sys_api_google_drive_refresh_token',
    'sys_api_google_drive_root_folder_id',
    'sys_api_remote_render_drive_folder_id',
    'remote_render_drive_folder_id',
]

function clean(value: unknown): string {
    return String(value ?? '').trim()
}

export async function getGoogleDriveConfig(): Promise<GoogleDriveConfig> {
    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', ADMIN_KEYS)

    if (error) throw new Error(`drive_config_load_failed: ${error.message}`)

    const settings = Object.fromEntries((data || []).map(row => [row.key, clean(row.value)]))
    const adminClientId = clean(settings.sys_api_google_drive_client_id)
    const adminClientSecret = clean(settings.sys_api_google_drive_client_secret)
    const adminRefreshToken = clean(settings.sys_api_google_drive_refresh_token)
    const hasAnyAdminCredential = Boolean(adminClientId || adminClientSecret || adminRefreshToken)

    if (hasAnyAdminCredential && !(adminClientId && adminClientSecret && adminRefreshToken)) {
        throw new Error('drive_admin_credentials_incomplete')
    }

    const rootFolderId = clean(
        settings.sys_api_google_drive_root_folder_id
        || settings.sys_api_remote_render_drive_folder_id
        || settings.remote_render_drive_folder_id
        || process.env.GOOGLE_DRIVE_ROOT_FOLDER_ID
        || process.env.REMOTE_RENDER_DRIVE_FOLDER_ID
    )

    if (hasAnyAdminCredential) {
        return {
            clientId: adminClientId,
            clientSecret: adminClientSecret,
            refreshToken: adminRefreshToken,
            rootFolderId,
            source: 'admin',
        }
    }

    return {
        clientId: clean(process.env.GOOGLE_DRIVE_CLIENT_ID),
        clientSecret: clean(process.env.GOOGLE_DRIVE_CLIENT_SECRET),
        refreshToken: clean(process.env.GOOGLE_DRIVE_REFRESH_TOKEN),
        rootFolderId,
        source: 'environment',
    }
}

export async function getGoogleDriveAccessToken(): Promise<{ accessToken: string; expiresIn: number; config: GoogleDriveConfig }> {
    const config = await getGoogleDriveConfig()
    if (!config.clientId || !config.clientSecret || !config.refreshToken) {
        throw new Error('drive_credentials_not_configured')
    }

    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            client_id: config.clientId,
            client_secret: config.clientSecret,
            refresh_token: config.refreshToken,
            grant_type: 'refresh_token',
        }),
        cache: 'no-store',
    })
    const tokenBody = await tokenRes.json().catch(() => ({}))
    if (!tokenRes.ok || !tokenBody.access_token) {
        throw new Error(`drive_token_refresh_failed: ${tokenBody?.error || tokenRes.status}`)
    }

    return {
        accessToken: String(tokenBody.access_token),
        expiresIn: Number(tokenBody.expires_in || 3600),
        config,
    }
}
