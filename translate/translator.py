#!/usr/bin/env python3
"""
Gemini 隨身翻譯 GUI
- 輸入文字，按 ⌘↩ 或「翻譯」按鈕呼叫 Gemini CLI
- 視窗保持最上層，啟動即聚焦輸入框
"""

import tkinter as tk
import subprocess
import threading
import os
import sys

# 確保能找到 gemini CLI
os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

PROMPT = (
    "檢測輸入文字的語言並將其翻譯。"
    "若原文為中文，翻譯成英文；否則翻譯成繁體中文。"
    "僅輸出翻譯內容。不做解釋、不加引號、不做額外格式。"
)
GEMINI_MODEL = None  # 使用 CLI 預設 model


def translate_text():
    input_text = text_in.get("1.0", "end-1c").strip()
    if not input_text:
        return

    btn_translate.config(state="disabled", text="翻譯中…")
    text_out.config(state="normal")
    text_out.delete("1.0", tk.END)
    text_out.insert(tk.END, "翻譯中…")
    text_out.config(state="disabled")

    def run():
        try:
            cmd = ["gemini", "-p", PROMPT]
            if GEMINI_MODEL:
                cmd = ["gemini", "-m", GEMINI_MODEL, "-p", PROMPT]
            result = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            translated = result.stdout.strip()
            if not translated:
                err = result.stderr.strip()
                translated = f"錯誤：{err}" if err else "翻譯失敗，請檢查 Gemini CLI 是否正常運作"
        except subprocess.TimeoutExpired:
            translated = "錯誤：翻譯超時（30 秒）"
        except FileNotFoundError:
            translated = "錯誤：找不到 gemini 指令，請確認已安裝 Gemini CLI\n（brew install gemini-cli 或參考官方文件）"
        except Exception as e:
            translated = f"錯誤：{e}"

        root.after(0, lambda: show_result(translated))

    threading.Thread(target=run, daemon=True).start()


def show_result(text: str):
    text_out.config(state="normal")
    text_out.delete("1.0", tk.END)
    text_out.insert(tk.END, text)
    text_out.config(state="disabled")
    btn_translate.config(state="normal", text="翻譯  ⌘↩")


def copy_result():
    result = text_out.get("1.0", "end-1c").strip()
    if result:
        root.clipboard_clear()
        root.clipboard_append(result)
        btn_copy.config(text="已複製！")
        root.after(1500, lambda: btn_copy.config(text="複製結果"))


def clear_all():
    text_in.delete("1.0", tk.END)
    text_out.config(state="normal")
    text_out.delete("1.0", tk.END)
    text_out.config(state="disabled")
    text_in.focus_set()


def on_cmd_enter(event):
    translate_text()
    return "break"


# ── 建立主視窗 ──────────────────────────────────────────────
root = tk.Tk()
root.title("Gemini 隨身翻譯")
root.geometry("520x420")
root.minsize(380, 320)
root.attributes("-topmost", True)
root.configure(bg="#f5f5f5", padx=14, pady=12)

FONT_LABEL = ("Helvetica Neue", 11)
FONT_TEXT = ("Helvetica Neue", 14)
FONT_BTN = ("Helvetica Neue", 12)
COLOR_BG = "#f5f5f5"
COLOR_TEXT_BG = "#ffffff"
COLOR_BTN = "#0071e3"
COLOR_BTN_FG = "#ffffff"

# ── 輸入區 ──
tk.Label(root, text="輸入文字", font=FONT_LABEL, bg=COLOR_BG, anchor="w").pack(fill="x")

frame_in = tk.Frame(root, bg=COLOR_TEXT_BG, bd=1, relief="solid")
frame_in.pack(fill="both", expand=True, pady=(4, 6))

text_in = tk.Text(
    frame_in, height=6, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=COLOR_TEXT_BG, fg="#1d1d1f",
    insertbackground="#1d1d1f",
)
text_in.pack(fill="both", expand=True)
text_in.focus_set()
text_in.bind("<Command-Return>", on_cmd_enter)
text_in.bind("<Control-Return>", on_cmd_enter)
root.bind("<Escape>", lambda e: root.destroy())

# ── 按鈕列 ──
frame_btns = tk.Frame(root, bg=COLOR_BG)
frame_btns.pack(fill="x", pady=4)

btn_translate = tk.Button(
    frame_btns, text="翻譯  ⌘↩", font=FONT_BTN,
    bg=COLOR_BTN, fg=COLOR_BTN_FG, activebackground="#005bbf",
    relief="flat", padx=16, pady=6, cursor="hand2",
    command=translate_text,
)
btn_translate.pack(side="left")

btn_clear = tk.Button(
    frame_btns, text="清除", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2",
    command=clear_all,
)
btn_clear.pack(side="left", padx=(8, 0))

btn_copy = tk.Button(
    frame_btns, text="複製結果", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2",
    command=copy_result,
)
btn_copy.pack(side="right")

# ── 輸出區 ──
tk.Label(root, text="翻譯結果", font=FONT_LABEL, bg=COLOR_BG, anchor="w").pack(fill="x")

frame_out = tk.Frame(root, bg=COLOR_TEXT_BG, bd=1, relief="solid")
frame_out.pack(fill="both", expand=True, pady=(4, 0))

text_out = tk.Text(
    frame_out, height=6, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=COLOR_TEXT_BG, fg="#1d1d1f",
    state="disabled",
)
text_out.pack(fill="both", expand=True)

# ── 啟動 ──
root.mainloop()
