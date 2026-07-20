// [AIR-0228] Real magic-byte MIME sniffing - existing upload endpoints in this
// repo (app/routers/settings.py's custom style/thumbnail uploads) only check
// file extension/name, never actual content (see
// docs/CHATGPT_PLUS_VERIFICATION_SPEC.md §1.1). This feature deliberately does
// not repeat that pattern, since evidence-of-payment uploads are exactly the
// kind of input worth being strict about.

export type SniffResult = { mimeType: string; ext: string } | null

export function sniffImageOrPdf(buffer: Buffer): SniffResult {
    if (buffer.length >= 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
        return { mimeType: 'image/jpeg', ext: 'jpg' }
    }
    if (
        buffer.length >= 8 &&
        buffer[0] === 0x89 && buffer[1] === 0x50 && buffer[2] === 0x4e && buffer[3] === 0x47 &&
        buffer[4] === 0x0d && buffer[5] === 0x0a && buffer[6] === 0x1a && buffer[7] === 0x0a
    ) {
        return { mimeType: 'image/png', ext: 'png' }
    }
    if (
        buffer.length >= 12 &&
        buffer.slice(0, 4).toString('ascii') === 'RIFF' &&
        buffer.slice(8, 12).toString('ascii') === 'WEBP'
    ) {
        return { mimeType: 'image/webp', ext: 'webp' }
    }
    if (buffer.length >= 5 && buffer.slice(0, 5).toString('ascii') === '%PDF-') {
        return { mimeType: 'application/pdf', ext: 'pdf' }
    }
    return null
}

export const MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024 // 15MB
