'use client'
import { Fragment, useState } from 'react'
import SubtitleSfxPicker from '@/components/SubtitleSfxPicker'
import { subtitleWords, sfxSubtitleIndex, wordBoundaryTime } from '@/lib/stdSfxCues'

export default function SubtitleSfxEditor({ subtitle, subtitleIndex, subtitles, assets, cues, selectedAssetId,
    onSelect, onSave, onEdit, activeTokenIndex, onError, projectId, headers, onPreviewOpen }: {
    projectId: string; headers: Record<string, string>; onPreviewOpen: () => void;
    subtitle: any; subtitleIndex: number; subtitles: any[]; assets: any[]; cues: any[]; selectedAssetId: string;
    onSelect: (id: string) => void; onSave: (cues: any[]) => Promise<void>; onEdit: () => void;
    activeTokenIndex: number; onError: (message: string) => void;
}) {
    const [saving, setSaving] = useState(false)
    const words = subtitleWords(subtitle.text)
    const current = cues.filter(cue => sfxSubtitleIndex(cue, subtitles) === subtitleIndex)
    const save = async (next: any[]) => {
        setSaving(true)
        try { await onSave(next) } catch (e: any) { onError(e.message || '효과음 위치 저장에 실패했습니다.') }
        finally { setSaving(false) }
    }
    const insert = (boundary: number) => {
        const asset = assets.find(a => a.id === selectedAssetId)
        if (!asset) return
        void save([...cues, {
            id: crypto.randomUUID(), asset_id: asset.id, file_name: asset.file_name,
            subtitle_id: subtitle.id ?? null, subtitle_index: subtitleIndex,
            subtitle_text: subtitle.text, scene_number: subtitle.scene_number,
            word_boundary: boundary, start: wordBoundaryTime(subtitle, boundary),
            volume_db: -18, enabled: true,
        }])
    }
    return <div className="min-w-0 flex-1 space-y-2">
        <SubtitleSfxPicker assets={assets} value={selectedAssetId} projectId={projectId} headers={headers}
            disabled={saving} onChange={onSelect} onOpen={onPreviewOpen} />
        <div className="flex flex-wrap items-center gap-1" aria-label="단어 사이 효과음 삽입">
            {Array.from({ length: words.length + 1 }, (_, boundary) => <Fragment key={boundary}>
                {current.filter(c => Number(c.word_boundary ?? 0) === boundary).map(c => <button key={c.id}
                    type="button" disabled={saving} onClick={() => void save(cues.filter(item => item.id !== c.id))}
                    title={`${c.file_name} · 클릭하여 삽입 삭제`} aria-label={`${c.file_name} 효과음 삭제`}
                    className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-purple-400/60 bg-purple-500/15 text-sm text-purple-200 hover:bg-purple-500/30">
                    <span aria-hidden="true">★</span>
                </button>)}
                {selectedAssetId && <button type="button" disabled={saving} onClick={() => insert(boundary)}
                    aria-label={`${boundary}번째 단어 뒤 효과음 삽입`} title={`${wordBoundaryTime(subtitle, boundary).toFixed(2)}초에 효과음 삽입`}
                    className="rounded px-1 text-purple-300 hover:bg-purple-500/25 disabled:opacity-40">+</button>}
                {boundary < words.length && <button type="button" onClick={onEdit}
                    className={`h-6 rounded border px-2 text-[11px] ${boundary === activeTokenIndex ? 'border-cyan-400/60 bg-cyan-500/15 text-cyan-100' : 'border-white/10 bg-[#10151d] text-gray-200'}`}>
                    {words[boundary]}
                </button>}
            </Fragment>)}
        </div>
        {saving && <p role="status" className="text-[10px] text-purple-200">효과음 위치 저장 중…</p>}
        {selectedAssetId && <p className="text-[10px] text-gray-400">+ 삽입 · 효과음 클릭으로 삭제 · 위치 자동 저장</p>}
    </div>
}
