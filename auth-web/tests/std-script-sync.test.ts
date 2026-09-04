import assert from 'node:assert/strict'
import {
    generateSynchronizedSubtitles,
    partitionScriptByExistingSceneBoundaries,
    repairSubtitleItemQuoteBoundaries,
    splitTextToSingleLineChunks,
} from '../lib/stdSubtitles'

const sceneCount = 53
const makeSceneText = (index: number) => `씬 ${index} 원본 문장입니다. 가족은 오래된 약속을 기억합니다.`
const baseScenes = Array.from({ length: sceneCount }, (_, index) => ({
    scene_number: index + 1,
    scene_text: makeSceneText(index + 1),
    script_excerpt: makeSceneText(index + 1),
    image_url: `drive-image-${index + 1}`,
    video_url: index < 12 ? `drive-video-${index + 1}` : null,
}))
const baseScript = baseScenes.map(scene => scene.scene_text).join('\n\n')

function syncLikeStdPage(script: string, scenes = baseScenes) {
    const partitioned = partitionScriptByExistingSceneBoundaries(script, scenes, scenes.length)
    const syncedScenes = scenes.map((scene, index) => {
        const text = partitioned[index] || ''
        return {
            ...scene,
            text,
            scene_text: text,
            script_text: text,
            script_excerpt: text,
            narration: text,
            narration_text: text,
            prompt_ko: text,
        }
    })
    return {
        scenes: syncedScenes,
        subtitles: generateSynchronizedSubtitles(script, syncedScenes, 20),
    }
}

const caseA = syncLikeStdPage(baseScript.replace(
    '씬 10 원본 문장입니다.',
    '씬 10 수정된 핵심 문장입니다.'
))
assert.match(caseA.scenes[9].scene_text, /수정된 핵심 문장/)
assert.match(caseA.scenes[9].script_excerpt, /수정된 핵심 문장/)
assert.match(caseA.scenes[9].narration_text, /수정된 핵심 문장/)
assert.ok(caseA.subtitles.some(sub => sub.scene_number === 10 && sub.text.includes('수정된')))

const caseB = syncLikeStdPage(baseScript.replace(
    '씬 10 원본 문장입니다.',
    '씬 10 원본 문장입니다. 새로 추가된 증거 문장입니다.'
))
assert.ok(
    caseB.scenes.slice(8, 11).some(scene => scene.scene_text.includes('새로 추가된 증거')),
    'added sentence should remain near the edited scene boundary'
)
assert.equal(caseB.scenes[9].image_url, 'drive-image-10')
assert.equal(caseB.scenes[9].video_url, 'drive-video-10')

const caseC = syncLikeStdPage(baseScript.replace(makeSceneText(10), ''))
assert.ok(!caseC.scenes.some(scene => scene.scene_text.includes('씬 10 원본 문장입니다')))
assert.ok(!caseC.subtitles.some(sub => sub.text.includes('씬 10 원본 문장입니다')))

const rewrittenScript = baseScenes
    .map((scene, index) => index % 2 === 0
        ? scene.scene_text.replace('가족은 오래된 약속을 기억합니다.', `대량 수정 문단 ${index + 1}입니다.`)
        : scene.scene_text
    )
    .join('\n\n')
const caseD = syncLikeStdPage(rewrittenScript)
assert.equal(caseD.scenes.length, sceneCount)
assert.ok(caseD.scenes[0].scene_text.includes('대량 수정 문단 1'))
assert.ok(caseD.scenes[52].scene_text.length > 0)
assert.ok(caseD.subtitles.length >= sceneCount)

const quotedSubtitleChunks = splitTextToSingleLineChunks(
    "'저 아들, 어머니를 버렸나 봐.' '죽었을 수도 있지 않을까?'",
    20
)
assert.equal(quotedSubtitleChunks[0], "'저 아들, 어머니를 버렸나 봐.'")
assert.equal(quotedSubtitleChunks[1], "'죽었을 수도 있지 않을까?'")

const persistedBrokenQuotes = repairSubtitleItemQuoteBoundaries([
    { scene_number: 9, text: "'저 아들, 어머니를 버렸나 봐." },
    { scene_number: 10, text: "'죽었을 수도 있지 않을까?" },
])
assert.equal(persistedBrokenQuotes[0].text, "'저 아들, 어머니를 버렸나 봐.'")
assert.equal(persistedBrokenQuotes[1].text, "'죽었을 수도 있지 않을까?'")

const quoteDraggedToNextScene = repairSubtitleItemQuoteBoundaries([
    { scene_number: 10, text: "'죽었을 수도 있지 않을까?" },
    { scene_number: 11, text: "'이렇게까지 받지 않다니, 뭔가" },
    { scene_number: 11, text: "있는 거 아닐까?" },
])
assert.equal(quoteDraggedToNextScene[0].text, "'죽었을 수도 있지 않을까?'")
assert.equal(quoteDraggedToNextScene[1].text, "'이렇게까지 받지 않다니, 뭔가")
assert.equal(quoteDraggedToNextScene[2].text, "있는 거 아닐까?'")

