import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
)

export async function POST(req: Request) {
  try {
    const { userId, apiKeys } = await req.json()
    if (!userId || !apiKeys) return NextResponse.json({ error: 'Missing data' }, { status: 400 })

    const { data, error } = await supabaseAdmin.auth.admin.updateUserById(userId, {
      app_metadata: { 
        custom_api_keys: apiKeys 
      }
    })

    if (error) throw error

    return NextResponse.json({ success: true, user: data.user })
  } catch (e: any) {
    console.error('API Key Update Error:', e)
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
