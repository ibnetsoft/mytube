"""Read-only live monitor for the existing AE worker; never starts rendering."""
import sys, json, threading, queue
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from dotenv import load_dotenv
for name in ['.env', '.env.local', 'auth-web/.env.local']:
    load_dotenv(ROOT / name)
from worker.script_worker_store import ScriptStore
from worker.worker_config import OUTPUT_DIR, LOG_DIR

store = ScriptStore()
events = queue.Queue()
window = tk.Tk()
window.title('AIR Studio · AE 워커 진행 상황 · 토픽 3373')
window.geometry('920x650')
window.minsize(700, 480)
frame = ttk.Frame(window, padding=18)
frame.pack(fill='both', expand=True)
title = ttk.Label(frame, text='AE 입모양 워커 · 19~101씬', font=('Malgun Gothic', 17, 'bold'))
title.pack(anchor='w')
state = tk.StringVar(value='작업 큐를 조회하고 있습니다…')
ttk.Label(frame, textvariable=state, font=('Malgun Gothic', 12)).pack(anchor='w', pady=12)
bar = ttk.Progressbar(frame, maximum=83)
bar.pack(fill='x')
detail = tk.StringVar(value='15초마다 자동 갱신합니다. 이 창을 닫아도 워커는 계속 실행됩니다.')
ttk.Label(frame, textvariable=detail, wraplength=870).pack(anchor='w', pady=12)
columns = ('scene', 'status', 'speaker', 'note')
table = ttk.Treeview(frame, columns=columns, show='headings', height=14)
for column, label, width in [('scene','씬',55),('status','진행 상태',140),('speaker','화자',140),('note','지침 / 확인 사항',480)]:
    table.heading(column, text=label)
    table.column(column, width=width, stretch=column=='note')
table.pack(fill='both', expand=True)
stamp = tk.StringVar()
ttk.Label(frame, textvariable=stamp).pack(anchor='w', pady=8)
labels = {'queued':'대기', 'processing':'분석 중', 'direction_pending':'지침 승인 대기',
          'direction_approved':'지침 승인 완료', 'review_pending':'결과 검수 대기',
          'reviewed':'검수 완료', 'failed':'실패', 'needs_review':'화자·입 확인 필요',
          'skipped':'입모양 작업 제외', 'approved':'결과 승인 완료'}

def fetch():
    try:
        jobs = store.request('GET', 'std_project_assets', params={
            'select':'id,updated_at,metadata', 'project_id':'eq.e9233112-f0d7-4b35-91bf-2f892844eb30',
            'metadata->>kind':'eq.ae_mouth_job', 'order':'created_at.desc', 'limit':'1'})[0]
        events.put(('data', jobs[0] if jobs else None))
    except Exception as exc:
        events.put(('error', str(exc)[:240]))

def refresh():
    threading.Thread(target=fetch, daemon=True).start()

def poll():
    try:
        kind, value = events.get_nowait()
        if kind == 'error':
            stamp.set('조회 오류 · 다음 갱신에서 재시도: ' + value)
        elif value:
            meta = value['metadata']; rows = meta.get('results', [])
            total = len(meta.get('input', {}).get('scenes', [])) or 83
            phase = meta.get('phase', 'discovery')
            status = meta.get('state', 'queued')
            counts = {k:sum(r.get('status')==k for r in rows) for k in ['direction_pending','needs_review','skipped','approved']}
            state.set(f"{labels.get(status,status)} · {'입모양 영상 생성 / AE 렌더' if phase=='render' else '대사·화자·입 위치 분석'} · {len(rows)}/{total}씬")
            bar.configure(maximum=total, value=len(rows))
            detail.set(f"지침 준비 {counts['direction_pending']} · 확인 필요 {counts['needs_review']} · 제외 {counts['skipped']} · 결과 승인 {counts['approved']}\n" + (meta.get('error') or ('지침 승인 후 입모양 생성과 AE 렌더링을 시작합니다.' if phase != 'render' else 'AE 결과를 확인하고 승인해야 최종 렌더링할 수 있습니다.')))
            table.delete(*table.get_children())
            for row in rows:
                table.insert('', 'end', values=(row['number'],labels.get(row['status'],row['status']),', '.join(row.get('speakers', [])),row.get('reason') or row.get('direction') or ''))
            stamp.set('최근 조회: ' + datetime.now().strftime('%H:%M:%S') + ' · 큐 갱신: ' + value['updated_at'])
            (ROOT / '_dev/artifacts/ae_monitor_status.json').write_text(json.dumps({'job_id':value['id'],'state':status,'phase':phase,'completed':len(rows),'total':total,'counts':counts},ensure_ascii=False),encoding='utf8')
        else:
            state.set('AE 작업이 아직 등록되지 않았습니다.')
        window.after(15000, refresh)
    except queue.Empty:
        pass
    window.after(500, poll)

ttk.Button(frame, text='지금 새로고침', command=refresh).pack(anchor='e')
refresh()
poll()
window.mainloop()
