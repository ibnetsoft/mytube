import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';

const supabaseAdmin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
);

const CONTENT_LANGUAGES = ['ko', 'en', 'ja'] as const;

function normalizePreferredLanguages(value: any): string[] {
    const raw = Array.isArray(value) ? value : [];
    const normalized = raw
        .map((item) => String(item || '').trim().toLowerCase())
        .filter((item) => CONTENT_LANGUAGES.includes(item as any));
    return normalized.length ? Array.from(new Set(normalized)) : ['ko'];
}

function isMissingColumnError(err: any): boolean {
    if (!err) return false;
    const code = String(err.code || '');
    if (code === 'PGRST204' || code === '42703') return true;
    const msg = String(err.message || '').toLowerCase();
    return msg.includes('schema cache') || /could not find the .* column/.test(msg) || /column .* does not exist/.test(msg);
}

export async function POST(req: Request) {
    try {
        const { userId, metadata } = await req.json();

        if (!userId || !metadata) {
            return NextResponse.json({ error: 'Invalid parameters' }, { status: 400 });
        }

        console.log(`Attempting to update metadata for user: ${userId}`);
        
        // 1. Fetch current user metadata first to perform a safe merge
        const { data: { user }, error: fetchError } = await supabaseAdmin.auth.admin.getUserById(userId);
        
        if (fetchError || !user) {
            console.error('Fetch User Error:', fetchError);
            return NextResponse.json({ error: 'User not found' }, { status: 404 });
        }

        const currentUserMetadata = user.user_metadata || {};
        const updatedMetadata = {
            ...currentUserMetadata,
            ...metadata
        };

        console.log('Merging metadata:', { old: currentUserMetadata, new: metadata, result: updatedMetadata });

        // 2. Perform the update with merged metadata
        const { data: updateData, error: updateError } = await supabaseAdmin.auth.admin.updateUserById(userId, {
            user_metadata: updatedMetadata
        });

        if (updateError) {
            console.error('Supabase Update Error:', updateError);
            return NextResponse.json({ error: updateError.message }, { status: 500 });
        }

        // 3. Update profiles table in Supabase to sync persona/language fields
        const profileUpdate: any = {
            persona_name: metadata.persona_name || null,
            persona_style: metadata.persona_style || null,
            persona_description: metadata.persona_description || null,
            preferred_languages: normalizePreferredLanguages(metadata.preferred_languages),
        };
        let { error: profileError } = await supabaseAdmin
            .from('profiles')
            .update(profileUpdate)
            .eq('id', userId);

        if (isMissingColumnError(profileError)) {
            const { preferred_languages: _preferredLanguages, ...fallbackProfileUpdate } = profileUpdate;
            const retry = await supabaseAdmin
                .from('profiles')
                .update(fallbackProfileUpdate)
                .eq('id', userId);
            profileError = retry.error;
        }

        if (profileError) {
            console.error('profiles sync error:', profileError);
        }

        console.log('Update success:', updateData.user.id);
        return NextResponse.json({ success: true, user: updateData.user });
    } catch (e: any) {
        console.error('Unexpected API Error:', e);
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}
