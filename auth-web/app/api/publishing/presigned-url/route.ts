
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey)

    try {
        const { userId, fileName, fileType } = await req.json()

        if (!userId || !fileName) {
            return NextResponse.json({ error: 'Missing userId or fileName' }, { status: 400 })
        }

        // 1. Path: publishing/{userId}/{timestamp}_{fileName}
        const timestamp = Date.now()
        const filePath = `${userId}/${timestamp}_${fileName}`

        // 2. Create Signed URL for Upload (valid for 15 mins)
        // Note: For 'upload', we use storage.from().createSignedUploadUrl()
        const { data, error } = await supabaseAdmin
            .storage
            .from('videos') // Make sure 'videos' bucket exists
            .createSignedUploadUrl(filePath)

        if (error) throw error

        return NextResponse.json({
            success: true,
            uploadUrl: data.signedUrl,
            path: filePath,
            token: data.token // Required for some SDK versions, but signedUrl usually sufficient
        })
    } catch (error: any) {
        console.error('Signed URL Error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
