'use client'

import { persistentThumbnailUrl } from '@/lib/stdThumbnailUrl'
import type { SupportedLocale } from '@/lib/i18n'
import { stdUiText } from '@/lib/stdUiText'
import { charactersFromPayload } from '@/lib/stdCharacterProtection'

export default function StdCharacterReferences({ payload, impersonateEmail, locale = 'ko' }: { payload: any; impersonateEmail?: string | null; locale?: SupportedLocale }) {
    const ui = (text: string, values?: Record<string, string | number>) => stdUiText(locale, text, values)
    const characters = charactersFromPayload(payload)
    return (
        <section className="bg-[#1c222c] border border-white/10 rounded-xl p-4">
            <h3 className="font-bold text-white">{ui('캐릭터 기준 이미지')}</h3>
            <p className="text-xs text-gray-400 mt-1">{ui('주요 캐릭터와 2개 이상 씬에 등장하는 인물의 얼굴·머리·변발·상투·의상을 저장해 같은 디자인을 유지하는 기준입니다. 설명문만 있으면 기준 이미지 생성 대기 상태입니다.')}</p>
            {!characters.length && <p className="text-sm text-amber-300 mt-3">{ui('캐릭터 기준 이미지 생성 대기')}</p>}
            <div role="list" aria-label={ui('캐릭터 기준 이미지')} className="mt-3 flex gap-2 overflow-x-auto pb-1">
                {characters.map((character: any, index: number) => {
                    const sheet = (character.character_sheet_assets || []).find((asset: any) => asset.type === 'model_sheet' && asset.status === 'ready')
                    let url = persistentThumbnailUrl(sheet?.image_url, character.image_url)
                    if (url && impersonateEmail && /^\/api\/std\/projects\/[^/?#]+\/character-thumbnail(?:\?|$)/.test(url)) {
                        const thumbnail = new URL(url, 'http://localhost')
                        thumbnail.searchParams.set('impersonate', impersonateEmail)
                        url = `${thumbnail.pathname}${thumbnail.search}`
                    }
                    const sceneCount = Array.isArray(character.scene_numbers)
                        ? new Set(character.scene_numbers.map(Number).filter((number: number) => Number.isSafeInteger(number) && number > 0)).size
                        : 0
                    return <div role="listitem" key={character.character_key || `${character.name}-${index}`} className="flex w-52 shrink-0 min-w-0 items-center gap-2 rounded-lg bg-black/20 p-2">
                        {url ? <div className={`${sheet ? 'h-16 w-24' : 'h-14 w-14'} shrink-0 overflow-hidden rounded`}>
                            {/* Show only the low-resolution authenticated display proxy. */}
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={url}
                                alt={`${character.name || ui('캐릭터')} ${ui('기준 이미지')}`}
                                width={sheet ? 96 : 56}
                                height={sheet ? 64 : 56}
                                className={sheet ? 'h-16 w-24 object-contain' : 'h-14 w-14 object-cover'}
                                draggable={false}
                            />
                        </div> : <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded bg-black/20 text-center text-[9px] text-amber-300">{ui('기준 이미지')}<br />{ui('생성 대기')}</div>}
                        <div className="min-w-0">
                            <p className="truncate text-xs font-bold text-white">{character.name || ui('캐릭터')}</p>
                            <p className="line-clamp-2 text-[10px] leading-tight text-gray-400">{character.role || ''}</p>
                            {sceneCount > 0 && <p className="text-[10px] text-sky-300">{ui('{count}개 씬 등장', { count: sceneCount })}</p>}
                            {sheet && <p className="text-[9px] text-gray-400">{ui(sheet.profile === 'turnaround' ? '다방향 시트' : '상세 캐릭터 시트')}</p>}
                        </div>
                    </div>
                })}
            </div>
        </section>
    )
}
