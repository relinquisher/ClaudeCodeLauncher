"""Claude Code ランチャー
フォルダとモデル(キャラクター)を選んで Claude Code を起動する GUI
"""
import json
import os
import subprocess
import tkinter.filedialog as filedialog
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from avatars import MODELS, get_avatar

CONFIG_PATH = Path(__file__).parent / "launcher_config.json"
MAX_RECENT = 8

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"recent_folders": [], "last_model": "sonnet", "read_japanese": False, "use_powershell": False}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                           encoding="utf-8")


class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Claude Code ランチャー")
        self.geometry("800x530")
        self.resizable(False, False)

        self.cfg = load_config()
        self.selected_model = self.cfg.get("last_model", "sonnet")
        self.model_cards = {}
        self.skip_perm_var = ctk.BooleanVar(
            value=self.cfg.get("skip_permissions", True))
        self.continue_var = ctk.BooleanVar(
            value=self.cfg.get("continue_session", False))
        self.resume_var = ctk.BooleanVar(
            value=self.cfg.get("resume_session", False))
        self.read_japanese_var = ctk.BooleanVar(
            value=self.cfg.get("read_japanese", False))
        self.use_powershell_var = ctk.BooleanVar(
            value=self.cfg.get("use_powershell", False))
        # --continue と --resume は同時指定できないので排他にする
        if self.continue_var.get() and self.resume_var.get():
            self.resume_var.set(False)

        self._build_model_section()
        self._build_folder_section()
        self._build_launch_section()
        self._update_selection_ui()

    # ---------- モデル選択 ----------
    def _build_model_section(self):
        ctk.CTkLabel(self, text="モデルを選んでね",
                     font=("Yu Gothic UI", 18, "bold")).pack(pady=(16, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=16)

        for model_id, m in MODELS.items():
            card = ctk.CTkFrame(row, corner_radius=16, width=140, height=190,
                                border_width=3, border_color="gray25")
            card.pack(side="left", padx=6)
            card.pack_propagate(False)

            img = ctk.CTkImage(light_image=get_avatar(model_id),
                               size=(96, 96))
            pic = ctk.CTkLabel(card, image=img, text="")
            pic.pack(pady=(12, 4))

            name = ctk.CTkLabel(card, text=m["label"],
                                font=("Yu Gothic UI", 16, "bold"))
            name.pack()
            desc = ctk.CTkLabel(card, text=m["desc"],
                                font=("Yu Gothic UI", 11),
                                text_color="gray70")
            desc.pack()

            for w in (card, pic, name, desc):
                w.bind("<Button-1>",
                       lambda e, mid=model_id: self._select_model(mid))
                w.configure(cursor="hand2")

            self.model_cards[model_id] = card

    def _select_model(self, model_id):
        self.selected_model = model_id
        self._update_selection_ui()

    def _update_selection_ui(self):
        for mid, card in self.model_cards.items():
            if mid == self.selected_model:
                card.configure(border_color="#3B8ED0", fg_color="gray17")
            else:
                card.configure(border_color="gray25", fg_color="gray14")
        m = MODELS[self.selected_model]
        self.launch_btn.configure(
            text=f"{m['label']} で起動 ▶")

    # ---------- フォルダ選択 ----------
    def _build_folder_section(self):
        ctk.CTkLabel(self, text="開始フォルダ",
                     font=("Yu Gothic UI", 18, "bold")).pack(pady=(20, 8))

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=24, fill="x")

        recents = self.cfg.get("recent_folders", [])
        default = recents[0] if recents else str(Path.home() / "Documents")

        self.folder_var = ctk.StringVar(value=default)
        self.folder_combo = ctk.CTkComboBox(
            frame, variable=self.folder_var, values=recents or [default],
            width=440, font=("Yu Gothic UI", 13))
        self.folder_combo.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(frame, text="参照...", width=90,
                      font=("Yu Gothic UI", 13),
                      command=self._browse).pack(side="left", padx=(8, 0))

    def _browse(self):
        current = self.folder_var.get()
        initial = current if os.path.isdir(current) else str(Path.home())
        path = filedialog.askdirectory(initialdir=initial,
                                       title="開始フォルダを選択")
        if path:
            self.folder_var.set(os.path.normpath(path))

    # ---------- 起動 ----------
    def _build_launch_section(self):
        ctk.CTkCheckBox(
            self, variable=self.skip_perm_var,
            text="確認(Do you want to proceed?)をスキップして起動",
            font=("Yu Gothic UI", 13)).pack(pady=(20, 0))

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(pady=(10, 0))

        ctk.CTkCheckBox(
            opts, variable=self.continue_var,
            text="--continue (直前の会話を再開)",
            font=("Yu Gothic UI", 13),
            command=lambda: self._toggle_session_opt("continue"),
        ).pack(side="left", padx=(0, 16))

        ctk.CTkCheckBox(
            opts, variable=self.resume_var,
            text="--resume (会話を選んで再開)",
            font=("Yu Gothic UI", 13),
            command=lambda: self._toggle_session_opt("resume"),
        ).pack(side="left")

        opts2 = ctk.CTkFrame(self, fg_color="transparent")
        opts2.pack(pady=(10, 0))

        ctk.CTkCheckBox(
            opts2, variable=self.read_japanese_var,
            text="日本語を読み上げる",
            font=("Yu Gothic UI", 13)).pack(side="left", padx=(0, 16))

        ctk.CTkCheckBox(
            opts2, variable=self.use_powershell_var,
            text="PowerShell 7 を使う",
            font=("Yu Gothic UI", 13)).pack(side="left")

        self.launch_btn = ctk.CTkButton(
            self, text="起動 ▶", height=52, corner_radius=26,
            font=("Yu Gothic UI", 18, "bold"),
            command=self._launch)
        self.launch_btn.pack(pady=(12, 4), padx=60, fill="x")

        self.status = ctk.CTkLabel(self, text="", font=("Yu Gothic UI", 12),
                                   text_color="gray70")
        self.status.pack()

    def _toggle_session_opt(self, which):
        """--continue と --resume は排他。片方をONにしたらもう片方をOFFにする"""
        if which == "continue" and self.continue_var.get():
            self.resume_var.set(False)
        elif which == "resume" and self.resume_var.get():
            self.continue_var.set(False)

    def _launch(self):
        folder = self.folder_var.get().strip().strip('"')
        if not folder or not os.path.isdir(folder):
            self.status.configure(text="⚠ フォルダが存在しません", text_color="#E06060")
            return

        folder = os.path.normpath(folder)
        model = self.selected_model

        # 履歴を更新
        recents = self.cfg.get("recent_folders", [])
        if folder in recents:
            recents.remove(folder)
        recents.insert(0, folder)
        self.cfg["recent_folders"] = recents[:MAX_RECENT]
        self.cfg["last_model"] = model
        skip_perm = self.skip_perm_var.get()
        do_continue = self.continue_var.get()
        do_resume = self.resume_var.get()
        read_japanese = self.read_japanese_var.get()
        use_powershell = self.use_powershell_var.get()
        self.cfg["skip_permissions"] = skip_perm
        self.cfg["continue_session"] = do_continue
        self.cfg["resume_session"] = do_resume
        self.cfg["read_japanese"] = read_japanese
        self.cfg["use_powershell"] = use_powershell
        save_config(self.cfg)
        self.folder_combo.configure(values=self.cfg["recent_folders"])

        # 新しいコンソールウィンドウで起動
        if model == "kimi":
            cmd = ["cmd", "/k", os.path.expandvars(r"%USERPROFILE%\kimi.cmd")]
        else:
            # claude のコマンドを構築
            claude_cmd = ["claude", "--model", model]
            if skip_perm:
                claude_cmd.append("--dangerously-skip-permissions")
            if do_continue:
                claude_cmd.append("--continue")
            elif do_resume:
                claude_cmd.append("--resume")

            if read_japanese:
                # 日本語読み上げを有効にする場合、PTY 経由のラッパーで起動
                script_path = Path(__file__).parent / "read_Japanese.py"
                if use_powershell:
                    # PowerShell で read_Japanese.py を実行
                    import shutil
                    pwsh_exe = shutil.which("pwsh")
                    if pwsh_exe:
                        # コマンドを PowerShell で実行
                        claude_cmd_str = " ".join(claude_cmd)
                        ps_cmd = f"python '{script_path}' {claude_cmd_str}"
                        cmd = ["pwsh", "-NoExit", "-Command", ps_cmd]
                    else:
                        # pwsh が見つからない場合は python で実行
                        cmd = ["python", str(script_path)] + claude_cmd
                else:
                    cmd = ["python", str(script_path)] + claude_cmd
            else:
                # 通常起動
                if use_powershell:
                    # PowerShell 7 で起動
                    import shutil
                    pwsh_exe = shutil.which("pwsh")
                    if pwsh_exe:
                        claude_cmd_str = " ".join(claude_cmd)
                        cmd = ["pwsh", "-NoExit", "-Command", claude_cmd_str]
                    else:
                        # pwsh が見つからない場合は cmd.exe にフォールバック
                        cmd = ["cmd", "/k"] + claude_cmd
                else:
                    # cmd.exe で起動
                    cmd = ["cmd", "/k"] + claude_cmd

        try:
            subprocess.Popen(
                cmd,
                cwd=folder,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            opt = ""
            if do_continue:
                opt = " (--continue)"
            elif do_resume:
                opt = " (--resume)"
            if read_japanese:
                opt += " 🔊"
            shell_info = " (PowerShell 7)" if use_powershell else ""
            self.status.configure(
                text=f"✓ {MODELS[model]['label']} を {folder} で起動しました{opt}{shell_info}",
                text_color="#60C080")
        except Exception as e:
            self.status.configure(text=f"⚠ 起動失敗: {e}", text_color="#E06060")


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()
