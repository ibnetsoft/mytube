import os
import re

html_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\webtoon_studio.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# I will recreate the tab buttons first
tab_buttons_old = r"""                <div class="w-4 h-px bg-gray-100 dark:bg-gray-700 mx-1"></div>

                <button id="tab-btn-plan" onclick="switchWebtoonTab('plan')"
                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                    disabled>
                    <span
                        class="w-5 h-5 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-400 flex items-center justify-center text-[10px]">3</span>
                    {{ t('wt_tab_plan') }}
                </button>

                <div class="w-4 h-px bg-gray-100 dark:bg-gray-700 mx-1"></div>

                <button id="tab-btn-produce" onclick="switchWebtoonTab('produce')"
                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                    disabled>
                    <span
                        class="w-5 h-5 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-400 flex items-center justify-center text-[10px]">4</span>
                    {{ t('wt_tab_produce') }}
                </button>

                <div class="w-4 h-px bg-gray-100 dark:bg-gray-700 mx-1"></div>

                <button id="tab-btn-cuts" onclick="switchWebtoonTab('cuts')"
                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <span
                        class="w-5 h-5 rounded-lg bg-emerald-500 text-white flex items-center justify-center text-[10px] shadow-sm shadow-emerald-500/30">✂</span>
                    {{ t('wt_tab_cuts') }}
                </button>

                <div class="w-4 h-px bg-gray-100 dark:bg-gray-700 mx-1"></div>

                <button id="tab-btn-vbuilder" onclick="switchWebtoonTab('vbuilder')"
                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <span
                        class="w-5 h-5 rounded-lg bg-rose-500 text-white flex items-center justify-center text-[10px] shadow-sm shadow-rose-500/30">🎬</span>
                    Video Builder
                </button>"""

# Find where to put them based on tab-btn-analysis
html = re.sub(r'(<button id="tab-btn-analysis".*?)\n\s*</div>\n\s*</div>', lambda m: m.group(1) + '\n' + tab_buttons_old + '\n            </div>\n        </div>', html, flags=re.DOTALL)

# Re-disable tab-btn-analysis to its original state (though user wanted it clickable, wait, the user said "현재 분석 및 분류 탭만 클릭이 안되는 원인을 파악해서 탭클릭하면 페이지 열리게 해줘봐." so they WANT it clickable.)
# So I'll keep it as it is (with `disabled` removed by my previous script).

