/** Check errors before starting a browser download, and retain the server's actual format. */
export async function downloadStdFile(url: string, headers: Record<string, string>, fallbackName: string, expectedType: 'image' | 'zip') {
    const response = await fetch(url, { headers })
    if (!response.ok) {
        const error = await response.json().catch(() => null)
        throw new Error(error?.error || `Download failed (${response.status})`)
    }
    const contentType = (response.headers.get('content-type') || '').split(';')[0].trim()
    if (expectedType === 'image' ? !contentType.startsWith('image/') : contentType !== 'application/zip') {
        throw new Error('Invalid download response')
    }
    const blob = await response.blob()
    if (!blob.size) throw new Error('Empty download response')
    const filename = response.headers.get('content-disposition')?.match(/filename="([^"]+)"/i)?.[1] || fallbackName
    const blobUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename.replace(/[\\/:*?"<>|]+/g, '-')
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(blobUrl), 30_000)
}
