export type TopicSubmission = {
    title: string; youtube_url: string; story: string; character_notes: string;
    requirements: string; category: string; duration_minutes: number;
    language: string; setting_country: string; era_region: string; image_style: string;
    production_mode: string; ae_scene_delivery: 'local' | 'gcs'; transcript: string;
    character_images: { name: string; data: string }[];
}

export function validateTopicSubmission(input: any): TopicSubmission {
    if (!input || typeof input !== 'object') throw new Error('입력 내용을 확인하세요.')
    const text = (key: string, max: number, required = false) => {
        if (input[key] != null && typeof input[key] !== 'string') throw new Error(`${key}: 문자열을 입력하세요.`)
        const value = (input[key] || '').trim()
        if ((required && !value) || value.length > max) throw new Error(`${key}: 필수 입력 및 최대 ${max}자를 확인하세요.`)
        return value
    }
    const youtube_url = text('youtube_url', 2048)
    if (youtube_url) {
        let valid = false
        try {
            const u = new URL(youtube_url)
            const parts = u.pathname.split('/').filter(Boolean)
            const id = u.hostname === 'youtu.be' && parts.length === 1 ? parts[0]
                : ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'].includes(u.hostname)
                    ? (u.pathname === '/watch' ? u.searchParams.get('v') : parts.length === 2 && ['shorts', 'embed', 'live'].includes(parts[0]) ? parts[1] : '') : ''
            valid = ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password && !u.port && /^[\w-]{11}$/.test(id || '')
        } catch { /* Invalid URL */ }
        if (!valid) throw new Error('올바른 YouTube 영상 URL을 입력하세요.')
    }
    const duration_minutes = Number(input.duration_minutes)
    if (!Number.isInteger(duration_minutes) || duration_minutes < 1 || duration_minutes > 60) throw new Error('분량은 1~60분입니다.')
    const language = text('language', 2, true)
    if (!['ko', 'en', 'ja', 'es'].includes(language)) throw new Error('대본 언어를 선택하세요.')
    const production_mode = text('production_mode', 20, true)
    if (!['standard', 'moving_comic'].includes(production_mode)) throw new Error('제작 모드를 선택하세요.')
    const ae_scene_delivery = input.ae_scene_delivery == null ? 'local' : text('ae_scene_delivery', 5, true)
    if (ae_scene_delivery !== 'local' && ae_scene_delivery !== 'gcs') throw new Error('AE 씬 영상 전달 방식을 선택하세요.')
    const images = input.character_images || []
    if (!Array.isArray(images) || images.length > 3) throw new Error('이미지는 최대 3장입니다.')
    const character_images = images.map((image: any) => {
        if (typeof image?.name !== 'string' || !image.name.trim() || image.name.length > 120 || typeof image?.data !== 'string') throw new Error('캐릭터 이미지 정보를 확인하세요.')
        const match = /^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$/.exec(image.data)
        if (!match || image.data.length > 700000) throw new Error('이미지는 PNG/JPEG/WebP, 장당 500KB 이하로 등록하세요.')
        const bytes = Buffer.from(match[2], 'base64')
        const signature = match[1] === 'png' ? bytes.subarray(0, 8).toString('hex') === '89504e470d0a1a0a'
            : match[1] === 'jpeg' ? bytes.subarray(0, 3).toString('hex') === 'ffd8ff'
                : bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP'
        if (!signature || bytes.length > 512000) throw new Error('이미지 형식 또는 크기가 올바르지 않습니다.')
        return { name: image.name.trim(), data: image.data }
    })
    return { title: text('title', 200, true), youtube_url, story: text('story', 2500, true),
        character_notes: text('character_notes', 1500), requirements: text('requirements', 1000),
        category: text('category', 80, true), duration_minutes, language, production_mode, ae_scene_delivery,
        setting_country: text('setting_country', 80, true), era_region: text('era_region', 120, true),
        image_style: text('image_style', 80, true), transcript: text('transcript', 40000), character_images }
}
