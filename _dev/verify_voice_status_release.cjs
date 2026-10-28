const fs = require('fs');
(async () => {
    const response = await fetch('https://studio.airing.work/std', { cache: 'no-store' });
    if (!response.ok) throw Error(`Production HTTP ${response.status}`);
    const html = await response.text();
    const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(m => new URL(m[1], response.url).href);
    let found;
    await Promise.all(scripts.map(async url => {
        const source = await (await fetch(url)).text();
        const offset = source.indexOf('성우 미지정 대사 {missing}개');
        if (offset < 0) return;
        const start = source.lastIndexOf('function ', offset);
        const snippet = source.slice(start, offset + 3000);
        const passed = snippet.includes('"aria-busy":')
            && snippet.includes('내레이션과 같은 성우를 쓰는 대사 {shared}개')
            && /["']details["'],\{className:["']mt-1 text-gray-400["'],children:/.test(snippet)
            && snippet.includes('같은 성우를 쓰는 내레이션 위치 {count}개 보기');
        found = { url, passed, snippet };
    }));
    if (!found) throw Error('Voice status component not found in production scripts');
    fs.writeFileSync('_dev/artifacts/voice_status_production_verification.json', JSON.stringify({ checkedAt: new Date().toISOString(), httpStatus: response.status, ...found }, null, 2));
    console.log(JSON.stringify({ httpStatus: response.status, bundle: found.url, statusRemainsVisible: found.passed }));
    if (!found.passed) process.exitCode = 1;
})().catch(e => { console.error(e.message); process.exitCode = 1; });
