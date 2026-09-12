// Local download only. Worker auto-import can consume this dedicated directory.
// Success means Chrome completed the download, not merely accepted the request.
chrome.action.onClicked.addListener(tab => {
  if (tab.id && tab.url?.startsWith('https://gemini.google.com/')) {
    chrome.tabs.sendMessage(tab.id, {type: 'air-show'}).catch(() => {});
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !sender.tab?.url?.startsWith('https://gemini.google.com/')) return;
  if (message.type !== 'air-save') return;
  (async () => {
    const {dataUrl, id} = message;
    if (!/^[a-f0-9-]{36}$/.test(id || '') || typeof dataUrl !== 'string' || dataUrl.length > 45000000) throw new Error('잘못된 저장 요청');
    const match = /^data:(audio\/[a-z0-9.+-]+)(?:;[^,]*)?;base64,/i.exec(dataUrl);
    const formats = {'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/ogg': 'ogg', 'audio/webm': 'webm', 'audio/mp4': 'm4a'};
    const ext = formats[match?.[1]?.toLowerCase()];
    if (!ext) throw new Error('지원되지 않거나 식별할 수 없는 오디오 형식');
    const downloadId = await chrome.downloads.download({url: dataUrl, filename: `AIR-Narration/${id}.${ext}`, conflictAction: 'uniquify', saveAs: false});
    await chrome.storage.local.set({[`download-${downloadId}`]: {jobId: id, state: 'saving'}});
    // Small data-URL downloads can finish before the storage mapping exists.
    const [item] = await chrome.downloads.search({id: downloadId});
    if (item && ['complete', 'interrupted'].includes(item.state)) {
      await chrome.storage.local.set({[`download-${downloadId}`]: {jobId: id, state: item.state}});
    }
    return {ok: true, downloadId};
  })().then(respond, error => respond({ok: false, error: error.message}));
  return true;
});
chrome.downloads.onChanged.addListener(async delta => {
  if (!['complete', 'interrupted'].includes(delta.state?.current)) return;
  const key = `download-${delta.id}`;
  const state = (await chrome.storage.local.get(key))[key];
  if (!state) return;
  await chrome.storage.local.set({[key]: {...state, state: delta.state.current}});
});
