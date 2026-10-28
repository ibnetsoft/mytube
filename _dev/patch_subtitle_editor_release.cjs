const fs=require('fs'),path=require('path');const root=fs.readFileSync('_dev/artifacts/subtitle_editor_deploy_root.txt','utf8').trim();
const read=p=>fs.readFileSync(path.join(root,p),'utf8').replace(/\r\n/g,'\n'),write=(p,s)=>fs.writeFileSync(path.join(root,p),s);
for(const name of ['stdSubtitleSceneIntegrity','stdSubtitleSnapshot','stdSubtitleFragments','stdSubtitleTranslation'])fs.copyFileSync('auth-web/lib/'+name+'.ts',path.join(root,'lib',name+'.ts'));
fs.copyFileSync('auth-web/app/api/std/projects/[projectId]/subtitle-translations/route.ts',path.join(root,'app/api/std/projects/[projectId]/subtitle-translations/route.ts'));
let page=read('app/std/page.tsx');
page=""+page.replace("'use client'\n","'use client'\nimport { restoreSavedSubtitleSnapshot } from '@/lib/stdSubtitleSnapshot'\n");
function replaceOnce(s,from,to){if(!s.includes(from))throw Error('Missing patch anchor '+from.slice(0,55));return s.replace(from,to)}
page=replaceOnce(page,"    en: {\n        code: 'EN'", "    ko: {\n        code: 'KO', name: '한국어', translating: '번역 중…', retry: '번역 실패 · 다시 시도',\n        candidate: '대사 후보', markDialogue: '대사로 지정', markNarration: '내레이션', automatic: '자동 감지',\n        dialogueVoice: '캐릭터 성우', narrationVoice: '내레이션 성우', pending: '번역 대기',\n    },\n    en: {\n        code: 'EN'");
page=page.replace(/\(\['en', 'vi', 'th'\] as const\)/g,"(['ko', 'en', 'vi', 'th'] as const)");
page=page.replace("currentLocale === 'th') ? currentLocale", "currentLocale === 'th' || currentLocale === 'ko') ? currentLocale");
page=page.replace(/        const canReuseSavedSubtitles =[\s\S]*?        const normalizedSubtitles =/, `        const subs = restoreSavedSubtitleSnapshot(savedSubtitles,\n            () => generateSynchronizedSubtitles(currentScript, scenes, Number(subMaxChars) || 20))\n        const normalizedSubtitles =`);
page=page.replace(/        const baseSubtitles = subtitlesMatchSceneManifest\(localSubtitles, scenes\)[\s\S]*?        const syncedSubtitles =/, `        const baseSubtitles = restoreSavedSubtitleSnapshot(localSubtitles,\n            () => generateSynchronizedSubtitles(selectedProject.project?.project_payload?.script || customScriptText || '', scenes, Number(subMaxChars) || 20))\n        const syncedSubtitles =`);
page=page.replace(/                const projectSubtitles = subtitlesMatchSceneManifest\(storedServerSubtitles, normalizedScenes\)[\s\S]*?\n\n                const fullProjectPayload/, `                const projectSubtitles = restoreSavedSubtitleSnapshot(storedServerSubtitles,\n                    () => generateSynchronizedSubtitles(fullScript, normalizedScenes, Number(subMaxChars) || 20))\n\n                const fullProjectPayload`);
const current=fs.readFileSync('auth-web/app/std/page.tsx','utf8').replace(/\r\n/g,'\n');
const translate=current.slice(current.indexOf('    const translateSubtitleBlocks ='),current.indexOf('    const safeParseJson ='));
page=page.slice(0,page.indexOf('    const translateSubtitleBlocks ='))+translate+page.slice(page.indexOf('    const safeParseJson ='));
page=page.replace(/\{ preferGemini: true \}/g,'{}');write('app/std/page.tsx',page);
let route=read('app/api/std/projects/[projectId]/route.ts');
route="import { preserveSubtitleScenes } from '@/lib/stdSubtitleSceneIntegrity'\nimport { normalizeSubtitleFragments } from '@/lib/stdSubtitleFragments'\n"+route;
route=replaceOnce(route,'    const protectedProject = {',`    const subtitlePayload = project.project_payload || {}
    if (Array.isArray(subtitlePayload.subtitles)) {
        const rows = normalizeSubtitleFragments(subtitlePayload.subtitles, 20, { punctuationOnly: true })
        const repaired = preserveSubtitleScenes(rows, subtitlePayload.subtitle_editor_snapshot || rows,
            scenes || [], subtitlePayload.deleted_subtitle_scene_numbers || []).subtitles
        if (JSON.stringify(repaired) !== JSON.stringify(subtitlePayload.subtitles)) {
            const { data: restored, error: restoreError } = await supabaseAdmin.from('std_projects')
                .update({ project_payload: { ...subtitlePayload, subtitles: repaired, subtitle_editor_snapshot: repaired }, updated_at: new Date().toISOString() })
                .eq('id', project.id).eq('updated_at', project.updated_at).select('*').maybeSingle()
            if (restoreError) return NextResponse.json({ success: false, error: restoreError.message }, { status: 503 })
            if (!restored) return NextResponse.json({ success: false, error: 'Project changed while saving; reload and retry' }, { status: 409 })
            project = restored
        }
    }
    const protectedProject = {`);
route=replaceOnce(route,"    const incomingProjectPayload = body?.project_payload || {}",`    const incomingProjectPayload = body?.project_payload || {}
    if (Array.isArray(incomingProjectPayload.subtitles)) {
        const current = project.project_payload || {}
        const previous = preserveSubtitleScenes(current.subtitles || [], current.subtitle_editor_snapshot || current.subtitles || [], [], current.deleted_subtitle_scene_numbers || []).subtitles
        incomingProjectPayload.subtitles = preserveSubtitleScenes(
            normalizeSubtitleFragments(incomingProjectPayload.subtitles, 20, { punctuationOnly: true }), previous, [],
            current.deleted_subtitle_scene_numbers || []).subtitles
    }`);
route=replaceOnce(route,'    if (titlePatch) updatePayload.title = titlePatch',`    if (updatePayload.project_payload) {
        updatePayload.project_payload.subtitle_editor_snapshot = Array.isArray(projectPayloadPatch.subtitles)
            ? projectPayloadPatch.subtitles : scriptChanged ? []
                : project.project_payload?.subtitle_editor_snapshot || project.project_payload?.subtitles || []
    }
    if (titlePatch) updatePayload.title = titlePatch`);
route=replaceOnce(route,"        .eq('status', project.status)\n        .select('*')\n        .single()", "        .eq('status', project.status)\n        .eq('updated_at', project.updated_at)\n        .select('*')\n        .maybeSingle()");
route=replaceOnce(route,"    let updatedScenes: any[] | null = null", "    if (!updated) return NextResponse.json({ success: false, error: 'Project changed while saving; reload and retry' }, { status: 409 })\n    let updatedScenes: any[] | null = null");write('app/api/std/projects/[projectId]/route.ts',route);
fs.copyFileSync('auth-web/tests/std-subtitle-scene-integrity.cjs',path.join(root,'tests-subtitle-scene-integrity.cjs'));
console.log('Patched deployed page restoration, persisted editor snapshot, and local Codex translation queue.');
