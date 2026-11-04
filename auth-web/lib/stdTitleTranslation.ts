import type { SupabaseClient } from '@supabase/supabase-js'
import { generateJsonWithModelSetting } from './aiRouter'

// Keep the administrator's configured model first. The general router's older
// Gemini fallback is not available to every account, so title translation gets
// its own currently available fallback when that route also fails.
export async function generateStdTitleTranslation(db: SupabaseClient, prompt: string, geminiKey: string): Promise<string> {
    try {
        return await generateJsonWithModelSetting(db, prompt, 'sys_api_translation_model', geminiKey, 0.2)
    } catch {
        return generateJsonWithModelSetting(db, prompt, 'sys_api_title_translation_fallback_model', geminiKey, 0.2,
            { defaultModel: 'gemini-3-flash-preview', disableFallback: true })
    }
}
