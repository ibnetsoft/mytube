'use client'

import { persistentThumbnailUrl } from '@/lib/stdThumbnailUrl'
import { charactersFromPayload } from '@/lib/stdCharacterProtection'

export default function StdCharacterReferences({ payload }: { payload: any }) {
    const characters = charactersFromPayload(payload)
    return (
        <section className="bg-[#1c222c] border border-white/10 rounded-xl p-4">
            <h3 className="font-bold text-white">캐릭터 기준 이미지</h3>
            <p className="text-xs text-gray-400 mt-1">주요 캐릭터와 2개 이상 씬에 등장하는 인물의 얼굴·머리·변발·상투·의상을 저장해 같은 디자인을 유지하는 기준입니다. 설명문만 있으면 기준 이미지 생성 대기 상태입니다.</p>
            {!characters.length && <p className="text-sm text-amber-300 mt-3">캐릭터 기준 이미지 생성 대기</p>}
            <div className="grid grid-cols-2 gap-2 mt-3 sm:grid-cols-3 lg:grid-cols-5">
                {characters.map((character: any, index: number) => {
                    const url = persistentThumbnailUrl(character.image_url)
                    const sceneCount = Array.isArray(character.scene_numbers)
                        ? new Set(character.scene_numbers.map(Number).filter((number: number) => Number.isSafeInteger(number) && number > 0)).size
                        : 0
                    return <div key={character.character_key || `${character.name}-${index}`} className="flex min-w-0 items-center gap-2 rounded-lg bg-black/20 p-2">
                        {url ? <div className="h-14 w-14 shrink-0 overflow-hidden rounded">
                            {/* The authenticated proxy already returns a fixed 64px asset. */}
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={url}
                                alt={`${character.name || '캐릭터'} 기준 이미지`}
                                width={56}
                                height={56}
                                className="h-14 w-14 object-cover"
                                draggable={false}
                            />
                        </div> : <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded bg-black/20 text-center text-[9px] text-amber-300">기준 이미지<br />생성 대기</div>}
                        <div className="min-w-0">
                            <p className="truncate text-xs font-bold text-white">{character.name || '캐릭터'}</p>
                            <p className="line-clamp-2 text-[10px] leading-tight text-gray-400">{character.role || ''}</p>
                            {sceneCount > 0 && <p className="text-[10px] text-sky-300">{sceneCount}개 씬 등장</p>}
                        </div>
                    </div>
                })}
            </div>
        </section>
    )
}
