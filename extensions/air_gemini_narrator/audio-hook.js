// Observe only media played while an explicit AIR job is armed. No cookies,
// authorization headers, private RPCs, or other response bodies are collected.
(() => {
  const nativePlay = HTMLMediaElement.prototype.play;
  const nativeFetch = window.fetch.bind(window);
  let armed = null;
  const MAX_BYTES = 32 * 1024 * 1024;
  const send = (id, type, payload = {}) => window.postMessage({channel: 'air-narrator-audio', id, type, ...payload}, location.origin);
  window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.channel !== 'air-narrator-control') return;
    const {type, id} = event.data;
    if (type === 'arm' && typeof id === 'string') armed = {id, claimed: false};
    if (type === 'disarm' && armed?.id === id) armed = null;
  });
  HTMLMediaElement.prototype.play = function (...args) {
    const job = armed;
    if (job && !job.claimed && this instanceof HTMLAudioElement) {
      job.claimed = true;
      const media = this;
      // Buffer the Blob before Gemini revokes its URL, but publish only after
      // playback ends. A changed source/chunked stream is rejected explicitly.
      const source = media.currentSrc || media.src;
      const pending = (async () => {
        if (!source.startsWith('blob:')) throw new Error('이 재생 경로는 단일 오디오 Blob이 아닙니다. 스트림 지원이 필요합니다.');
        const response = await nativeFetch(source);
        if (!response.ok) throw new Error('오디오 Blob 읽기 실패');
        const blob = await response.blob();
        if (!blob.size || blob.size > MAX_BYTES) throw new Error('오디오 크기가 허용 범위를 벗어났습니다.');
        return blob;
      })();
      // Attach an immediate rejection handler to prevent unhandled rejections.
      const result = pending.then(blob => ({blob}), error => ({error}));
      const finish = async () => {
        if (armed !== job) return;
        try {
          const {blob, error} = await result;
          if (error) throw error;
          if ((media.currentSrc || media.src) !== source) throw new Error('음성이 여러 소스로 나뉘어 재생됐습니다. 전체 파일 검증이 필요합니다.');
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error('오디오 변환 실패'));
            reader.readAsDataURL(blob);
          });
          send(job.id, 'audio', {dataUrl, bytes: blob.size});
        } catch (error) { send(job.id, 'error', {message: error.message}); }
      };
      media.addEventListener('ended', finish, {once: true});
      media.addEventListener('error', () => send(job.id, 'error', {message: 'Gemini 음성 재생 오류'}), {once: true});
      result.then(({error}) => { if (error && armed === job) send(job.id, 'error', {message: error.message}); });
    }
    return Reflect.apply(nativePlay, this, args);
  };
})();
