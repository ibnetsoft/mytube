
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''

if (!supabaseUrl || !supabaseAnonKey) {
    console.error('❌ Supabase environment variables are missing! Check your Vercel settings.')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
