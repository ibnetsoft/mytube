import webbrowser
import subprocess
import sys
import os
import json
import multiprocessing

# [FIX] Delayed import for tkinter to avoid Tcl/Tk errors in server mode
tk = None
ttk = None
messagebox = None

# Configuration
AUTH_URL = "https://mytube-ashy-seven.vercel.app"
LICENSE_FILE = "license.key"

TRANSLATIONS = {
    'ko': {
        'title': 'PICADIRI STUDIO 런처',
        'subtitle': 'AI 자동 영상 제작 플랫폼',
        'input_label': '라이선스 키 / 유저 ID 입력',
        'launch_btn': '🚀 스튜디오 시작',
        'get_key_btn': '🔑 라이선스 키 발급받기',
        'status_empty': '유효한 라이선스 키를 입력해주세요.',
        'status_launch': '시작 중...',
        'error': '오류 발생: ',
        'or': '---------- 또는 ----------'
    },
    'en': {
        'title': 'PICADIRI STUDIO Launcher',
        'subtitle': 'AI Automated Video Creation Platform',
        'input_label': 'Enter License Key / User ID',
        'launch_btn': '🚀 Launch Studio',
        'get_key_btn': '🔑 Get License Key',
        'status_empty': 'Please enter a valid license key.',
        'status_launch': 'Launching...',
        'error': 'Error: ',
        'or': '---------- OR ----------'
    },
    'vi': {
        'title': 'Bộ khởi chạy PICADIRI STUDIO',
        'subtitle': 'Nền tảng tạo video tự động bằng AI',
        'input_label': 'Nhập mã bản quyền / ID người dùng',
        'launch_btn': '🚀 Bắt đầu Studio',
        'get_key_btn': '🔑 Lấy mã bản quyền',
        'status_empty': 'Vui lòng nhập mã bản quyền hợp lệ.',
        'status_launch': 'Đang khởi chạy...',
        'error': 'Lỗi: ',
        'or': '---------- HOẶC ----------'
    },
    'es': {
        'title': 'Lanzador de PICADIRI STUDIO',
        'subtitle': 'Plataforma de creación de video automatizada por AI',
        'input_label': 'Ingrese clave de licencia / ID de usuario',
        'launch_btn': '🚀 Iniciar Studio',
        'get_key_btn': '🔑 Obtener clave de licencia',
        'status_empty': 'Por favor ingrese una clave válida.',
        'status_launch': 'Iniciando...',
        'error': 'Error: ',
        'or': '---------- O ----------'
    },
    'th': {
        'title': 'ตัวเปิด PICADIRI STUDIO',
        'subtitle': 'แพลตฟอร์มสร้างวิดีโออัตโนมัติด้วย AI',
        'input_label': 'ใส่รหัสใบอนุญาต / ID ผู้ใช้',
        'launch_btn': '🚀 เริ่มต้นสตูดิโอ',
        'get_key_btn': '🔑 รับรหัสใบอนุญาต',
        'status_empty': 'กรุณาใส่รหัสใบอนุญาตที่ถูกต้อง',
        'status_launch': 'กำลังเริ่ม...',
        'error': 'ข้อผิดพลาด: ',
        'or': '---------- หรือ ----------'
    },
    'id': {
        'title': 'Peluncur PICADIRI STUDIO',
        'subtitle': 'Platform Pembuatan Video Otomatis AI',
        'input_label': 'Masukkan Kunci Lisensi / ID Pengguna',
        'launch_btn': '🚀 Jalankan Studio',
        'get_key_btn': '🔑 Dapatkan Kunci Lisensi',
        'status_empty': 'Silakan masukkan kunci lisensi yang valid.',
        'status_launch': 'Menjalankan...',
        'error': 'Kesalahan: ',
        'or': '---------- ATAU ----------'
    },
    'fr': {
        'title': 'Lanceur PICADIRI STUDIO',
        'subtitle': 'Plateforme de création vidéo automatisée par IA',
        'input_label': 'Entrez la clé de licence / ID utilisateur',
        'launch_btn': '🚀 Lancer le Studio',
        'get_key_btn': '🔑 Obtenir une clé de licence',
        'status_empty': 'Veuillez entrer une clé de licence valide.',
        'status_launch': 'Lancement...',
        'error': 'Erreur : ',
        'or': '---------- OU ----------'
    },
    'ru': {
        'title': 'Запуск PICADIRI STUDIO',
        'subtitle': 'AI-платформа для создания видео',
        'input_label': 'Введите лицензионный ключ / ID',
        'launch_btn': '🚀 Запустить студию',
        'get_key_btn': '🔑 Получить ключ',
        'status_empty': 'Пожалуйста, введите ключ.',
        'status_launch': 'Запуск...',
        'error': 'Ошибка: ',
        'or': '---------- ИЛИ ----------'
    },
    'pt': {
        'title': 'Lançador PICADIRI STUDIO',
        'subtitle': 'Plataforma de Criação de Vídeo Automática por IA',
        'input_label': 'Insira a Chave de Licença / ID de Usuário',
        'launch_btn': '🚀 Iniciar Studio',
        'get_key_btn': '🔑 Obter Chave de Licença',
        'status_empty': 'Por favor, insira uma chave válida.',
        'status_launch': 'Iniciando...',
        'error': 'Erro: ',
        'or': '---------- OU ----------'
    }
}

