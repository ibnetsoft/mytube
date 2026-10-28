from pathlib import Path
for root in [Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]:
    path=root/'auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts'
    data=path.read_bytes()
    def change(old,new):
        global data
        a,b=old.encode(),new.encode()
        if a not in data:a,b=a.replace(b'\n',b'\r\n'),b.replace(b'\n',b'\r\n')
        assert a in data,old[:70]
        data=data.replace(a,b,1)
    change('import { assembleStoredNarration }', 'import { assembleStoredNarration, prepareStoredNarration }')
    change('            const assembled = await assembleStoredNarration(voiceSegments, {', '            const narrationIo: Parameters<typeof assembleStoredNarration>[1] = {')
    change('            }, { allowGenerate: !assembleOnly })\n            audioBuffer = assembled.audioBuffer', '''            }
            if (prepareOnly) {
                stage = 'prepare_segment_references'
                const prepared = await prepareStoredNarration(voiceSegments, narrationIo.resolve)
                return NextResponse.json({ success: true, prepared: prepared.prepared,
                    segment_reuse: { reused: prepared.reused, generated: prepared.generated } })
            }
            const assembled = await assembleStoredNarration(voiceSegments, narrationIo, { allowGenerate: !assembleOnly })
            audioBuffer = assembled.audioBuffer''')
    change('''            if (prepareOnly) {
                // No full narration asset or project completion update until the final join.
                return NextResponse.json({ success: true, prepared: voiceSegments.length, segment_reuse: segmentReuse })
            }
''','')
    path.write_bytes(data)
