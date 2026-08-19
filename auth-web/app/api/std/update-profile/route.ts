import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

export const STD_OFFICIAL_CATEGORIES = [
    { id: 2, name: '옛날이야기' },
    { id: 3, name: '경제' },
    { id: 4, name: '탈북사연' },
    { id: 5, name: '한국사연' },
    { id: 6, name: '해외감동' },
    { id: 7, name: '무협' },
    { id: 8, name: '노후금융' },
    { id: 9, name: '황혼19금' },
]

export async function POST(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { user, profile, email } = auth.requester
    try {
        const body = await req.json()
        const fullName = String(body.full_name ?? profile.full_name ?? '').trim()
        const nationality = String(body.nationality ?? profile.nationality ?? '').trim()
        const contact = String(body.contact ?? profile.contact ?? '').trim()
        
        let preferredCategoryIds: (number | string)[] = []
        let preferredCategoryNames: string[] = []

        if (Array.isArray(body.preferred_category_ids)) {
            preferredCategoryIds = body.preferred_category_ids
        } else if (Array.isArray(body.preferred_categories)) {
            preferredCategoryIds = body.preferred_categories
        }

        if (Array.isArray(body.preferred_category_names)) {
            preferredCategoryNames = body.preferred_category_names
        } else if (preferredCategoryIds.length > 0) {
            preferredCategoryNames = STD_OFFICIAL_CATEGORIES
                .filter(c => preferredCategoryIds.includes(c.id) || preferredCategoryIds.includes(String(c.id)))
                .map(c => c.name)
        }

        // If names are provided but IDs not mapped, map them
        if (preferredCategoryNames.length > 0 && preferredCategoryIds.length === 0) {
            preferredCategoryIds = STD_OFFICIAL_CATEGORIES
                .filter(c => preferredCategoryNames.includes(c.name))
                .map(c => c.id)
        }

        // Update profiles table
        const { error: profileError } = await supabaseAdmin
            .from('profiles')
            .update({
                full_name: fullName,
                nationality: nationality,
                contact: contact,
                preferred_category_ids: preferredCategoryIds,
                preferred_category_names: preferredCategoryNames,
            })
            .eq('id', user.id)

        if (profileError) {
            // fallback by email if id differed
            await supabaseAdmin
                .from('profiles')
                .update({
                    full_name: fullName,
                    nationality: nationality,
                    contact: contact,
                    preferred_category_ids: preferredCategoryIds,
                    preferred_category_names: preferredCategoryNames,
                })
                .eq('email', email)
        }

        // Update auth.users metadata
        try {
            await supabaseAdmin.auth.admin.updateUserById(user.id, {
                user_metadata: {
                    ...(user.user_metadata || {}),
                    full_name: fullName,
                    nationality: nationality,
                    contact: contact,
                    preferred_category_ids: preferredCategoryIds,
                    preferred_category_names: preferredCategoryNames,
                }
            })
        } catch (metaErr: any) {
            console.warn('[update-profile] user_metadata update warning:', metaErr?.message)
        }

        return NextResponse.json({
            success: true,
            user: {
                id: user.id,
                email,
                full_name: fullName,
                nationality: nationality,
                contact: contact,
                preferred_category_ids: preferredCategoryIds,
                preferred_category_names: preferredCategoryNames,
            }
        })
    } catch (err: any) {
        console.error('[update-profile] Error:', err?.message)
        return NextResponse.json({ success: false, error: err?.message || '저장 실패' }, { status: 500 })
    }
}
