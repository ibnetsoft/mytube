import React from 'react'
import { createRoot } from 'react-dom/client'
import StdVideoModelSettings from '../../components/StdVideoModelSettings'
const headers = {}
let catalog: any = { models: [], active_id: null }
window.fetch = async (_url, init) => {
    if (init?.body) {
        const body = JSON.parse(String(init.body))
        if (body.action === 'save') catalog.models = [...catalog.models.filter((item: any) => item.id !== body.model.id), { ...body.model, has_key: true }]
        if (body.action === 'apply') catalog.active_id = body.id
        if (body.action === 'delete') { catalog.models = catalog.models.filter((item: any) => item.id !== body.id); if (catalog.active_id === body.id) catalog.active_id = null }
    }
    return new Response(JSON.stringify(catalog), { status: 200 })
}
createRoot(document.getElementById('root')!).render(<main style={{ background: '#101722', color: 'white', padding: 24 }}><StdVideoModelSettings headers={headers} /></main>)
