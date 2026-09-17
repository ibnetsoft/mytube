// Keep encoded audio frames; discard per-file tags/seek headers whose duration
// describes just one clip. Embedded ID3 headers otherwise cause decode errors.
export function joinMp3Segments(clips: Buffer[]): Buffer {
    return Buffer.concat(clips.map(clip => {
        let start = 0, end = clip.length
        while (clip.toString('ascii', start, start + 3) === 'ID3' && start + 10 <= end) {
            const size = ((clip[start + 6] & 127) << 21) | ((clip[start + 7] & 127) << 14)
                | ((clip[start + 8] & 127) << 7) | (clip[start + 9] & 127)
            const footer = clip[start + 3] === 4 && (clip[start + 5] & 16) ? 10 : 0
            start += 10 + size + footer
        }
        if (end - start >= 128 && clip.toString('ascii', end - 128, end - 125) === 'TAG') end -= 128
        if (start + 4 <= end && clip[start] === 255 && (clip[start + 1] & 224) === 224) {
            const version = (clip[start + 1] >> 3) & 3
            const layer = (clip[start + 1] >> 1) & 3
            const rateIndex = (clip[start + 2] >> 2) & 3
            const bitrateIndex = clip[start + 2] >> 4
            if (version !== 1 && layer === 1 && rateIndex < 3 && bitrateIndex > 0 && bitrateIndex < 15) {
                const rates = version === 3 ? [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320] : [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160]
                const sampleRate = [44100,48000,32000][rateIndex] / (version === 3 ? 1 : version === 2 ? 2 : 4)
                const frameLength = Math.floor((version === 3 ? 144 : 72) * rates[bitrateIndex] * 1000 / sampleRate) + ((clip[start + 2] >> 1) & 1)
                const mono = (clip[start + 3] >> 6) === 3
                const sideInfo = version === 3 ? (mono ? 17 : 32) : (mono ? 9 : 17)
                const crc = (clip[start + 1] & 1) ? 0 : 2
                const tag = clip.toString('ascii', start + 4 + crc + sideInfo, start + 8 + crc + sideInfo)
                const vbri = clip.toString('ascii', start + 36, start + 40)
                if (start + frameLength <= end && (tag === 'Xing' || tag === 'Info' || vbri === 'VBRI')) start += frameLength
            }
        }
        if (start >= end) throw new Error('합칠 음성 데이터가 비어 있습니다.')
        return clip.subarray(start, end)
    }))
}
