'use client'
import { Fragment, useState, useEffect } from 'react'
import SubtitleSfxPicker from '@/components/SubtitleSfxPicker'
import { subtitleWords, sfxSubtitleIndex, wordBoundaryTime, resolveSfxCues, sfxNeedsReview } from '@/lib/stdSfxCues'

export default function SubtitleSfxEditor({ subtitle, subtitleIndex, subtitles, assets, cues, selectedAssetId,
    onSelect, onSave, onEdit, activeTokenIndex, onError, projectId, headers, onPreviewOpen }: {
    projectId: string; headers: Record<string, string>; onPreviewOpen: () => void;
    subtitle: any; subtitleIndex: number; subtitles: any[]; assets: any[]; cues: any[]; selectedAssetId: string;
    onSelect: (id: string) => void; onSave: (cues: any[]) => Promise<void>; onEdit: () => void;
    activeTokenIndex: number; onError: (message: string) => void;
}) {
    const [saving, setSaving] = useState(false)
    const [editing, setEditing] = useState<any>(null)
    const [sample, setSample] = useState('')
    useEffect(() => () => { if (sample) URL.revokeObjectURL(sample) }, [sample])
    useEffect(() => { setEditing(null); setSample('') }, [subtitleIndex])
    const words = subtitleWords(subtitle.text)
    const current = cues.filter(cue => cue.enabled !== false && sfxSubtitleIndex(cue, subtitles) === subtitleIndex)
        .map(c => resolveSfxCues([c], subtitles)[0] || c)
    const review = cues.filter(c => sfxNeedsReview(c, subtitles))
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
            volume_db: -18, enabled: true, source: 'manual', user_override: true,
        }])
    }
    return <div className="min-w-0 flex-1 space-y-2">
        <SubtitleSfxPicker assets={assets} value={selectedAssetId} projectId={projectId} headers={headers}
            disabled={saving} onChange={onSelect} onOpen={onPreviewOpen} />
        <div className="flex flex-wrap items-center gap-1" aria-label="단어 사이 효과음 삽입">
            {Array.from({ length: words.length + 1 }, (_, boundary) => <Fragment key={boundary}>
                {current.filter(c => Number(c.word_boundary ?? 0) === boundary).map(c => <button key={c.id}
                    type="button" disabled={saving} onClick={() => setEditing({ ...c })}
                    title={`${c.file_name} · 클릭하여 효과음 편집`} aria-label={`${c.file_name} 효과음 편집`}
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
        {editing && <div className="space-y-2 rounded border border-purple-400/30 p-2 text-xs text-gray-200">
            <p>{editing.file_name}</p>
            {editing.reason && <p className="text-purple-200">AI 배치 이유: {editing.reason}</p>}
            <p className="text-gray-400">{editing.timing_mode === 'subtitle_start' ? '단어 타이밍 없음 · 자막 시작 기준' : '단어 위치 기준'}</p>
            <label className="block">위치 <select value={editing.word_boundary} onChange={e => setEditing({...editing, word_boundary:Number(e.target.value)})} className="bg-[#10151d]">
                {Array.from({length:words.length+1},(_,i)=><option key={i} value={i}>{i === 0 ? '자막 시작' : `${words[i-1]} 뒤`}</option>)}
            </select></label>
            <label className="block">볼륨(dB) <input type="number" min="-60" max="0" value={editing.volume_db} onChange={e=>setEditing({...editing, volume_db:Number(e.target.value)})} className="w-16 bg-[#10151d]" /></label>
            <label className="block">길이(초) <input type="number" min="0.2" max="30" step="0.1" value={editing.duration || 2} onChange={e=>setEditing({...editing, duration:Number(e.target.value)})} className="w-16 bg-[#10151d]" /></label>
            <button type="button" disabled={saving} onClick={async () => {
                try {
                    const res = await fetch(`/api/std/projects/${projectId}/assets/file?assetId=${encodeURIComponent(editing.asset_id)}`, {headers})
                    if (!res.ok) throw new Error('효과음을 불러오지 못했습니다.')
                    setSample(URL.createObjectURL(await res.blob()))
                } catch(e:any) { onError(e.message) }
            }} className="mr-2 rounded border px-2 py-1">미리듣기</button>
            {sample && <audio src={sample} controls autoPlay className="w-full" />}
            {selectedAssetId && selectedAssetId !== editing.asset_id && <button type="button" onClick={()=>{
                const replacement = assets.find(a=>a.id===selectedAssetId)
                if(replacement) setEditing({...editing,asset_id:replacement.id,file_name:replacement.file_name})
            }} className="block text-purple-200">선택한 파일로 교체</button>}
            <button type="button" disabled={saving} onClick={() => {
                const next = {...editing, source:'manual', user_override:true, anchor_scope:'subtitle', subtitle_id:subtitle.id ?? null,
                    subtitle_text:subtitle.text, subtitle_index:subtitleIndex, scene_number:subtitle.scene_number,
                    volume_db:Math.max(-60,Math.min(0,editing.volume_db)), duration:Math.max(.2,Math.min(30,editing.duration || 2))}
                void save(cues.map(c=>c.id === editing.id ? next : c)); setEditing(null); setSample('')
            }} className="mr-2 rounded bg-purple-700 px-2 py-1">변경 저장</button>
            <button type="button" disabled={saving} onClick={() => {
                void save(cues.map(c=>c.id === editing.id ? {...c,enabled:false,source:'manual',user_override:true} : c)); setEditing(null); setSample('')
            }} className="text-red-300">효과음 제거</button>
        </div>}
        {review.length > 0 && <div className="rounded border border-amber-500/30 p-2 text-xs text-amber-200">
            위치 확인 필요 {review.length}개 · 합치기/분리기 또는 문장 수정으로 기준 위치가 바뀌었습니다. 해당 자막에 다시 배치해 주세요.
            {review.map(c=><p key={c.id}>{c.file_name} <button type="button" onClick={()=>void save(cues.map(x=>x.id===c.id?{...x,enabled:false,source:'manual',user_override:true}:x))}>제거</button></p>)}
        </div>}
        {saving && <p role="status" className="text-[10px] text-purple-200">효과음 위치 저장 중…</p>}
        {(selectedAssetId || current.length > 0) && <p className="text-[10px] text-gray-400">+ 삽입 · 단어 사이의 ★ 클릭으로 편집·삭제 · 자동 저장</p>}
    </div>
}
