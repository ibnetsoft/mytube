import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';

const supabaseAdmin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
);

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

        console.log('Update success:', updateData.user.id);
        return NextResponse.json({ success: true, user: updateData.user });
    } catch (e: any) {
        console.error('Unexpected API Error:', e);
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}