const duplicatedOpeningQuotes = repairSubtitleItemQuoteBoundaries([
    { scene_number: 10, text: "' '죽었을 수도 있지 않을까?" },
    { scene_number: 11, text: "' '이렇게까지 받지 않다니, 뭔가" },
    { scene_number: 11, text: "있는 거 아닐까?" },
])
assert.equal(duplicatedOpeningQuotes[0].text, "'죽었을 수도 있지 않을까?'")
assert.equal(duplicatedOpeningQuotes[1].text, "'이렇게까지 받지 않다니, 뭔가")
assert.equal(duplicatedOpeningQuotes[2].text, "있는 거 아닐까?'")

const narrationWithStrayQuotes = repairSubtitleItemQuoteBoundaries([
    { scene_number: 12, text: "' 그런 말들이 할머니 귀에" },
    { scene_number: 12, text: "들어왔지.'" },
])
assert.equal(narrationWithStrayQuotes[0].text, '그런 말들이 할머니 귀에')
assert.equal(narrationWithStrayQuotes[1].text, '들어왔지.')

const alreadyClosedPreviousQuote = repairSubtitleItemQuoteBoundaries([
    { scene_number: 10, text: "'죽었을 수도 있지 않을까?'" },
    { scene_number: 11, text: "'이렇게까지 받지 않다니, 뭔가" },
    { scene_number: 11, text: "있는 거 아닐까?" },
    { scene_number: 12, text: "그런 말들이 할머니 귀에" },
    { scene_number: 12, text: "들어왔지." },
])
assert.equal(alreadyClosedPreviousQuote[0].text, "'죽었을 수도 있지 않을까?'")
assert.equal(alreadyClosedPreviousQuote[1].text, "'이렇게까지 받지 않다니, 뭔가")
assert.equal(alreadyClosedPreviousQuote[2].text, "있는 거 아닐까?'")
assert.equal(alreadyClosedPreviousQuote[3].text, "그런 말들이 할머니 귀에")
assert.equal(alreadyClosedPreviousQuote[4].text, "들어왔지.")

const splitSceneQuote = repairSubtitleItemQuoteBoundaries([
    { scene_number: 11, text: "'이렇게까지 받지 않는다니, 뭔가" },
    { scene_number: 11, text: "있는 거 아닐까?" },
])
assert.equal(splitSceneQuote[0].text, "'이렇게까지 받지 않는다니, 뭔가")
assert.equal(splitSceneQuote[1].text, "있는 거 아닐까?'")

const mixedNarrationAndDialogue = repairSubtitleItemQuoteBoundaries([
    { id: 'mixed-1', scene_number: 20, start_num: 0, end_num: 4, start_time: '0.0', end_time: '4.0', text: '만약 아들이 말할 수 있었다면 이렇게' },
    { id: 'mixed-2', scene_number: 20, start_num: 4, end_num: 8, start_time: '4.0', end_time: '8.0', text: "말했을 거야. '엄마, 미안해. 나는", voice_id: 'dialogue-voice', voice_name: 'Dialogue' },
    { id: 'mixed-3', scene_number: 20, start_num: 8, end_num: 12, start_time: '8.0', end_time: '12.0', text: "성공하지 못했어.'", voice_id: 'dialogue-voice', voice_name: 'Dialogue' },
])
assert.deepEqual(mixedNarrationAndDialogue.map(item => item.text), [
    '만약 아들이 말할 수 있었다면 이렇게',
    '말했을 거야.',
    "'엄마, 미안해. 나는",
    "성공하지 못했어.'",
])
assert.equal(mixedNarrationAndDialogue[1].voice_id, undefined)
assert.equal(mixedNarrationAndDialogue[2].voice_id, 'dialogue-voice')
assert.equal(mixedNarrationAndDialogue[1].start_num, 4)
assert.equal(mixedNarrationAndDialogue[2].end_num, 8)
assert.equal(mixedNarrationAndDialogue[1].end_num, mixedNarrationAndDialogue[2].start_num)

const dialogueThenNarration = repairSubtitleItemQuoteBoundaries([
    { scene_number: 21, text: "'괜찮아.' 그리고 그는 돌아섰다." },
])
assert.deepEqual(dialogueThenNarration.map(item => item.text), ["'괜찮아.'", '그리고 그는 돌아섰다.'])

const englishApostrophe = repairSubtitleItemQuoteBoundaries([
    { scene_number: 22, text: "It's still narration." },
])
assert.deepEqual(englishApostrophe.map(item => item.text), ["It's still narration."])

console.log('STD script sync regression tests passed')
