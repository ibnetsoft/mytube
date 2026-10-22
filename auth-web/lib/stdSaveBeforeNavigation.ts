/** One navigation at a time. Recheck edits made while the save was in flight. */
export function createSaveBeforeNavigationGuard(options: {
    needsSave: () => boolean;
    save: () => Promise<boolean | void>;
    onError: (error: unknown) => void;
    onBusy?: (busy: boolean) => void;
}) {
    let busy = false
    return async (navigate: () => void | Promise<void>): Promise<boolean> => {
        if (busy) return false
        busy = true
        try {
            options.onBusy?.(options.needsSave())
            for (let attempt = 0; options.needsSave(); attempt++) {
                if (attempt >= 5) throw new Error('저장 중 변경사항이 추가되었습니다. 저장 완료 후 다시 이동해 주세요.')
                if (await options.save() === false) throw new Error('변경사항을 저장하지 못해 이동하지 않았습니다.')
            }
            await navigate()
            return true
        } catch (error) {
            options.onError(error)
            return false
        } finally { busy = false; options.onBusy?.(false) }
    }
}
