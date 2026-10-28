import policy from './productionEnginePolicy.json'

export const alternativeEnginesEnabled = policy.alternative_engines_enabled === true
export function productionEngineError(project: any): string | null {
    if (alternativeEnginesEnabled) return null
    const motion = project?.project_payload?.render_settings?.motion
    if (['effectcraft', 'filmcraft', 'motion_studio'].includes(motion?.production_method) || motion?.web || motion?.final_renderer === 'filmcraft') {
        return '대체 제작 엔진은 현재 비활성화되어 있습니다. 제작 방식을 After Effects로, 최종 조립을 기본 FFmpeg로 변경·저장한 뒤 다시 요청하세요. 기존 설정과 결과는 보존됩니다.'
    }
    return null
}
