const DB_NAME = 'air-studio-std-local-media'
const DB_VERSION = 1
const HANDLE_STORE = 'directory-handles'
const ASSET_STORE = 'project-assets'
const ROOT_HANDLE_ID = 'std-media-root'

type DirectoryPermissionState = 'granted' | 'denied' | 'prompt'
type LocalDirectoryStatus = 'unsupported' | 'not_selected' | 'permission_needed' | 'connected'

type LocalAssetRecord = {
    key: string
    projectId: string
    sceneNumber: number | null
    assetType: string
    relativePath: string[]
    fileName: string
    mimeType: string
    size: number
    savedAt: string
}

export type StdLocalDirectoryState = {
    status: LocalDirectoryStatus
    folderName: string
}

export type RestoredStdLocalMedia = {
    key: string
    sceneNumber: number | null
    assetType: string
    relativePath: string
    fileName: string
    objectUrl: string
}

function supportsLocalDirectoryAccess(): boolean {
    return typeof window !== 'undefined'
        && typeof indexedDB !== 'undefined'
        && typeof (window as any).showDirectoryPicker === 'function'
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error || new Error('IndexedDB request failed'))
    })
}

function openLocalMediaDb(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION)
        request.onupgradeneeded = () => {
            const db = request.result
            if (!db.objectStoreNames.contains(HANDLE_STORE)) {
                db.createObjectStore(HANDLE_STORE, { keyPath: 'id' })
            }
            if (!db.objectStoreNames.contains(ASSET_STORE)) {
                const store = db.createObjectStore(ASSET_STORE, { keyPath: 'key' })
                store.createIndex('projectId', 'projectId', { unique: false })
            }
        }
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error || new Error('Local media database could not be opened'))
    })
}

async function getRootHandle(): Promise<any | null> {
    const db = await openLocalMediaDb()
    try {
        const transaction = db.transaction(HANDLE_STORE, 'readonly')
        const row = await requestResult<any>(transaction.objectStore(HANDLE_STORE).get(ROOT_HANDLE_ID))
        return row?.handle || null
    } finally {
        db.close()
    }
}

async function saveRootHandle(handle: any): Promise<void> {
    const db = await openLocalMediaDb()
    try {
        const transaction = db.transaction(HANDLE_STORE, 'readwrite')
        await requestResult(transaction.objectStore(HANDLE_STORE).put({ id: ROOT_HANDLE_ID, handle }))
    } finally {
        db.close()
    }
}

async function queryPermission(handle: any, requestAccess: boolean): Promise<DirectoryPermissionState> {
    let state = await handle.queryPermission({ mode: 'readwrite' }) as DirectoryPermissionState
    if (state === 'prompt' && requestAccess) {
        state = await handle.requestPermission({ mode: 'readwrite' }) as DirectoryPermissionState
    }
    return state
}

export async function getStdLocalDirectoryState(): Promise<StdLocalDirectoryState> {
    if (!supportsLocalDirectoryAccess()) return { status: 'unsupported', folderName: '' }
    const handle = await getRootHandle()
    if (!handle) return { status: 'not_selected', folderName: '' }
    const permission = await queryPermission(handle, false)
    return {
        status: permission === 'granted' ? 'connected' : 'permission_needed',
        folderName: String(handle.name || ''),
    }
}

export async function selectStdLocalDirectory(): Promise<StdLocalDirectoryState> {
    if (!supportsLocalDirectoryAccess()) {
        throw new Error('이 브라우저는 로컬 폴더 저장을 지원하지 않습니다. 최신 Chrome 또는 Edge를 사용해주세요.')
    }
    const handle = await (window as any).showDirectoryPicker({
        id: 'air-studio-std-media',
        mode: 'readwrite',
    })
    await saveRootHandle(handle)
    return { status: 'connected', folderName: String(handle.name || '') }
}

async function writableRootHandle(promptForAccess: boolean): Promise<any> {
    let handle = await getRootHandle()
    if (!handle && promptForAccess) {
        await selectStdLocalDirectory()
        handle = await getRootHandle()
    }
    if (!handle) throw new Error('먼저 로컬 저장 폴더를 선택해주세요.')

    const permission = await queryPermission(handle, promptForAccess)
    if (permission !== 'granted') {
        throw new Error('로컬 저장 폴더 권한이 필요합니다. 폴더 연결 버튼을 눌러 다시 허용해주세요.')
    }
    return handle
}

