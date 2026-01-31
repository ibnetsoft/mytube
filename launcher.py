import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import subprocess
import sys
import os
import json

# Configuration
AUTH_URL = "http://localhost:3000"
LICENSE_FILE = "license.key"

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MyTube Studio Launcher")
        self.root.geometry("400x500")
        self.root.configure(bg="#1a1a1a")
        self.root.resizable(False, False)

        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#1a1a1a")
        style.configure("TLabel", background="#1a1a1a", foreground="white", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 20, "bold"), foreground="#3b82f6")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10, background="#3b82f6", foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", "#2563eb")])

        # UI Elements
        self.create_widgets()

        # Check existing license
        self.check_saved_license()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="30 40 30 40")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Logo / Title
        title_label = ttk.Label(main_frame, text="MyTube Studio", style="Header.TLabel")
        title_label.pack(pady=(0, 10))

        subtitle_label = ttk.Label(main_frame, text="AI Automated Video Creation Platform", foreground="#a0a0a0")
        subtitle_label.pack(pady=(0, 40))

        # License Input
        input_label = ttk.Label(main_frame, text="Enter License Key / User ID")
        input_label.pack(anchor="w", pady=(0, 5))

        self.license_entry = ttk.Entry(main_frame, font=("Consolas", 11), width=40)
        self.license_entry.pack(fill=tk.X, pady=(0, 20), ipady=5)

        # Buttons
        self.login_btn = ttk.Button(main_frame, text="🚀 Launch Studio", command=self.launch_app)
        self.login_btn.pack(fill=tk.X, pady=(0, 10))

        separator = ttk.Frame(main_frame, height=2, style="TFrame") # Dummy separator
        ttk.Label(main_frame, text="---------- OR ----------", foreground="#404040").pack(pady=10)

        self.get_key_btn = ttk.Button(main_frame, text="🔑 Get License Key", command=self.open_auth_web)
        self.get_key_btn.configure() # Use different style if needed
        self.get_key_btn.pack(fill=tk.X, pady=(0, 10))
        
        # Status
        self.status_label = ttk.Label(main_frame, text="", foreground="#ef4444", font=("Segoe UI", 9))
        self.status_label.pack(pady=10)

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
        key = self.license_entry.get().strip()
        if not key:
            self.status_label.config(text="Please enter a valid license key.")
            return

        # TODO: Verify key against Supabase API usually.
        # For this hybrid proto, we will save it and trust it for now, 
        # or we could make a dummy request.
        
        # Save key
        with open(LICENSE_FILE, "w") as f:
            f.write(key)

        self.status_label.config(text="Launching...", foreground="#22c55e")
        self.root.update()

        # Launch main.py
        try:
            # Hide launcher
            self.root.withdraw()
            
            # Run main.py using the same python interpreter
            cmd = [sys.executable, "main.py"]
            subprocess.Popen(cmd, cwd=os.getcwd())
            
            # Close launcher after 2 seconds
            self.root.after(2000, self.root.destroy)
            
        except Exception as e:
            self.status_label.config(text=f"Error launching: {e}")
            self.root.deiconify()

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
