/** Crops are tied to the exact image hash, never to a character name or slot. */
type FaceCrop = readonly [number, number, number, number]
const VERIFIED_FACE_CROPS: Record<string, FaceCrop> = {
    'ea44a9ec300cb26798a086e35f68401f7b46a2533473db83d470c1a2274e8217': [405/1536, 10/1024, 350/1536, 350/1024],
    '7f9a3a2be355a1d897a9dfe0cf957074ce021b86bff6f67ee923c002cf2a4dcf': [405/1536, 10/1024, 350/1536, 350/1024],
    '2242bd13af1f9e44ff4c5080f7652df24b2e87d1e9b4ed64c6423a5d74b256a9': [1170/1536, 0/1024, 350/1536, 350/1024],
    '589a9dd8ca3952ac93d82059414d1273ec08a5efb75ffda607e7cc5e0fdbfc49': [365/1536, 10/1024, 350/1536, 350/1024],
    'a6e7d0050d3bd9b2ff4609695e5c38703c2db32be84e5cd492fa28f5fb8ef6b1': [365/1536, 10/1024, 350/1536, 350/1024],
    '623d25a693b3ef744ab4f110ff176b9cab5a8cf9fa7fa90701dc7b3e8eb7e908': [855/1536, 15/1024, 350/1536, 350/1024],
    '8538934db3684d91de793fcdbefbebf2685ac6b0776467a033455f5ef6aa0d9c': [1080/1536, 10/1024, 360/1536, 360/1024],
    '6befe28d3bdc36430b724f4659180818b8fe2bf32988b32a00ac4786a6753f94': [930/1536, 5/1024, 350/1536, 350/1024],
    '54999dd12a88cfd5aa2eadceaa63a3a33206c0bdb993c0621baff728b4596a71': [470/1536, 10/1024, 350/1536, 350/1024],
    '25c020d0fb23204c55e5060a31b77035e80b77e6c683b57f68bf9f2c6cd83bc4': [1040/1536, 5/1024, 360/1536, 360/1024],
    'abf3eb7df382c18a9eac245b4cab93bf650d782c8a2aa910fd4b060b6baa4be7': [840/1536, 5/1024, 360/1536, 360/1024],
    'e3a34109800068f3de1f7f0f06c577d0e2f0c41dd70946680ae1c10e52897b41': [1060/1536, 0/1024, 360/1536, 360/1024],
    'b58a698b3c65c44b20602b35396889880392d4f497e27e7151c1d99a63dcdf31': [1080/1536, 5/1024, 360/1536, 360/1024],
}

/** Return positioning only for a verified crop of this exact saved reference. */
export function speakerPortraitStyle(character: any): Record<string, string> | undefined {
    const hash = String(character?.thumbnail_draft_metadata?.sha256 || '').toLowerCase()
    const box = VERIFIED_FACE_CROPS[hash]
    if (!box) return undefined
    const [x, y, w, h] = box
    return { position: 'absolute', left: `${-x / w * 100}%`, top: `${-y / h * 100}%`,
        width: `${100 / w}%`, height: `${100 / h}%`, maxWidth: 'none', objectFit: 'fill' }
}

// Browsers that provide native face detection can also crop references not in
// the reviewed registry. Never guess a crop when detection is unavailable.
const detectedFaces = new Map<string, Promise<FaceCrop | null>>()
export function detectSpeakerPortrait(image: HTMLImageElement, character: any): void {
    if (speakerPortraitStyle(character) || typeof window === 'undefined') return
    const Detector = (window as any).FaceDetector
    if (typeof Detector !== 'function' || !image.naturalWidth || !image.naturalHeight) return
    const src = image.currentSrc || image.src
    let pending = detectedFaces.get(src)
    if (!pending) {
        const width = image.naturalWidth, height = image.naturalHeight
        pending = Promise.resolve().then(() => new Detector({ fastMode: true, maxDetectedFaces: 12 }).detect(image))
            .then((faces: any[]) => {
                const face = faces.filter(item => item?.boundingBox?.width > 0 && item?.boundingBox?.height > 0)
                    .sort((a, b) => b.boundingBox.width * b.boundingBox.height - a.boundingBox.width * a.boundingBox.height)[0]?.boundingBox
                if (!face) return null
                const size = Math.min(Math.max(face.width, face.height) * 1.5, width, height)
                const x = Math.max(0, Math.min(width - size, face.x + face.width / 2 - size / 2))
                const y = Math.max(0, Math.min(height - size, face.y + face.height / 2 - size / 2))
                return [x / width, y / height, size / width, size / height] as FaceCrop
            }).catch(() => null)
        if (detectedFaces.size >= 128) detectedFaces.clear()
        detectedFaces.set(src, pending)
    }
    void pending.then(box => {
        if (!box || !image.isConnected || (image.currentSrc || image.src) !== src) return
        const [x, y, w, h] = box
        Object.assign(image.style, { position: 'absolute', left: `${-x / w * 100}%`, top: `${-y / h * 100}%`,
            width: `${100 / w}%`, height: `${100 / h}%`, maxWidth: 'none', objectFit: 'fill' })
    })
}
