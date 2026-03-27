async function distributeImages() {
    if (!confirm('AI가 자막 내용을 분석하여 이미지를 자동으로 배치합니다.\n기존 이미지 배치는 덮어씌워집니다. 진행하시겠습니까?')) return;

    Utils.setLoading(true, "AI가 이미지 싱크를 맞추는 중입니다...");

    try {
        const res = await fetch('/api/subtitle/auto_sync_images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId })
        });
        const data = await res.json();

        if (data.status === 'ok') {
            images = data.timeline_images;
            imageTimings = data.image_timings;

            renderSubtitles();
            renderImageStrip(); // Update badge usage
            Utils.showToast(data.message, 'success');
        } else {
            throw new Error(data.error);
        }
    } catch (e) {
        console.error(e);
        Utils.showToast("이미지 싱크 실패: " + e.message, 'error');
    } finally {
        Utils.setLoading(false);
    }
}
