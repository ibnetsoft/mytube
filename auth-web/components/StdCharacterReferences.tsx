'use client'

import { persistentThumbnailUrl } from '@/lib/stdThumbnailUrl'

export default function StdCharacterReferences({ payload }: { payload: any }) {
    const anchors = payload?.structure?.character_anchors || payload?.character_anchors || {}
    const main = anchors.main_character || payload?.main_character || payload?.structure?.main_character
    const supporting = anchors.supporting_characters || payload?.supporting_characters || payload?.structure?.supporting_characters || []
    const characters = [main, ...(Array.isArray(supporting) ? supporting : [])].filter(Boolean)
    return (
        <section className="bg-[#1c222c] border border-white/10 rounded-xl p-5">
            <h3 className="font-bold text-white">주요 캐릭터 기준 이미지</h3>
            <p className="text-xs text-gray-400 mt-1">장면 이미지의 얼굴·의상 일관성을 위한 기준입니다. 설명문만 있는 경우 생성 완료가 아닙니다.</p>
            {!characters.length && <p className="text-sm text-amber-300 mt-3">캐릭터 기준 이미지 생성 대기</p>}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
                {characters.map((character: any, index: number) => {
                    const url = persistentThumbnailUrl(character.image_url)
                    return <div key={character.character_key || `${character.name}-${index}`} className="rounded-lg bg-black/20 p-3">
                        {url ? <a href={url} target="_blank" rel="noopener noreferrer">
                            <img src={url} alt={`${character.name || '캐릭터'} 기준 이미지`} className="w-full max-h-64 object-contain rounded" />
                        </a> : <div className="h-32 flex items-center justify-center text-amber-300 text-sm">기준 이미지 미생성</div>}
                        <p className="text-sm font-bold text-white mt-2">{character.name || '캐릭터'}</p>
                        <p className="text-xs text-gray-400">{character.role || ''}</p>
                    </div>
                })}
            </div>
        </section>
    )
}
