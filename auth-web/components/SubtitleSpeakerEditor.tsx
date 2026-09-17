 'use client'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import type { SpeakerInfo } from '@/lib/stdSpeakerAssignment'
export default function SubtitleSpeakerEditor({ speaker, names, thai, onSave, onClose }: { speaker: SpeakerInfo | null; names: string[]; thai: boolean; onSave: (name: string, gender: string) => Promise<void>; onClose: () => void }) {
    const [name, setName] = useState(speaker?.name || '')
    const [gender, setGender] = useState(speaker?.gender || '')
    const [saving, setSaving] = useState(false), [error, setError] = useState('')
    return createPortal(<div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4" onClick={e => e.stopPropagation()}>
        <div role="dialog" aria-modal="true" aria-label="화자 확인" className="w-full max-w-md space-y-4 rounded-xl border border-white/20 bg-[#1c2027] p-5 text-gray-100">
            <h2 className="font-bold">{thai ? 'ยืนยันผู้พูด' : '화자 확인'}</h2>
            <p className="text-xs text-gray-400">{thai ? 'ข้อมูลสำหรับผู้ตัดต่อเท่านั้น ไม่อ่านออกเสียงและไม่แสดงในคำบรรยายวิดีโอ' : '편집용 정보입니다. TTS와 영상 자막에는 포함되지 않습니다.'}</p>
            <label className="block text-sm">{thai ? 'ชื่อผู้พูด (ใช้ชื่อเดียวกันทุกประโยค)' : '화자 이름 (같은 인물은 같은 이름 사용)'}<input list="subtitle-speaker-names" value={name} maxLength={80} onChange={e => setName(e.target.value)} className="mt-2 w-full rounded bg-black/30 p-2"/><datalist id="subtitle-speaker-names">{names.map(n => <option key={n} value={n}/>)}</datalist></label>
            <label className="block text-sm">{thai ? 'เพศของตัวละคร' : '인물 성별'}<select value={gender} onChange={e => setGender(e.target.value)} className="ml-3 rounded bg-[#10141b] p-2"><option value="">{thai ? 'ยังไม่ยืนยัน' : '확인 필요'}</option><option value="male">{thai ? 'ชาย' : '남성'}</option><option value="female">{thai ? 'หญิง' : '여성'}</option></select></label>
            {error && <p role="alert" className="text-red-300">{error}</p>}
            <div className="flex justify-end gap-2"><button disabled={saving} onClick={onClose}>{thai ? 'ยกเลิก' : '취소'}</button><button disabled={saving || !name.trim()} className="rounded bg-emerald-600 px-4 py-2 disabled:opacity-40" onClick={async () => { setSaving(true); try { await onSave(name.trim(), gender); onClose() } catch { setError(thai ? 'บันทึกไม่สำเร็จ' : '저장에 실패했습니다.') } finally { setSaving(false) } }}>{thai ? 'บันทึก' : '저장'}</button></div>
        </div>
    </div>, document.body)
}
