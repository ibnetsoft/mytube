import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'
import {
    deleteSelectedTopics, listTopicsForDeletion, TopicDeletionInputError,
    topicDeletionIds, topicDeletionLanguage,
} from '@/lib/adminTopicDeletion'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } },
)

const responseError = (error: unknown) => {
    if (error instanceof TopicDeletionInputError) {
        return NextResponse.json({ success: false, error: error.message }, { status: 400 })
    }
    console.error('Admin topic deletion failed:', error)
    return NextResponse.json({ success: false, error: '주제 목록 또는 삭제 상태를 확인하지 못했습니다. 다시 시도해 주세요.' }, { status: 500 })
}

export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester
        const params = new URL(req.url).searchParams
        const language = topicDeletionLanguage(params.get('language') || 'ko')
        const page = Number(params.get('page') || 1)
        const perPage = Number(params.get('perPage') || 500)
        if (!Number.isSafeInteger(page) || page < 1 || page > 100000
            || !Number.isSafeInteger(perPage) || perPage < 1 || perPage > 500) {
            throw new TopicDeletionInputError('목록 페이지 값이 올바르지 않습니다.')
        }
        return NextResponse.json(await listTopicsForDeletion(getAdmin(), language, page, perPage), {
            headers: { 'Cache-Control': 'private, no-store' },
        })
    } catch (error) { return responseError(error) }
}

export async function DELETE(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester
        const text = await req.text()
        if (text.length > 20000) throw new TopicDeletionInputError('삭제 요청이 너무 큽니다.')
        let body: any
        try { body = JSON.parse(text) } catch { throw new TopicDeletionInputError('삭제 요청 형식이 올바르지 않습니다.') }
        const ids = topicDeletionIds(body?.ids)
        const language = topicDeletionLanguage(body?.language)
        return NextResponse.json(await deleteSelectedTopics(getAdmin(), ids, language))
    } catch (error) { return responseError(error) }
}
