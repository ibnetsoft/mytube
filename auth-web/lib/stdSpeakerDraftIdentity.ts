/** Rebind a draft only when the pixels, cast and speaker list are still identical. */
export function canRetainSpeakerDraft(previous: any, scene: any, sha: string) {
    return !!previous && !!previous.castKey && previous.number === scene.number
        && previous.castKey === scene.castKey && /^[a-f0-9]{64}$/.test(previous.sha)
        && previous.sha === sha
        && JSON.stringify([...previous.speakers].sort()) === JSON.stringify([...new Set(scene.rows.map((r: any) => r.speaker))].sort())
}
