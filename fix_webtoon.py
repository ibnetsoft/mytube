import shutil
import re

head_path = 'webtoon_studio_HEAD.html'
dest_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\webtoon_studio.html'

shutil.copy(head_path, dest_path)

with open(dest_path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Remove disabled from tab-analysis
html = html.replace('id="tab-btn-analysis" onclick="switchWebtoonTab(\'analysis\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"\n                    disabled>',
                    'id="tab-btn-analysis" onclick="switchWebtoonTab(\'analysis\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">')

html = html.replace('id="tab-btn-plan" onclick="switchWebtoonTab(\'plan\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"\n                    disabled>',
                    'id="tab-btn-plan" onclick="switchWebtoonTab(\'plan\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">')

html = html.replace('id="tab-btn-produce" onclick="switchWebtoonTab(\'produce\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50"\n                    disabled>',
                    'id="tab-btn-produce" onclick="switchWebtoonTab(\'produce\')"\n                    class="tab-btn text-gray-400 px-4 py-2.5 rounded-xl text-xs font-black transition-all flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50">')

# 2. Update renderScenes to show PNG cuts side-by-side
# We locate `<!-- 원본 통 이미지 -->` and replace it.
original_img_html = r"""                        <!-- 원본 통 이미지 -->
                        <div class="mb-4">
                            <img src="${scene.image_path || ''}" alt="Scene Original Image" 
                                class="w-full h-auto object-contain rounded-xl border border-gray-200 dark:border-gray-700 max-h-[400px]">
                        </div>"""

new_img_html = r"""                        <!-- 통 이미지 및 추출된 컷 -->
                        <div class="mb-4 flex flex-col md:flex-row gap-4">
                            <div class="flex-1">
                                <span class="text-xs font-bold text-gray-500 mb-1 block">원본 이미지:</span>
                                <img src="${scene.original_image_path || scene.image_path || ''}" alt="Scene Original Image" 
                                    class="w-full h-auto object-contain rounded-xl border border-gray-200 dark:border-gray-700 max-h-[400px]">
                            </div>
                            ${scene.extracted_cuts && scene.extracted_cuts.length > 0 ? `
                            <div class="w-32 shrink-0 flex flex-col gap-2">
                                <span class="text-xs font-bold text-emerald-500 mb-1 block">추출된 컷 (${scene.extracted_cuts.length}장):</span>
                                <div class="flex flex-col gap-2 overflow-y-auto max-h-[400px] custom-scrollbar pr-1">
                                    ${scene.extracted_cuts.map(cut => `
                                        <img src="${cut}" class="w-full h-auto object-contain rounded-lg border border-emerald-200 shadow-sm" title="${cut.split('/').pop()}">
                                    `).join('')}
                                </div>
                            </div>
                            ` : ''}
                        </div>"""

html = html.replace(original_img_html, new_img_html)

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("done")