# I will recreate the missing body part from lines 335 to 849
deleted_body_part_1 = r"""        <!-- Step 2: Confirmation & Generation -->
        <div id="vb-result" class="hidden space-y-8 mt-8 border-t border-gray-100 dark:border-gray-700 pt-8">
            <div class="flex items-center justify-between">
                <h3 class="text-xl font-black text-gray-800 dark:text-white flex items-center gap-2">
                    <span class="text-purple-500">2</span> 감독 연출 노트 및 영상 생성
                </h3>
            </div>

            <!-- Overview Section -->
            <div
                class="bg-indigo-50 dark:bg-indigo-900/20 rounded-2xl p-6 border border-indigo-100 dark:border-indigo-900/50">
                <h4 class="font-bold text-indigo-800 dark:text-indigo-300 mb-2 flex items-center gap-2">
                    <span>🎬</span> 작품 총평 (Director's Note)
                </h4>
                <p id="vb-overview" class="text-indigo-900 dark:text-indigo-100 text-sm leading-relaxed"></p>
                <div class="mt-4 flex flex-wrap gap-4 text-xs">
                    <div
                        class="flex items-center gap-1.5 bg-white dark:bg-indigo-950/50 px-3 py-1.5 rounded-lg text-indigo-600 dark:text-indigo-300">
                        <span class="font-bold">♪ 추천 BGM:</span>
                        <span id="vb-bgm"></span>
                    </div>
                    <div
                        class="flex items-center gap-1.5 bg-white dark:bg-indigo-950/50 px-3 py-1.5 rounded-lg text-indigo-600 dark:text-indigo-300">
                        <span class="font-bold">⏱️ 예상 시간:</span>
                        <span id="vb-duration"></span>
                    </div>
                    <div
                        class="flex items-center gap-1.5 bg-white dark:bg-indigo-950/50 px-3 py-1.5 rounded-lg text-indigo-600 dark:text-indigo-300">
                        <span class="font-bold">🎭 분위기:</span>
                        <span id="vb-mood"></span>
                    </div>
                </div>
            </div>

            <!-- Scene Cards Container -->
            <div id="vb-scene-cards" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <!-- Cards will be injected here -->
            </div>

            <!-- Action Buttons -->
            <div
                class="pt-6 border-t border-gray-100 dark:border-gray-700 flex flex-col md:flex-row items-center gap-4">
                <div class="flex items-center gap-2">
                    <label for="vb-scene-range" class="text-sm font-bold text-gray-600 dark:text-gray-300">생성
                        범위:</label>
                    <input type="text" id="vb-scene-range" value="ALL" placeholder="ALL 또는 1-3"
                        class="w-32 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm font-bold text-center text-rose-600 dark:text-rose-400 outline-none uppercase tracking-wider">
                </div>
                <button onclick="vbApproveAndGenerate()"
                    class="flex-1 w-full md:w-auto btn-primary py-4 rounded-xl bg-gradient-to-r from-rose-500 to-purple-600 shadow-lg shadow-rose-500/30 font-black text-white hover:scale-[1.02] transition-transform flex items-center justify-center gap-2 text-lg">
                    <span>✨</span> 기획안 승인 및 영상 생성 시작
                </button>
            </div>

        </div>
        <!-- TAB 3: Production Plan -->
        <div id="tab-plan" class="tab-content hidden space-y-8">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-xl font-black text-gray-800 dark:text-white">제작 기획서</h3>
                <button onclick="generatePlan(true)"
                    class="px-6 py-2 rounded-xl bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border-2 border-indigo-600 dark:border-indigo-400 shadow-lg shadow-indigo-500/10 font-bold flex items-center gap-2 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-all">
                    🔄 기획서 재생성
                </button>
            </div>

            <div id="production-plan-area" class="mb-8 block">
                <div
                    class="bg-indigo-50 dark:bg-indigo-900/10 border-2 border-indigo-200 dark:border-indigo-800/50 rounded-3xl p-6 shadow-xl">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-3">
                            <span class="text-2xl">📋</span>
                            <div>
                                <h4 class="text-lg font-black text-indigo-800 dark:text-indigo-300">
                                    AI 비디오 제작 기획서</h4>
                                <p class="text-[10px] text-indigo-500 font-bold uppercase tracking-widest">
                                    Production Tech Plan generated by Gemini</p>
                            </div>
                        </div>
                    </div>

                    <div id="plan-content" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <!-- Populated by JS -->
                        <div class="col-span-1 space-y-4">
                            <div
                                class="bg-white dark:bg-gray-800 p-4 rounded-2xl shadow-sm border border-indigo-100 dark:border-indigo-900/30">
                                <h5 class="text-xs font-black text-gray-400 uppercase mb-2">총괄 전략
                                </h5>
                                <p id="plan-strategy"
                                    class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed text-gray-400 italic">
                                    기획서 생성 버튼을 눌러주세요.</p>
                            </div>
                            <div
                                class="bg-white dark:bg-gray-800 p-4 rounded-2xl shadow-sm border border-indigo-100 dark:border-indigo-900/30">
                                <h5 class="text-xs font-black text-gray-400 uppercase mb-2">추천 사운드
                                    (BGM)</h5>
                                <p id="plan-bgm" class="text-sm font-bold text-indigo-600 dark:text-indigo-400">
                                </p>
                            </div>
                        </div>
                        <div
                            class="lg:col-span-2 bg-white dark:bg-gray-800 p-4 rounded-2xl shadow-sm border border-indigo-100 dark:border-indigo-900/30 overflow-x-auto">
                            <h5 class="text-xs font-black text-gray-400 uppercase mb-4">장면별 기술 사양
                                (Scene Specifications)
                            </h5>
                            <table class="w-full text-left text-xs">
                                <thead>
                                    <tr class="border-b border-gray-100 dark:border-gray-700">
                                        <th class="py-2 font-black text-gray-500">SCENE</th>
                                        <th class="py-2 font-black text-gray-500">ENGINE</th>
                                        <th class="py-2 font-black text-gray-500">MOTION</th>
                                        <th class="py-2 font-black text-gray-500">RATIONALE</th>
                                        <th class="py-2 font-black text-gray-500">CROPPING/ADVICE
                                        </th>
                                    </tr>
                                </thead>
                                <tbody id="plan-scene-table">
                                    <!-- Populated by JS -->
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div class="mt-6 flex justify-end gap-3">
                        <button onclick="applyPlanAndClose()"
                            class="px-6 py-2 bg-indigo-600 text-white rounded-xl font-black text-sm shadow-lg shadow-indigo-500/20 hover:scale-105 transition-transform">
                            ✅ 기획서 내용 적용 후 다음 단계로
                        </button>
                    </div>
                </div>
            </div>
        </div> <!-- End Tab 3 -->

        <!-- TAB 4: Automatic Production -->
        <div id="tab-produce" class="tab-content hidden space-y-8">
            <!-- Production Settings & Start -->
            <div id="production-settings-area" class="card bg-white dark:bg-gray-800 p-8">
                <h3 class="text-xl font-black text-gray-800 dark:text-white mb-6">최종 제작 설정</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
                    <!-- Option 1: Lip Sync -->
                    <div
                        class="bg-purple-50 dark:bg-purple-900/10 p-4 rounded-xl border border-purple-100 dark:border-purple-800/30">
                        <label class="relative inline-flex items-center cursor-pointer group w-full justify-between">
                            <span class="text-sm font-bold text-gray-700 dark:text-gray-300 flex flex-col">
                                <span class="flex items-center gap-2">
                                    🎭 AI 립싱크 활성화
                                    <span
                                        class="text-[10px] bg-purple-100 text-purple-600 px-2 py-0.5 rounded-md">PREMIUM</span>
                                </span>
                                <span class="text-xs text-gray-400 font-normal mt-1">캐릭터 입모양을 대사에 맞춰
                                    애니메이션화합니다.</span>
                            </span>
                            <input type="checkbox" id="use-lipsync" class="sr-only peer" checked>
                            <div
                                class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:right-[2px] after:top-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600">
                            </div>
                        </label>
                    </div>

                    <!-- Option 2: Subtitles -->
                    <div
                        class="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-xl border border-blue-100 dark:border-blue-800/30">
                        <label class="relative inline-flex items-center cursor-pointer group w-full justify-between">
                            <span class="text-sm font-bold text-gray-700 dark:text-gray-300 flex flex-col">
                                <span class="flex items-center gap-2">📝 자막 생성 포함</span>
                                <span class="text-xs text-gray-400 font-normal mt-1">대사에 맞는 자막을 영상에
                                    자동으로 입힙니다.</span>
                            </span>
                            <input type="checkbox" id="use-subtitles" class="sr-only peer" checked>
                            <div
                                class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:right-[2px] after:top-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600">
                            </div>
                        </label>
                    </div>
                </div>

                <div class="flex justify-center">
                    <button id="step-3-start-btn" onclick="startAutomation()"
                        class="px-12 py-4 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 shadow-xl shadow-purple-500/30 font-black text-xl text-white hover:scale-105 transition-transform flex items-center gap-3">
                        <span>🎬</span>
                        <span>오토파일럿 제작 시작 (Start Automation)</span>
                    </button>
                </div>
            </div>

            <div id="step-3-area" class="hidden">
                <div class="card bg-white dark:bg-gray-800 p-12 text-center">
                    <div
                        class="w-24 h-24 bg-green-100 dark:bg-green-900/30 text-green-500 rounded-full flex items-center justify-center mx-auto mb-6 text-5xl">
                        ✅</div>
                    <h3 id="step-3-title" class="text-3xl font-black text-gray-800 dark:text-white mb-4">제작 대기열에
                        추가되었습니다!</h3>

                    <!-- [NEW] Real-time Progress Section -->
                    <div id="automation-progress-container" class="mt-8 mb-10 max-w-md mx-auto">
                        <div class="flex justify-between items-center mb-3">
                            <span id="automation-status-text" class="text-sm font-bold text-gray-400">오토파일럿 워커 대기
                                중...</span>
                            <span id="automation-percent" class="text-sm font-black text-purple-500">0%</span>
                        </div>
                        <div class="w-full bg-gray-100 dark:bg-gray-700 h-3 rounded-full overflow-hidden shadow-inner">
                            <div id="automation-progress-bar"
                                class="bg-gradient-to-r from-purple-500 via-blue-500 to-cyan-500 h-full w-0 transition-all duration-700">
                            </div>
                        </div>
                        <div id="automation-logs"
                            class="mt-6 text-[10px] text-gray-400 font-mono text-left bg-gray-50 dark:bg-gray-900/40 p-4 rounded-2xl h-40 overflow-y-auto custom-scrollbar border border-gray-100 dark:border-gray-800 shadow-sm">
                            <div class="text-blue-500 font-bold opacity-50">> 시스템 연결 대기 중...</div>
                        </div>
                    </div>

                    <p id="step-3-desc" class="text-gray-500 dark:text-gray-400 mb-8 max-w-lg mx-auto">
                        모든 장면에 대한 대본, TTS, 모션 설정이 완료되었습니다. <br>
                        브라우저를 닫으셔도 서버에서 제작이 계속 진행됩니다.
                    </p>

                    <div class="flex justify-center gap-4">
                        <a href="/projects" class="btn-primary px-8 py-3 rounded-xl bg-blue-600 font-bold text-white">내
                            프로젝트 바로가기</a>
                        <button onclick="location.reload()"
                            class="btn-secondary px-8 py-3 rounded-xl border border-gray-200 dark:border-gray-700 font-bold hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">새
                            작업 시작</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 5: PNG 컷 추출 -->
        <div id="tab-cuts" class="tab-content hidden">
            <div class="max-w-2xl mx-auto space-y-6 py-4">

                <!-- 입력 섹션 -->
                <div
                    class="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6 space-y-5">
                    <div class="flex items-center gap-3 mb-2">
                        <span
                            class="w-9 h-9 rounded-xl bg-emerald-500 text-white flex items-center justify-center text-xl shadow shadow-emerald-500/30">✂️</span>
                        <div>
                            <h3 class="font-black text-gray-800 dark:text-white text-base">{{ t('wt_cuts_start') }}</h3>
                            <p class="text-xs text-gray-400 mt-0.5">Instantly split images into cuts without AI
                                analysis.</p>
                        </div>
                    </div>

                    <!-- 폴더 경로 -->
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">📂 {{
                            t('wt_cuts_input') }}</label>
                        <input type="text" id="cuts-input-dir" placeholder="예: C:\Users\User\Downloads\Episode_01"
                            class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border-2 border-gray-200 dark:border-gray-700 rounded-xl text-sm font-mono focus:border-emerald-500 outline-none transition-all text-gray-700 dark:text-gray-200"
                            onkeydown="if(event.key==='Enter') startExtractCuts()">
                    </div>



                    <!-- 제외할 레이어 (PSD 전용) -->
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                            ✂️ {{ t('wt_cuts_exclude') }}
                            <span class="text-gray-400 font-normal normal-case">(PSD only — remove text/dialogue layers
                                before cutting)</span>
                        </label>
                        <input type="text" id="cuts-exclude-layer" value="식자"
                            placeholder="예: 식자, 대사  (쉼표로 구분, 비워두면 전체 레이어 포함)"
                            class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border-2 border-orange-200 dark:border-orange-900/50 rounded-xl text-sm focus:border-orange-400 outline-none transition-all text-gray-700 dark:text-gray-200">
                        <p class="text-[10px] text-orange-500 dark:text-orange-400 mt-1.5">
                            ⚡ 입력 시: <strong>① 레이어 제외 → ② 클린본 합성 → ③ 컷 분리</strong> (1회 클릭으로 모두 처리)
                        </p>
                    </div>

                    <!-- 추출 버튼 -->
                    <button id="cuts-start-btn" onclick="startExtractCuts()"
                        class="w-full py-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 shadow-lg shadow-emerald-500/20 font-black text-white text-sm hover:scale-[1.02] transition-transform flex items-center justify-center gap-2">
                        {{ t('wt_cuts_start') }}
                    </button>

                </div>

                <!-- 결과 섹션 -->
                <div id="cuts-result"
                    class="hidden bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-emerald-100 dark:border-emerald-900/30 p-6 space-y-4">

                    <!-- 저장 경로 -->
                    <div class="bg-emerald-50 dark:bg-emerald-900/10 rounded-xl p-4 flex items-start gap-3">
                        <span class="text-2xl mt-0.5">📁</span>
                        <div class="flex-1 min-w-0">
                            <p
                                class="text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-1">
                                저장 위치</p>
                            <p id="cuts-output-path"
                                class="text-sm font-mono text-gray-700 dark:text-gray-200 break-all"></p>
                        </div>
                        <button onclick="cutsCopyPath()" title="경로 복사"
                            class="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 font-bold hover:bg-emerald-200 transition-colors">
                            {{ t('wt_cuts_copy_path') }}
                        </button>
                    </div>

                    <!-- 통계 -->
                    <div class="grid grid-cols-4 gap-2">
                        <div class="bg-gray-50 dark:bg-gray-900 rounded-xl p-3 text-center">
                            <p class="text-xl font-black text-gray-800 dark:text-white" id="cuts-stat-files">0</p>
                            <p class="text-[10px] text-gray-400 mt-1">{{ t('wt_cuts_files') }}</p>
                        </div>
                        <div class="bg-emerald-50 dark:bg-emerald-900/10 rounded-xl p-3 text-center">
                            <p class="text-xl font-black text-emerald-600" id="cuts-stat-cuts">0</p>
                            <p class="text-[10px] text-gray-400 mt-1">{{ t('wt_cuts_extracted') }}</p>
                        </div>
                        <div class="bg-amber-50 dark:bg-amber-900/10 rounded-xl p-3 text-center">
                            <p class="text-xl font-black text-amber-500" id="cuts-stat-landscape">0</p>
                            <p class="text-[10px] text-gray-400 mt-1">{{ t('wt_cuts_landscape') }}</p>
                        </div>
                        <div class="bg-red-50 dark:bg-red-900/10 rounded-xl p-3 text-center">
                            <p class="text-xl font-black text-red-500" id="cuts-stat-errors">0</p>
                            <p class="text-[10px] text-gray-400 mt-1">{{ t('wt_cuts_errors') }}</p>
                        </div>
                    </div>

                    <!-- 파일 목록 -->
                    <div>
                        <h4 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">📋 {{
                            t('wt_cuts_list') }}</h4>
                        <div id="cuts-file-list"
                            class="bg-gray-50 dark:bg-gray-900 rounded-xl p-3 max-h-72 overflow-y-auto space-y-1 border border-gray-100 dark:border-gray-700 text-xs font-mono">
                        </div>
                    </div>

                    <!-- 오류 -->
                    <div id="cuts-errors-area" class="hidden">
                        <h4 class="text-xs font-bold text-red-400 uppercase tracking-wider mb-2">⚠️ 처리 오류</h4>
                        <div id="cuts-errors-list"
                            class="bg-red-50 dark:bg-red-900/10 rounded-xl p-3 text-xs text-red-500 space-y-1 border border-red-100 dark:border-red-900/30">
                        </div>
                    </div>

                    <!-- 다시 -->
                    <button onclick="resetExtractCuts()"
                        class="w-full py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-bold text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                        🔄 다시 추출
                    </button>
                </div>

                <!-- 오류 박스 -->
                <div id="cuts-error-box"
                    class="hidden bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-xl p-4 text-sm text-red-600 dark:text-red-400">
                </div>

            </div>
        </div><!-- End Tab 5 -->

        <!-- TAB 6: Video Builder -->
        <div id="tab-vbuilder" class="tab-content hidden">
            <div class="max-w-5xl mx-auto space-y-6 py-4">

                <!-- 헤더 -->
                <div
                    class="bg-gradient-to-r from-rose-900/30 to-purple-900/30 rounded-2xl border border-rose-500/20 p-6">
                    <div class="flex items-center gap-3 mb-2">
                        <span
                            class="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-500 to-purple-600 text-white flex items-center justify-center text-xl shadow shadow-rose-500/30">🎬</span>
                        <div>
                            <h3 class="font-black text-white text-lg">AI Video Builder</h3>
                            <p class="text-xs text-rose-300/80 mt-0.5">PNG 컷 + 대본 → Gemini 감독 기획서 → Scene Builder 체인 영상
                                생성</p>
                        </div>
                    </div>
                    <div class="mt-4 grid grid-cols-3 gap-3 text-xs">
                        <div class="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                            <div class="text-rose-400 font-black text-base">STEP 1</div>
                            <div class="text-white/70 mt-1">PNG 폴더 지정<br>+ 대본 참조</div>
                        </div>
                        <div class="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                            <div class="text-purple-400 font-black text-base">STEP 2</div>
                            <div class="text-white/70 mt-1">Gemini 감독<br>기획서 생성</div>
                        </div>
                        <div class="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                            <div class="text-blue-400 font-black text-base">STEP 3</div>
                            <div class="text-white/70 mt-1">승인 후<br>영상 자동 생성</div>
                        </div>
                    </div>
                </div>

                <!-- STEP 1: 입력 -->
                <div id="vb-step1"
                    class="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6 space-y-4">
                    <h4 class="font-black text-gray-800 dark:text-white text-sm flex items-center gap-2">
                        <span
                            class="w-6 h-6 rounded-lg bg-rose-500 text-white flex items-center justify-center text-xs">1</span>
                        분석할 PNG 컷 폴더 지정
                    </h4>

                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">📂 PNG 컷 폴더
                            경로</label>
                        <input type="text" id="vb-folder-path" placeholder="예: C:\Users\User\Downloads\Episode_01\cuts"
                            class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border-2 border-gray-200 dark:border-gray-700 rounded-xl text-sm font-mono focus:border-rose-500 outline-none transition-all text-gray-700 dark:text-gray-200">
                        <p class="text-[10px] text-gray-400 mt-1.5">💡 PNG 컷 추출 탭에서 추출한 cuts 폴더를 그대로 사용하세요.</p>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">📝 대본 맥락
                            (선택)</label>
                        <textarea id="vb-script-context" rows="3"
                            placeholder="Gemini가 참고할 스토리 맥락을 입력하세요. (비워두면 기존 기획서를 자동 참조합니다)"
                            class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border-2 border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:border-rose-500 outline-none transition-all text-gray-700 dark:text-gray-200 resize-none"></textarea>
                    </div>

                    <div id="vb-file-preview" class="hidden">
                        <p class="text-xs font-bold text-gray-500 mb-2">📋 감지된 이미지 파일</p>
                        <div id="vb-file-list"
                            class="bg-gray-50 dark:bg-gray-900 rounded-xl p-3 max-h-40 overflow-y-auto text-xs font-mono text-gray-600 dark:text-gray-400 space-y-0.5 border border-gray-200 dark:border-gray-700">
                        </div>
                    </div>

                    <div class="flex gap-3">
                        <button onclick="vbScanFolder()"
                            class="flex-1 py-3 rounded-xl bg-gray-100 dark:bg-gray-700 font-bold text-gray-600 dark:text-gray-300 text-sm hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex items-center justify-center gap-2">
                            📂 폴더 스캔
                        </button>
                        <button id="vb-analyze-btn" onclick="vbStartAnalysis()"
                            class="flex-2 flex-1 py-3 rounded-xl bg-gradient-to-r from-rose-500 to-purple-600 shadow-lg shadow-rose-500/20 font-black text-white text-sm hover:scale-[1.02] transition-transform flex items-center justify-center gap-2">
                            ✨ Gemini 감독 기획서 생성
                        </button>
                    </div>
                </div>

                <!-- STEP 2: 분석 중 -->
                <div id="vb-loading"
                    class="hidden bg-white dark:bg-gray-800 rounded-2xl border border-purple-200 dark:border-purple-900/30 p-8 text-center">
                    <div
                        class="w-16 h-16 rounded-full bg-gradient-to-br from-rose-500 to-purple-600 flex items-center justify-center mx-auto mb-4 animate-pulse">
                        <span class="text-2xl">🎬</span>
                    </div>
                    <p class="font-black text-gray-800 dark:text-white text-lg">Gemini 감독이 분석 중...</p>
                    <p class="text-sm text-gray-500 mt-2">각 씬의 분위기, 카메라 모션, 영상 프롬프트를 생성하고 있습니다.</p>
                    <div class="mt-4 w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2">
                        <div class="bg-gradient-to-r from-rose-500 to-purple-600 h-2 rounded-full animate-pulse"
                            style="width: 65%"></div>
                    </div>
                </div>

                <!-- STEP 3: 감독 기획서 결과 -->
                <div id="vb-result" class="hidden space-y-4">

                    <!-- 총 연출 방향 -->
                    <div
                        class="bg-gradient-to-br from-purple-900/40 to-rose-900/30 rounded-2xl border border-purple-500/20 p-5">
                        <div class="flex items-start gap-3">
                            <span class="text-2xl">🎭</span>
                            <div class="flex-1">
                                <p class="text-xs font-bold text-purple-400 uppercase tracking-wider mb-1">감독 총평 & 연출 방향
                                </p>
                                <p id="vb-overview" class="text-white text-sm leading-relaxed"></p>
                                <div class="mt-3 flex flex-wrap gap-2">
                                    <span
                                        class="px-3 py-1 bg-purple-500/20 rounded-full text-xs text-purple-300 border border-purple-500/30">🎵
                                        <span id="vb-bgm"></span></span>
                                    <span
                                        class="px-3 py-1 bg-rose-500/20 rounded-full text-xs text-rose-300 border border-rose-500/30">⏱️
                                        <span id="vb-duration"></span></span>
                                    <span
                                        class="px-3 py-1 bg-blue-500/20 rounded-full text-xs text-blue-300 border border-blue-500/30">🎨
                                        <span id="vb-mood"></span></span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 씬별 카드 목록 -->
                    <div>
                        <div class="flex items-center justify-between mb-3">
                            <h4 class="font-black text-gray-800 dark:text-white text-sm flex items-center gap-2">
                                <span
                                    class="w-6 h-6 rounded-lg bg-purple-500 text-white flex items-center justify-center text-xs">2</span>
                                씬별 감독 연출 기획서
                            </h4>
                            <p class="text-xs text-gray-400">프롬프트를 직접 수정할 수 있습니다</p>
                        </div>
                        <div id="vb-scene-cards" class="space-y-3"></div>
                    </div>

                    <!-- 승인 버튼 -->
                    <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-5">
                        <div class="flex items-center gap-3 mb-4">
                            <span
                                class="w-6 h-6 rounded-lg bg-blue-500 text-white flex items-center justify-center text-xs">3</span>
                            <h4 class="font-black text-gray-800 dark:text-white text-sm">영상 생성 승인</h4>
                        </div>
                        <div
                            class="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 mb-4 text-sm text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-900/50">
                            💡 위 감독 기획서를 확인하신 후, 필요한 경우 프롬프트를 수정하고 승인 버튼을 눌러주세요.<br>
                            승인 시 각 씬의 마지막 프레임이 다음 씬의 시작 이미지로 연결되는 <strong>Scene Builder 체인</strong>으로 영상이 생성됩니다.
                        </div>
                        <div class="grid grid-cols-2 gap-3">
                            <button onclick="vbReset()"
                                class="py-3 rounded-xl border border-gray-200 dark:border-gray-700 font-bold text-gray-500 dark:text-gray-400 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                                🔄 다시 분석
                            </button>
                            <button onclick="vbApproveAndGenerate()"
                                class="py-3 rounded-xl bg-gradient-to-r from-blue-500 to-purple-600 shadow-lg font-black text-white text-sm hover:scale-[1.02] transition-transform flex items-center justify-center gap-2">
                                ✅ 승인하고 영상 생성 시작
                            </button>
                        </div>
                    </div>

                </div>

                <!-- 오류 -->
                <div id="vb-error"
                    class="hidden bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50 rounded-xl p-4 text-sm text-red-600 dark:text-red-400">
                </div>

            </div>
        </div><!-- End Tab 6 -->"""

