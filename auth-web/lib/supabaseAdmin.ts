
import { createClient } from '@supabase/supabase-js'

// [AIR-0227D-VALIDATION Stage 2 - security hotfix] This module used to fall
// back to NEXT_PUBLIC_SUPABASE_ANON_KEY whenever SUPABASE_SERVICE_ROLE_KEY
// was unset - meaning every admin/internal route built on `supabaseAdmin`
// would silently start running under RLS as an anonymous caller instead of
// failing loudly. For a privileged client that's the wrong direction to
// fail in: a misconfigured deployment should refuse to serve admin/internal
// traffic, not quietly downgrade its own privileges. requireEnv() throws
// immediately (module-evaluation time - for a Next.js route handler bundle
// that means "on that route's first invocation/cold start", not at
// `next build`) rather than deferring the failure into whatever RLS-denied
// error a caller would eventually see. Mirrors the existing fail-fast
// pattern in lib/desktopSession.ts::getSecret() for DESKTOP_SESSION_SECRET.
// Never logs the key value itself, only the env var name that's missing.
function requireEnv(name: string): string {
    const value = process.env[name]
    if (!value) {
        throw new Error(`${name} is not configured - refusing to start a privileged Supabase client (no anon-key fallback)`)
    }
    return value
}

export const supabaseAdmin = createClient(requireEnv('NEXT_PUBLIC_SUPABASE_URL'), requireEnv('SUPABASE_SERVICE_ROLE_KEY'), {
    auth: {
        autoRefreshToken: false,
        persistSession: false
    }
})
