from pathlib import Path
import difflib
roots = [Path.cwd(), Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]
def change(root, name, old, new):
    p = root / name
    b = p.read_bytes()
    original = b.decode().splitlines(keepends=True)
    text = b.decode().replace('\r\n','\n')
    if old not in text and new in text: return
    assert old in text, name + ' missing replacement: ' + old[:60]
    current = text.replace(old,new,1).splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None,[x.rstrip('\r\n') for x in original],[x.rstrip('\r\n') for x in current],autojunk=False)
    output=[]
    for kind,a,b,c,d in matcher.get_opcodes(): output.extend(original[a:b] if kind=='equal' else current[c:d])
    p.write_bytes(''.join(output).encode())
for root in roots:
    name = 'auth-web/components/StdMotionAutomation.tsx'
    change(root,name,"import type { MotionDraft }", "import { startVisiblePolling } from '@/lib/stdVisiblePolling'\nimport type { MotionDraft }")
    p = root/name
    b = p.read_bytes(); lines = b.splitlines(keepends=True)
    idx = next((i for i,l in enumerate(lines) if b'const timer=setInterval(load,15000)' in l),None)
    if idx is None: idx = len(lines); lines.append(b'')
    lines[idx] = b"    const headerKey = JSON.stringify(headers)\r\n    useEffect(() => {\r\n        if (planningOnly) return\r\n        let cancelled = false\r\n        const stop = startVisiblePolling(async signal => {\r\n            try {\r\n                const response = await fetch(`/api/std/projects/${projectId}/motion-automation`, { headers: JSON.parse(headerKey), signal })\r\n                const data = await response.json()\r\n                if (!response.ok) throw Error(data.error || 'State request failed')\r\n                if (!cancelled && !signal.aborted) { setJob(data.job); setError('') }\r\n                return data.job && ['queued', 'processing'].includes(data.job.state) ? 15000 : 60000\r\n            } catch (error: any) {\r\n                if (!cancelled && !signal.aborted) setError(error.message)\r\n                throw error\r\n            }\r\n        }, 15000)\r\n        return () => { cancelled = true; stop() }\r\n    }, [projectId, headerKey, planningOnly])\r\n"
    if b'const timer=setInterval(load,15000)' in b: p.write_bytes(b''.join(lines))
    # Existing full-input panels: serialize, abort on unmount, and pause hidden tabs.
    name = 'auth-web/components/StdMouthPreviews.tsx'
    change(root,name,"import { useEffect, useState } from 'react'", "import { useEffect, useState } from 'react'\nimport { startVisiblePolling } from '@/lib/stdVisiblePolling'")
    change(root,name,'        const read = async () => {','        const read = async (signal: AbortSignal) => {')
    change(root,name,'signal: abort.signal','signal')
    change(root,name,'signal: abort.signal','signal')
    change(root,name,'                if (response.ok) setData(next)','                if (!response.ok) throw Error(next.error || \'State request failed\')\n                if (!abort.signal.aborted && !signal.aborted) setData(next)')
    change(root,name,'                if (run.ok) setPipeline(await run.json())\n            } catch {}','                if (!run.ok) throw Error(\'Pipeline request failed\')\n                const pipeline = await run.json()\n                if (!abort.signal.aborted && !signal.aborted) setPipeline(pipeline)\n            } catch (error) { throw error }')
    change(root,name,'        void read()\n        const timer = setInterval(read, 10000)\n        return () => { clearInterval(timer); abort.abort() }','        const stop = startVisiblePolling(read, 15000)\n        return () => { stop(); abort.abort() }')
    name = 'auth-web/components/StdLipSyncPanel.tsx'
    change(root,name,"import { useEffect, useState } from 'react'", "import { useEffect, useState } from 'react'\nimport { startVisiblePolling } from '@/lib/stdVisiblePolling'")
    change(root,name,'        const read = async () => {','        const read = async (signal: AbortSignal) => {')
    change(root,name,'signal: controller.signal','signal')
    change(root,name,'                if (live) { if (!r.ok) setError(d.error); else setData(d) }\n            } catch (e: any) { if (live) setError(e.message) }','                if (!r.ok) throw Error(d.error || \'State request failed\')\n                if (live && !signal.aborted) setData(d)\n            } catch (e: any) { if (live && !signal.aborted) setError(e.message); throw e }')
    change(root,name,'        void read()\n        const timer = setInterval(read, 10000)\n        return () => { live = false; controller.abort(); clearInterval(timer) }','        const stop = startVisiblePolling(read, 15000)\n        return () => { live = false; controller.abort(); stop() }')
    name = 'auth-web/app/api/std/projects/[projectId]/motion-automation/route.ts'
    change(root,name,".select('id,created_at,updated_at,metadata')", ".select('id,kind:metadata->>kind,state:metadata->>state,phase:metadata->>phase,progress:metadata->progress,error:metadata->>error,results:metadata->results,total_scenes:metadata->total_scenes,supplemental_assets:metadata->supplemental_assets,final:metadata->final')")
    text = (root/name).read_text(encoding='utf-8')
    if 'm=job?.metadata' in text:
        start=text.index('    const job=result.data')
        end=text.index('    return NextResponse.json',start)
        change(root,name,text[start:end],"    const job=result.data,m=job\n    const engine=m?.kind==='effectcraft_automation'?'effectcraft':m?.kind==='filmcraft_automation'?'filmcraft':'ae'\n")
