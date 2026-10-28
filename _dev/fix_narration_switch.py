from pathlib import Path
roots=[Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]
for root in roots:
    path=root/'auth-web/app/std/page.tsx'
    data=path.read_bytes()
    anchor=b"import { restoreSavedSubtitleSnapshot }"
    assert anchor in data
    data=data.replace(anchor,b"import { assignSubtitleNarration, subtitleDialogueDisplayParts } from '@/lib/stdSubtitleNarration'\n"+anchor,1)
    start=data.index(b'        const parts = aiDialogueParts.get(index)',data.index(b'    const renderAiDialogue ='))
    end=data.index(b'\n    }',start)
    data=data[:start]+b'''        const speakerName = subtitleSpeakers[index]?.name || subtitle?.dialogue_speaker || 'Dialogue'
        return subtitleDialogueDisplayParts(subtitle, aiDialogueParts.get(index), isSubtitleDialogue(subtitle, index), speakerName)
            .map((part, i) => <span key={i} className={part.dialogue ? 'text-yellow-300' : undefined}
                title={part.dialogue ? `Dialogue: ${part.speaker || speakerName}` : undefined}>{part.text}</span>)'''+data[end:]
    old=b"const updated = localSubtitles.map((sub, index) => index === item.subtitleIndex ? { ...sub, dialogue_override: false } : sub)"
    assert old in data
    data=data.replace(old,b'''const current = speechSubtitlesRef.current
                                                                                                const updated = assignSubtitleNarration(current, item.subtitleIndex, selectedVoice, voiceNameById, isSubtitleNarration)
                                                                                                if (String(updated[item.subtitleIndex]?.voice_id || selectedVoice) !== String(current[item.subtitleIndex]?.voice_id || selectedVoice)) {
                                                                                                    if (isPlayingPreview) stopVrewPlayback()
                                                                                                    markVrewSegmentStale(updated[item.subtitleIndex], item.subtitleIndex)
                                                                                                }''',1)
    path.write_bytes(data)
