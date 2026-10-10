const sceneNumber = (scene: any) => Number(scene?.scene_number ?? scene?.scene_order ?? scene?.number)

export type SceneDirectionBadge = {
    kind: 'eye' | 'mouth' | 'layer' | 'parallax' | 'motion' | 'camera' | 'light' | 'atmosphere' | 'review'
    label: string
    detail?: string
    state: 'planned' | 'verified' | 'needs_review'
}

const directionFor = (scene: any) => scene?.scene_direction_plan || scene?.ae_directorial_plan
    || scene?.metadata?.scene_direction_plan || scene?.metadata?.ae_directorial_plan

const geometryFor = (scene: any) => scene?.metadata?.cowork_image_asset?.speaker_geometry
    || scene?.speaker_geometry || null

const isSha256 = (value: unknown) => /^[a-f0-9]{64}$/i.test(String(value || '').trim())

/**
 * A scene may advertise a layer plan before the files are usable. Only treat it
 * as complete when the reviewed PSD is stored in GCS and the scene-level ready
 * receipt links that exact asset back into metadata.
 */
export function hasApprovedGcsLayerAsset(scene: any): boolean {
    const asset = scene?.metadata?.psd_layer_asset
    return Boolean(
        scene?.psd_layer_status === 'ready'
        && asset?.source === 'independently_authored_png_layers'
        && asset?.storage_provider === 'gcs'
        && String(asset?.gcs_bucket || '').trim()
        && String(asset?.gcs_path || '').trim()
        && isSha256(asset?.sha256)
        && Array.isArray(asset?.layers)
        && asset.layers.length > 0
        && asset.layers.every((role: unknown) => typeof role === 'string' && role.trim())
        && asset?.qa_status === 'approved'
        && asset?.review
        && typeof asset.review === 'object'
    )
}

/** Return only an explicitly enabled script-worker eye-blink direction for this scene. */
export function directedEyeBlinkPlan(scenes: any[], number: number) {
    for (const scene of scenes || []) {
        if (!scene || sceneNumber(scene) !== Number(number)) continue
        const direction = directionFor(scene)
        const plan = direction?.eye_blink_plan
        if (plan?.enabled === true && Array.isArray(plan.cues) && plan.cues.length > 0) return plan
    }
    return null
}

/** Summarize saved directing and validation receipts without inventing UI state. */
export function sceneDirectionBadges(scenes: any[], number: number): SceneDirectionBadge[] {
    const matches = (scenes || []).filter(scene => scene && sceneNumber(scene) === Number(number))
    const direction = matches.map(directionFor).find(Boolean)
    const geometry = matches.map(geometryFor).find(Boolean)
    const layeredScene = matches.find(hasApprovedGcsLayerAsset)
    if (!direction && !geometry && !layeredScene) return []

    const operations = new Set<string>(Array.isArray(direction?.ae_operations) ? direction.ae_operations : [])
    const requiredLayers = new Set<string>(Array.isArray(direction?.required_layers) ? direction.required_layers : [])
    const badges: SceneDirectionBadge[] = []
    const blink = direction?.eye_blink_plan
    if (blink?.enabled === true && Array.isArray(blink.cues) && blink.cues.length) {
        const receipt = geometry?.eye_blink
        const state = receipt?.state === 'ready' ? 'verified' : receipt?.state === 'skipped' ? 'needs_review' : 'planned'
        const times = blink.cues.map((cue: any) => Number(cue?.at_seconds)).filter(Number.isFinite).map((at: number) => `${at}초`)
        badges.push({ kind: 'eye', label: '눈 깜빡임', state,
            detail: [blink.character, times.join(', ')].filter(Boolean).join(' · ') })
    }

    const visibleSpeakers = Array.isArray(geometry?.speakers)
        ? geometry.speakers.filter((speaker: any) => speaker?.status === 'visible' && speaker?.mouth_box) : []
    if (visibleSpeakers.length) badges.push({ kind: 'mouth', label: '입모양 좌표', state: 'verified',
        detail: visibleSpeakers.map((speaker: any) => speaker.speaker).filter(Boolean).join(', ') })

    const layeredApproved = Boolean(layeredScene)
    if (layeredApproved) badges.push({ kind: 'layer', label: '레이어 완료', state: 'verified',
        detail: 'GCS 저장 · 씬 연결 · 검수 완료' })
    if (operations.has('depth_parallax')) badges.push({ kind: 'parallax', label: '패럴랙스',
        state: layeredApproved ? 'verified' : 'needs_review', detail: layeredApproved ? '승인 레이어' : '승인 레이어 필요' })

    if (operations.has('pose_change') || operations.has('prop_motion')
        || requiredLayers.has('hair_cloth') || requiredLayers.has('prop_focus')) {
        badges.push({ kind: 'motion', label: '부분 움직임', state: layeredApproved ? 'verified' : 'needs_review',
            detail: [...requiredLayers].filter(role => role === 'hair_cloth' || role === 'prop_focus').join(', ') })
    }
    if (operations.has('camera_move')) badges.push({ kind: 'camera', label: '카메라 연출', state: 'planned',
        detail: direction?.focus_target?.reason || '' })
    if (operations.has('light_flicker')) badges.push({ kind: 'light', label: '조명 연출', state: 'planned' })
    if (operations.has('atmosphere_drift')) badges.push({ kind: 'atmosphere', label: '분위기 효과', state: 'planned' })

    const reviewItems = badges.filter(badge => badge.state === 'needs_review').map(badge => badge.label)
    if (reviewItems.length) badges.splice(Math.min(1, badges.length), 0, {
        kind: 'review', label: '확인 필요', detail: reviewItems.join(', '), state: 'needs_review',
    })
    return badges
}
