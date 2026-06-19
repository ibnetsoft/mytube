'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'

type MusicPlanTemplate = {
  id?: string
  key_code: string
  display_name_ko: string
  display_name_vi?: string
  prompt_template: string
  gemini_instruction?: string
  image_url?: string
  created_at?: string
}

const emptyForm: MusicPlanTemplate = {
  key_code: '',
  display_name_ko: '',
  display_name_vi: '',
  prompt_template: '',
  gemini_instruction: '',
  image_url: '',
}

export default function MusicPlanTemplatesPage() {
  const [templates, setTemplates] = useState<MusicPlanTemplate[]>([])
  const [form, setForm] = useState<MusicPlanTemplate>(emptyForm)
  const [editingId, setEditingId] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const pageTitle = useMemo(() => editingId ? 'Edit Music Plan Template' : 'Music Plan Templates', [editingId])

  async function fetchTemplates() {
    setLoading(true)
    try {
      const res = await fetch('/api/admin/music-plan-templates')
      const data = await res.json()
      if (res.ok && data.templates) setTemplates(data.templates)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTemplates()
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await fetch('/api/admin/music-plan-templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          id: editingId || undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) {
        alert(data.error || 'Save failed')
        return
      }
      setForm(emptyForm)
      setEditingId('')
      fetchTemplates()
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(item: MusicPlanTemplate) {
    if (!confirm(`Delete template "${item.key_code}"?`)) return
    const query = item.id ? `id=${encodeURIComponent(item.id)}` : `key_code=${encodeURIComponent(item.key_code)}`
    const res = await fetch(`/api/admin/music-plan-templates?${query}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok || !data.success) {
      alert(data.error || 'Delete failed')
      return
    }
    fetchTemplates()
  }

  function startEdit(item: MusicPlanTemplate) {
    setEditingId(item.id || '')
    setForm({
      key_code: item.key_code || '',
      display_name_ko: item.display_name_ko || '',
      display_name_vi: item.display_name_vi || '',
      prompt_template: item.prompt_template || '',
      gemini_instruction: item.gemini_instruction || '',
      image_url: item.image_url || '',
    })
  }

  return (
    <main className="min-h-screen bg-[#0b1020] text-white px-6 py-8">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-black uppercase tracking-[0.18em] text-blue-300">Admin</div>
            <h1 className="mt-2 text-3xl font-black">{pageTitle}</h1>
            <p className="mt-2 text-sm text-gray-400">60곡 음악기획 템플릿을 저장하고 로컬 음악기획 페이지에서 불러옵니다.</p>
          </div>
          <a href="/dashboard" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-black text-gray-300 hover:bg-white/10">Dashboard</a>
        </div>

        <section className="rounded-3xl border border-white/10 bg-[#0f172a]/70 p-6 shadow-2xl">
          <div className="mb-4 rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="text-xs font-black uppercase tracking-[0.14em] text-blue-300">Template JSON Guide</div>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-[11px] text-gray-400">{`{
  "playlist_title": "Midnight City Drive",
  "genre": "lofi",
  "vocal_mode": "instrumental",
  "track_count": 60,
  "playlist_duration_seconds": 14400,
  "moods": ["calm", "dreamy", "rainy_night"],
  "lyrics_mode": "instrumental",
  "style_prompt": "warm night drive, soft tape texture, gentle bass",
  "style_tags": ["night drive", "soft piano", "vinyl"],
  "vocal_gender": "any",
  "genre_mix": ["lofi", "ambient", "city_pop"],
  "vocal_mode_distribution": ["instrumental", "instrumental", "soft_vocal"],
  "vocal_gender_distribution": ["female", "male", "duet"],
  "lyrics_ratio_percent": 20,
  "duration_distribution": {
    "sequence": [210, 240, 270]
  },
  "weirdness": 35,
  "style_influence": 70
}`}</pre>
          </div>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <input className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" placeholder="key_code" value={form.key_code} onChange={e => setForm(prev => ({ ...prev, key_code: e.target.value }))} required />
            <input className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" placeholder="display_name_ko" value={form.display_name_ko} onChange={e => setForm(prev => ({ ...prev, display_name_ko: e.target.value }))} required />
            <input className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" placeholder="display_name_vi" value={form.display_name_vi} onChange={e => setForm(prev => ({ ...prev, display_name_vi: e.target.value }))} />
            <input className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" placeholder="image_url" value={form.image_url} onChange={e => setForm(prev => ({ ...prev, image_url: e.target.value }))} />
            <textarea className="min-h-[120px] rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none md:col-span-2" placeholder="prompt_template" value={form.prompt_template} onChange={e => setForm(prev => ({ ...prev, prompt_template: e.target.value }))} required />
            <textarea className="min-h-[160px] rounded-xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-xs outline-none md:col-span-2" placeholder='{"track_count":60,"playlist_duration_seconds":14400,"genre":"lofi"}' value={form.gemini_instruction} onChange={e => setForm(prev => ({ ...prev, gemini_instruction: e.target.value }))} />
            <div className="md:col-span-2 flex gap-3">
              <button type="submit" disabled={saving} className="rounded-xl bg-blue-600 px-5 py-3 text-xs font-black hover:bg-blue-500 disabled:opacity-50">{saving ? 'Saving...' : 'Save Template'}</button>
              <button type="button" onClick={() => { setEditingId(''); setForm(emptyForm) }} className="rounded-xl border border-white/10 bg-white/5 px-5 py-3 text-xs font-black text-gray-300 hover:bg-white/10">Reset</button>
            </div>
          </form>
        </section>

        <section className="rounded-3xl border border-white/10 bg-[#0f172a]/70 p-6 shadow-2xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-black">Saved Templates</h2>
            <button onClick={fetchTemplates} className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-black text-gray-300 hover:bg-white/10">Refresh</button>
          </div>
          {loading ? (
            <div className="py-8 text-sm text-gray-400">Loading...</div>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {templates.map(item => (
                <div key={item.id || item.key_code} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-black">{item.display_name_ko}</div>
                      <div className="mt-1 text-[11px] font-mono text-gray-400">{item.key_code}</div>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => startEdit(item)} className="rounded-lg bg-blue-600/15 px-3 py-1.5 text-[11px] font-black text-blue-300 hover:bg-blue-600 hover:text-white">Edit</button>
                      <button onClick={() => handleDelete(item)} className="rounded-lg bg-red-600/15 px-3 py-1.5 text-[11px] font-black text-red-300 hover:bg-red-600 hover:text-white">Delete</button>
                    </div>
                  </div>
                  <div className="mt-3 whitespace-pre-wrap rounded-xl border border-white/5 bg-black/30 p-3 text-xs text-gray-300">{item.prompt_template}</div>
                  {item.gemini_instruction && (
                    <div className="mt-3 whitespace-pre-wrap rounded-xl border border-white/5 bg-black/30 p-3 font-mono text-[11px] text-gray-400">{item.gemini_instruction}</div>
                  )}
                </div>
              ))}
              {!templates.length && <div className="py-8 text-sm text-gray-500">No templates yet.</div>}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
