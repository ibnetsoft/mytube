type CoordinateStatus = {state:string;count:number;results?:unknown[];error?:string;updatedAt?:string;heartbeatAt?:string;currentScene?:number}
export function coordinateStatus(result:CoordinateStatus, now=Date.now()):string {
    const progress = `${result.results?.length || 0}/${result.count}`
    if (result.state === 'ready') return `확인 완료 (${result.count}개 대사씬)`
    if (result.state === 'needs_review') return `추가 확인 필요 (${progress}): ${result.error || '분석 결과를 확인해 주세요.'}`
    if (result.state === 'queued') return `작업기 연결 대기 (${progress}) · 로컬 캐릭터 확인 작업기가 실행되면 자동으로 시작됩니다.`
    if (result.state === 'processing') {
        const last = Date.parse(result.heartbeatAt || result.updatedAt || '')
        if (Number.isFinite(last) && now-last > 120000) return `작업기 응답 지연 (${progress}) · 작업기가 다시 연결되면 이어서 확인합니다.`
        return `캐릭터 분석 중 (${progress})${result.currentScene ? ` · ${result.currentScene}번 씬 확인 중` : ''}`
    }
    return `상태 확인 필요 (${progress})`
}
