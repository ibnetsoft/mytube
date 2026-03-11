import os
import re

html_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\webtoon_studio.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Remove redundant tab buttons
pattern_btns = r'<div class="w-4 h-px bg-gray-100 dark:bg-gray-700 mx-1"></div>\s*<button id="tab-btn-plan".*?Video Builder\n?\s*</button>'
html = re.sub(pattern_btns, '', html, flags=re.DOTALL)

# 2. Enable tab-btn-analysis
html = html.replace('id="tab-btn-analysis" onclick="switchWebtoonTab(\'analysis\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"\n                    disabled>', 'id="tab-btn-analysis" onclick="switchWebtoonTab(\'analysis\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">')

# 3. Replace from <!-- Step 2: Confirmation & Generation --> to <!-- Image Optimization Result Modal -->
pattern_body = r'<!-- Step 2: Confirmation & Generation -->.*?<!-- Image Optimization Result Modal -->'
new_body = r"""
                    <!-- [NEW] GENERATION UI IN TAB 2 -->
                    <div id="vb-result" class="space-y-8 mt-12 border-t border-purple-100 dark:border-purple-900/30 pt-8" style="display:none;">
                        <div class="flex items-center justify-between mb-4">
                            <h3 class="text-xl font-black text-gray-800 dark:text-white flex items-center gap-2">
                                <span class="text-purple-500">🎬</span> 연출안 확정 및 영상 자동 생성
                            </h3>
                        </div>
                        <!-- Action Buttons -->
                        <div class="flex flex-col md:flex-row items-center gap-4">
                            <div class="flex items-center gap-2">
                                <label for="vb-scene-range" class="text-sm font-bold text-gray-600 dark:text-gray-300">생성 범위:</label>
                                <input type="text" id="vb-scene-range" value="ALL" placeholder="ALL 또는 1-3"
                                    class="w-32 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm font-bold text-center text-rose-600 dark:text-rose-400 outline-none uppercase tracking-wider">
                            </div>
                            <button onclick="approveAndGenerate()"
                                class="flex-1 w-full md:w-auto btn-primary py-4 rounded-xl bg-gradient-to-r from-rose-500 to-purple-600 shadow-lg shadow-rose-500/30 font-black text-white hover:scale-[1.02] transition-transform flex items-center justify-center gap-2 text-lg">
                                <span>✨</span> 모든 씬 기획 확정 및 영상 생성
                            </button>
                        </div>
                        <div id="vb-generation-box" class="mt-8"></div>
                    </div>

                </div>

            </div> <!-- End Analysis Result Container -->
        </div> <!-- End Tab 2 -->

        <!-- Image Optimization Result Modal -->"""
html = re.sub(pattern_body, lambda m: new_body, html, flags=re.DOTALL)

# 4. We want `vb-result` to show up when scenes are rendered. We will modify `renderScenes()`:
html = html.replace("document.getElementById('analysis-result-container').classList.remove('hidden');", "document.getElementById('analysis-result-container').classList.remove('hidden');\n    document.getElementById('vb-result').style.display = 'block';")

