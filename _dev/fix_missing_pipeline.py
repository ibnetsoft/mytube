from pathlib import Path
roots=[Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]
for root in roots:
    path=root/'auth-web/app/api/std/projects/[projectId]/pipeline/route.ts'
    source=path.read_bytes()
    for old,new in [
        (".select('id,progress_payload')",".select('id,pipeline_run_id:progress_payload->>pipeline_run_id')"),
        ("const id = project.data.progress_payload?.pipeline_run_id","const id = project.data.pipeline_run_id"),
        (".eq('project_id', params.projectId).single()",".eq('project_id', params.projectId).maybeSingle()"),
        ("    const stages =", "    if (run.error) return NextResponse.json({ error: 'Pipeline read failed' }, { status: 503 })\n    if (!run.data) return NextResponse.json({ run: null, stages: [], render: null, status: 'missing_run', warning: '이전 제작 작업 기록을 찾지 못했습니다.' })\n    const stages ="),
        ("if (run.error || stages.error)","if (stages.error)"),
        (".eq('id', run.data.render_queue_id).single()", ".eq('id', run.data.render_queue_id).maybeSingle()"),
        ("    return NextResponse.json({ run: run.data, stages: stages.data, render: queue.data })", "    if (queue.error) return NextResponse.json({ error: 'Render status read failed' }, { status: 503 })\n    return NextResponse.json({ run: run.data, stages: stages.data, render: queue.data })"),
    ]:
        a,b=old.encode(),new.encode()
        if a not in source: a,b=a.replace(b'\n',b'\r\n'),b.replace(b'\n',b'\r\n')
        assert a in source,old
        source=source.replace(a,b,1)
    path.write_bytes(source)
    path=root/'auth-web/components/StdMouthPreviews.tsx'
    source=path.read_bytes()
    marker=b'        {pipeline?.run &&'
    assert marker in source
    source=source.replace(marker,"        {pipeline?.warning && <p className=\"mt-2 text-xs text-amber-200\" role=\"status\">{pipeline.warning}</p>}\n".encode()+marker,1)
    path.write_bytes(source)
