/** Remember an explicitly dismissed terminal job without hiding newer jobs. */
export function ttsNoticeAcknowledged(storage: Pick<Storage, 'getItem'>, projectId: string, jobId: string): boolean {
    try { return storage.getItem(`std-tts-notice:${projectId}`) === jobId } catch { return false }
}

export function acknowledgeTtsNotice(storage: Pick<Storage, 'setItem'>, projectId: string, jobId: string): void {
    try { storage.setItem(`std-tts-notice:${projectId}`, jobId) } catch { /* Storage can be unavailable in private mode. */ }
}