# 5. Inject approveAndGenerate() script.
new_script = r"""
            function approveAndGenerate() {
                if (!analyzedScenes || analyzedScenes.length === 0) return;

                // Collect edited prompts from scene cards
                const updatedScenes = analyzedScenes.map((scene, idx) => {
                    const motionInput = document.querySelector(`#scene-${idx}-motion-desc`);
                    return {
                        scene_id: scene.scene_id || scene.scene_number || (idx + 1),
                        image_path: scene.original_image_path || scene.image_path,
                        motion_prompt: motionInput ? motionInput.value : (scene.motion_desc || "Cinematic camera angle"),
                    };
                });

                // 선택된 씬 범위인지 파악
                const sceneRangeStr = document.getElementById('vb-scene-range').value.trim();
                let filteredScenes = updatedScenes;

                if (sceneRangeStr && sceneRangeStr.toUpperCase() !== 'ALL') {
                    // "1-3" 또는 "3" 파싱
                    const matchRange = sceneRangeStr.match(/^(\d+)\s*-\s*(\d+)$/);
                    const matchSingle = sceneRangeStr.match(/^(\d+)$/);

                    if (matchRange) {
                        const start = parseInt(matchRange[1]);
                        const end = parseInt(matchRange[2]);
                        filteredScenes = updatedScenes.filter(s => {
                            const sid = s.scene_id;
                            return sid >= start && sid <= end;
                        });
                        console.log(`[VB] Scene range subset: ${start} ~ ${end}, count: ${filteredScenes.length}`);
                    } else if (matchSingle) {
                        const target = parseInt(matchSingle[1]);
                        filteredScenes = updatedScenes.filter(s => {
                            const sid = s.scene_id;
                            return sid === target;
                        });
                        console.log(`[VB] Scene single subset: ${target}, count: ${filteredScenes.length}`);
                    } else {
                        alert('잘못된 범위 형식입니다. ALL, 1-3, 또는 5 와 같이 입력해주세요.');
                        return;
                    }
                }

                if (filteredScenes.length === 0) {
                    alert('선택된 범위에 해당하는 씬이 없습니다.');
                    return;
                }

                // 진행 UI 표시
                const vbBox = document.getElementById('vb-generation-box');
                vbBox.innerHTML = `
                    <div class="flex items-center gap-3 mb-4">
                        <span class="w-6 h-6 rounded-lg bg-blue-500 text-white flex items-center justify-center text-xs animate-pulse">▶</span>
                        <h4 class="font-black text-gray-800 dark:text-white text-sm">영상 생성 진행 중</h4>
                    </div>
                    <div id="vb-gen-status" class="text-sm text-gray-600 dark:text-gray-400 mb-3">시작 중...</div>
                    <div class="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-3 mb-4 overflow-hidden">
                        <div id="vb-gen-progress" class="bg-gradient-to-r from-rose-500 to-purple-600 h-3 rounded-full transition-all duration-500" style="width:0%"></div>
                    </div>
                    <div id="vb-gen-log" class="space-y-1 max-h-48 overflow-y-auto text-xs font-mono text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 rounded-xl p-3 border border-gray-100 dark:border-gray-700"></div>
                    <div id="vb-gen-result" class="hidden mt-4"></div>
                `;

                // SSE 스트리밍 영상 생성 시작
                const body = {
                    scenes: filteredScenes,
                    project_id: currentProjectId || null,
                };

                fetch('/webtoon/video-builder/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                }).then(resp => {
                    if (!resp.ok) {
                        resp.json().then(d => {
                            document.getElementById('vb-gen-status').textContent = '❌ ' + (d.detail || '서버 오류');
                            Utils.showToast('❌ 영상 생성 실패', 'error');
                        });
                        return;
                    }
                    const reader = resp.body.getReader();
                    const decoder = new TextDecoder();

                    function read() {
                        reader.read().then(({ done, value }) => {
                            if (done) return;
                            const text = decoder.decode(value);
                            // SSE 파싱
                            text.split('\n').forEach(line => {
                                if (!line.startsWith('data: ')) return;
                                try {
                                    const ev = JSON.parse(line.slice(6));
                                    _vbHandleSSEEvent(ev, filteredScenes.length);
                                } catch (e) { }
                            });
                            read();
                        }).catch(err => {
                            console.error('[VB SSE] error:', err);
                        });
                    }
                    read();
                }).catch(err => {
                    document.getElementById('vb-gen-status').textContent = '❌ 연결 오류: ' + err.message;
                    Utils.showToast('❌ ' + err.message, 'error');
                });
            }

            function vbApproveAndGenerate() {
"""
pattern_func = r'function vbApproveAndGenerate\(\)\s*\{.*?(?=// --- Image Edit Logic ---)'
html = re.sub(pattern_func, lambda m: new_script, html, flags=re.DOTALL)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("done")