html = re.sub(r'<!-- \[NEW\] GENERATION UI IN TAB 2 -->.*?</div>\s*</div>\s*</div> <!-- End Analysis Result Container -->\s*</div> <!-- End Tab 2 -->', lambda m: deleted_body_part_1 + '\n                </div>\n            </div> <!-- End Analysis Result Container -->\n        </div> <!-- End Tab 2 -->', html, flags=re.DOTALL)

# Revert generatePlan button in analysis tab changes
html = re.sub(r'<button id="plan-btn" onclick="document\.getElementById\(\'vb-result\'\)\.scrollIntoView.*?🎬 영상 생성으로 이동\n\s*</button>', lambda m: r"""<button id="plan-btn" onclick="generatePlan()"
                                class="px-6 py-2 rounded-xl bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border-2 border-indigo-600 dark:border-indigo-400 shadow-lg shadow-indigo-500/10 font-bold flex items-center gap-2 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-all">
                                📋 {{ t('wt_goto_plan') }}
                            </button>""", html, flags=re.DOTALL)

# Remove the injected script function approveAndGenerate
html = re.sub(r'function approveAndGenerate\(\) \{.*?(?=function vbApproveAndGenerate)', lambda m: '', html, flags=re.DOTALL)

# Revert renderScenes removing vb-result
html = html.replace("document.getElementById('analysis-result-container').classList.remove('hidden');\n    document.getElementById('vb-result').style.display = 'block';", "document.getElementById('analysis-result-container').classList.remove('hidden');")

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("Restored successfully")