function safePathSegment(value: string, fallback: string): string {
    const normalized = String(value || '')
        .trim()
        .replace(/[<>:"/\\|?*\u0000-\u001f]+/g, '_')
        .replace(/[. ]+$/g, '')
        .slice(0, 100)
    return normalized || fallback
}

function localAssetKey(projectId: string, sceneNumber: number | null, assetType: string): string {
    return `${projectId}:${sceneNumber == null ? 'project' : sceneNumber}:${assetType}`
}

async function writeAssetRecord(record: LocalAssetRecord): Promise<void> {
    const db = await openLocalMediaDb()
    try {
        const transaction = db.transaction(ASSET_STORE, 'readwrite')
        await requestResult(transaction.objectStore(ASSET_STORE).put(record))
    } finally {
        db.close()
    }
}

async function readProjectAssetRecords(projectId: string): Promise<LocalAssetRecord[]> {
    const db = await openLocalMediaDb()
    try {
        const transaction = db.transaction(ASSET_STORE, 'readonly')
        const index = transaction.objectStore(ASSET_STORE).index('projectId')
        return await requestResult<LocalAssetRecord[]>(index.getAll(projectId))
    } finally {
        db.close()
    }
}

async function getOrCreateDirectory(root: any, segments: string[]): Promise<any> {
    let directory = root
    for (const segment of segments) {
        directory = await directory.getDirectoryHandle(segment, { create: true })
    }
    return directory
}

async function readFileAtPath(root: any, relativePath: string[]): Promise<File> {
    if (relativePath.length < 2) throw new Error('Invalid local media path')
    let directory = root
    for (const segment of relativePath.slice(0, -1)) {
        directory = await directory.getDirectoryHandle(segment)
    }
    const fileHandle = await directory.getFileHandle(relativePath[relativePath.length - 1])
    return await fileHandle.getFile()
}

export async function saveStdLocalMediaFile(input: {
    projectId: string
    projectTitle: string
    sceneNumber: number | null
    assetType: 'image' | 'video' | 'thumbnail'
    file: File
}): Promise<{ relativePath: string; folderName: string }> {
    const root = await writableRootHandle(true)
    const projectName = safePathSegment(input.projectTitle, 'project')
    const projectSuffix = safePathSegment(input.projectId, 'id').slice(0, 8)
    const projectFolder = `${projectName}_${projectSuffix}`
    const sceneFolder = input.sceneNumber == null
        ? 'project-assets'
        : `scene-${String(Math.max(1, Math.floor(input.sceneNumber))).padStart(3, '0')}`
    const extensionIndex = input.file.name.lastIndexOf('.')
    const extension = extensionIndex > -1 ? input.file.name.slice(extensionIndex).toLowerCase().slice(0, 12) : ''
    const storedFileName = safePathSegment(`${input.assetType}${extension}`, input.assetType)
    const directorySegments = ['AIRStudio-STD', projectFolder, sceneFolder]
    const directory = await getOrCreateDirectory(root, directorySegments)
    const fileHandle = await directory.getFileHandle(storedFileName, { create: true })
    const writable = await fileHandle.createWritable()
    try {
        await writable.write(input.file)
        await writable.close()
    } catch (error) {
        await writable.abort().catch(() => undefined)
        throw error
    }

    const relativePath = [...directorySegments, storedFileName]
    await writeAssetRecord({
        key: localAssetKey(input.projectId, input.sceneNumber, input.assetType),
        projectId: input.projectId,
        sceneNumber: input.sceneNumber,
        assetType: input.assetType,
        relativePath,
        fileName: input.file.name,
        mimeType: input.file.type,
        size: input.file.size,
        savedAt: new Date().toISOString(),
    })

    return {
        relativePath: relativePath.join('/'),
        folderName: String(root.name || ''),
    }
}

export async function restoreStdLocalProjectMedia(
    projectId: string,
    assets: any[]
): Promise<{
    state: StdLocalDirectoryState
    entries: RestoredStdLocalMedia[]
}> {
    const state = await getStdLocalDirectoryState()
    if (state.status !== 'connected') return { state, entries: [] }

    const root = await writableRootHandle(false)
    const savedRecords = await readProjectAssetRecords(projectId)
    const candidates = new Map<string, LocalAssetRecord>()
    for (const record of savedRecords) candidates.set(record.key, record)

    for (const asset of Array.isArray(assets) ? assets : []) {
        const assetType = String(asset?.asset_type || '').toLowerCase()
        if (!['image', 'video', 'thumbnail'].includes(assetType)) continue
        const sceneValue = asset?.scene_number == null ? null : Number(asset.scene_number)
        const sceneNumber = Number.isFinite(sceneValue) ? sceneValue : null
        const key = localAssetKey(projectId, sceneNumber, assetType)
        if (candidates.has(key)) continue
        const relativePathValue = String(asset?.metadata?.local_relative_path || '').trim()
        if (!relativePathValue) continue
        const relativePath = relativePathValue.split('/').filter(Boolean)
        candidates.set(key, {
            key,
            projectId,
            sceneNumber,
            assetType,
            relativePath,
            fileName: String(asset?.file_name || relativePath[relativePath.length - 1] || 'asset'),
            mimeType: String(asset?.mime_type || ''),
            size: Number(asset?.file_size || 0),
            savedAt: String(asset?.created_at || ''),
        })
    }

    const restored = await Promise.all(Array.from(candidates.values()).map(async record => {
        try {
            const file = await readFileAtPath(root, record.relativePath)
            return {
                key: record.key,
                sceneNumber: record.sceneNumber,
                assetType: record.assetType,
                relativePath: record.relativePath.join('/'),
                fileName: record.fileName,
                objectUrl: URL.createObjectURL(file),
            }
        } catch {
            return null
        }
    }))

    return {
        state,
        entries: restored.filter(Boolean) as RestoredStdLocalMedia[],
    }
}