LANGUAGES = [
    ('ko', '🇰🇷 한국어'),
    ('en', '🇺🇸 English'),
    ('vi', '🇻🇳 Tiếng Việt'),
    ('es', '🇪🇸 Español'),
    ('th', '🇹🇭 ภาษาไทย'),
    ('id', '🇮🇩 Bahasa Indonesia'),
    ('fr', '🇫🇷 Français'),
    ('ru', '🇷🇺 Русский'),
    ('pt', '🇧🇷 Português')
]

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.current_lang = 'ko'
        self.root.title("PICADIRI STUDIO Launcher")
        self.root.geometry("450x650")
        self.root.configure(bg="#1a1a1a")
        self.root.resizable(False, False)

        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#1a1a1a")
        style.configure("TLabel", background="#1a1a1a", foreground="white", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 24, "bold"), foreground="#3b82f6")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10, background="#3b82f6", foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", "#2563eb")])
        style.configure("TMenubutton", font=("Segoe UI", 9), background="#333", foreground="white")

        # UI Elements
        self.create_widgets()

        # Check existing license
        self.check_saved_license()

    def create_widgets(self):
        # Clear existing widgets if any
        for widget in self.root.winfo_children():
            widget.destroy()

        t = TRANSLATIONS[self.current_lang]

        main_frame = ttk.Frame(self.root, padding="30 20 30 40")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Language Selector at Top Right
        lang_frame = ttk.Frame(main_frame)
        lang_frame.pack(anchor="e", pady=(0, 20))
        
        self.lang_var = tk.StringVar(value=dict(LANGUAGES).get(self.current_lang))
        lang_menu = ttk.OptionMenu(
            lang_frame, 
            self.lang_var, 
            dict(LANGUAGES).get(self.current_lang), 
            *[name for code, name in LANGUAGES],
            command=self.change_language
        )
        lang_menu.pack()

        # Logo / Title
        title_label = ttk.Label(main_frame, text="PICADIRI STUDIO", style="Header.TLabel")
        title_label.pack(pady=(0, 5))

        subtitle_label = ttk.Label(main_frame, text=t['subtitle'], foreground="#a0a0a0", font=("Segoe UI", 11))
        subtitle_label.pack(pady=(0, 40))

        # License Input
        input_label = ttk.Label(main_frame, text=t['input_label'])
        input_label.pack(anchor="w", pady=(0, 8))

        self.license_entry = ttk.Entry(main_frame, font=("Consolas", 12), width=45)
        self.license_entry.pack(fill=tk.X, pady=(0, 25), ipady=8)

        # Buttons
        self.login_btn = ttk.Button(main_frame, text=t['launch_btn'], command=self.launch_app)
        self.login_btn.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(main_frame, text=t['or'], foreground="#404040").pack(pady=10)

        self.get_key_btn = ttk.Button(main_frame, text=t['get_key_btn'], command=self.open_auth_web)
        self.get_key_btn.pack(fill=tk.X, pady=(0, 10))
        
        # Status
        self.status_label = ttk.Label(main_frame, text="", foreground="#ef4444", font=("Segoe UI", 10))
        self.status_label.pack(pady=20)

    def change_language(self, selected_name):
        for code, name in LANGUAGES:
            if name == selected_name:
                self.current_lang = code
                break
        self.create_widgets()
        # Keep the license key if it was entered
        # (Since we recreate widgets, we need to restore the text)
        # Note: In a real app we'd just update labels, but recreating is easier for this structure

    def open_auth_web(self):
        webbrowser.open(AUTH_URL)

    def check_saved_license(self):
        if os.path.exists(LICENSE_FILE):
            try:
                with open(LICENSE_FILE, "r") as f:
                    key = f.read().strip()
                    self.license_entry.insert(0, key)
            except:
                pass

    def launch_app(self):
        t = TRANSLATIONS[self.current_lang]
        key = self.license_entry.get().strip()
        if not key:
            self.status_label.config(text=t['status_empty'])
            return

        # Save key
        with open(LICENSE_FILE, "w") as f:
            f.write(key)

        self.status_label.config(text=t['status_launch'], foreground="#22c55e")
        self.root.update()

        # Launch main.py
        try:
            self.root.withdraw()
            
            # Pass language to main.py via environment variable
            env = os.environ.copy()
            env["APP_LANG"] = self.current_lang
            
            # [FIX] Clear Tcl/Tk environment variables to avoid PyInstaller crash
            # Inherited paths from the GUI process can conflict with the new process extraction
            for k in ["TCL_LIBRARY", "TK_LIBRARY"]:
                if k in env:
                    del env[k]

            if getattr(sys, 'frozen', False):
                # When frozen, run the EXE itself with --server flag
                cmd = [sys.executable, "--server"]
                subprocess.Popen(cmd, cwd=os.path.dirname(sys.executable), env=env)
            else:
                # In development, run main.py script
                cmd = [sys.executable, "main.py"]
                subprocess.Popen(cmd, cwd=os.getcwd(), env=env)
            
            self.root.after(2000, self.root.destroy)
            
        except Exception as e:
            self.status_label.config(text=f"{t['error']}{e}")
            self.root.deiconify()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # check for server mode argument
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        # Launch main server
        print("🚀 Starting Main Studio Server...")
        import main
    else:
        # Launch GUI
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
        app = LauncherApp(root)
        root.mainloop()
