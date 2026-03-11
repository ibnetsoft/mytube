import os
import re

html_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\templates\pages\webtoon_studio.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace plan-btn logic
pattern_plan_btn = r'<button id="plan-btn" onclick="generatePlan\(\)".*?</button>'
new_plan_btn = """<button id="plan-btn" onclick="document.getElementById('vb-result').scrollIntoView({behavior:'smooth'})"
                                class="px-6 py-2 rounded-xl bg-white dark:bg-gray-800 text-rose-600 dark:text-rose-400 border-2 border-rose-600 dark:border-rose-400 shadow-lg shadow-rose-500/10 font-bold flex items-center gap-2 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-all">
                                🎬 영상 생성으로 이동
                            </button>"""
html = re.sub(pattern_plan_btn, new_plan_btn, html, flags=re.DOTALL)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("Fix plan-btn done")
