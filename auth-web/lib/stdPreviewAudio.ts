// Loading a file is not playback: auxiliary tracks follow the narration media clock.
export function bindNarrationPlayback(audio: HTMLAudioElement, onPlaying: () => void, onStopped: () => void) {
    audio.addEventListener('playing', onPlaying)
    const stops = ['waiting', 'pause', 'ended', 'error']
    stops.forEach(event => audio.addEventListener(event, onStopped))
    return () => {
        audio.removeEventListener('playing', onPlaying)
        stops.forEach(event => audio.removeEventListener(event, onStopped))
        onStopped()
    }
}

export function narrationLoadError(body: string, status: number) {
    if (/invalid_grant|drive_credentials_not_configured|drive_admin_credentials_incomplete/.test(body)) {
        return '저장된 음성을 불러오려면 Google Drive를 다시 연결해야 합니다. Drive 인증이 만료되었거나 해제되었습니다. 기존 음성은 새로 생성하지 않았습니다.'
    }
    return `저장된 음성 파일을 불러오지 못했습니다. (${status}) 잠시 후 다시 시도해 주세요.`
}

export async function resolveStoredSegmentAudio(
    request: (repairLegacy?: boolean) => Promise<any>,
    read: (payload: any) => Promise<string>,
    onRepair: () => void,
) {
    // Never spend TTS credits to repair a file access/authentication failure.
    const payload = await request()
    return await read(payload)
}
