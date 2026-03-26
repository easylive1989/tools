#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Gemini 隨身翻譯 GUI
- 每次翻譯呼叫 gemini -p（非互動模式），乾淨無 TUI 干擾
- ⌘↩ 翻譯，Esc 關閉
"""

import tkinter as tk
import threading
import subprocess
import os
import re

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r')
_SYSTEM_PROMPT = (
    "你是翻譯工具。規則：若輸入為中文翻譯成英文，否則翻譯成繁體中文。"
    "僅輸出翻譯結果，不加解釋、引號或其他格式。"
)


def _do_translate(text: str, timeout: int = 60) -> str:
    prompt = f"{_SYSTEM_PROMPT}\n\n翻譯：{text}"
    try:
        result = subprocess.run(
            ["gemini", "-m", "gemini-2.5-flash", "-p", prompt],
            capture_output=True, text=True, timeout=timeout,
            env=os.environ.copy(),
        )
        output = _ANSI_RE.sub('', result.stdout).strip()
        if not output and result.stderr:
            err = _ANSI_RE.sub('', result.stderr).strip()
            return f"錯誤：{err[:200]}"
        return output or "錯誤：無回應"
    except subprocess.TimeoutExpired:
        return "錯誤：翻譯超時"
    except FileNotFoundError:
        return "錯誤：找不到 gemini 指令"
    except Exception as e:
        return f"錯誤：{e}"


# ── UI 邏輯 ──────────────────────────────────────────────────
def translate_text():
    input_text = text_in.get("1.0", "end-1c").strip()
    if not input_text:
        return

    btn_translate.config(state="disabled", text="翻譯中…")
    _set_output("翻譯中…", editable=False)

    def run():
        result = _do_translate(input_text)
        root.after(0, lambda: show_result(result))

    threading.Thread(target=run, daemon=True).start()


def show_result(text: str):
    _set_output(text, editable=False)
    btn_translate.config(state="normal", text="翻譯  ⌘↩")


def _set_output(text: str, *, editable: bool):
    text_out.config(state="normal")
    text_out.delete("1.0", tk.END)
    text_out.insert(tk.END, text)
    if not editable:
        text_out.config(state="disabled")


def copy_result():
    result = text_out.get("1.0", "end-1c").strip()
    if result:
        root.clipboard_clear()
        root.clipboard_append(result)
        btn_copy.config(text="已複製！")
        root.after(1500, lambda: btn_copy.config(text="複製結果"))


def clear_all():
    text_in.delete("1.0", tk.END)
    _set_output("", editable=False)
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
FONT_TEXT  = ("Helvetica Neue", 14)
FONT_BTN   = ("Helvetica Neue", 12)
C_BG       = "#f5f5f5"
C_TEXT_BG  = "#ffffff"
C_BTN      = "#0071e3"
C_BTN_FG   = "#ffffff"

# 輸入區
tk.Label(root, text="輸入文字", font=FONT_LABEL, bg=C_BG, anchor="w").pack(fill="x")
frame_in = tk.Frame(root, bg=C_TEXT_BG, bd=1, relief="solid")
frame_in.pack(fill="both", expand=True, pady=(4, 6))
text_in = tk.Text(
    frame_in, height=6, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=C_TEXT_BG, fg="#1d1d1f", insertbackground="#1d1d1f",
)
text_in.pack(fill="both", expand=True)
text_in.focus_set()
text_in.bind("<Command-Return>", on_cmd_enter)
text_in.bind("<Control-Return>", on_cmd_enter)
root.bind("<Escape>", lambda e: root.destroy())

# 按鈕列
frame_btns = tk.Frame(root, bg=C_BG)
frame_btns.pack(fill="x", pady=4)

btn_translate = tk.Button(
    frame_btns, text="翻譯  ⌘↩", font=FONT_BTN,
    bg=C_BTN, fg=C_BTN_FG, activebackground="#005bbf",
    disabledforeground="#a0a0a0",
    relief="flat", padx=16, pady=6, cursor="hand2", command=translate_text,
)
btn_translate.pack(side="left")

tk.Button(
    frame_btns, text="清除", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2", command=clear_all,
).pack(side="left", padx=(8, 0))

btn_copy = tk.Button(
    frame_btns, text="複製結果", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2", command=copy_result,
)
btn_copy.pack(side="right")

# 輸出區
tk.Label(root, text="翻譯結果", font=FONT_LABEL, bg=C_BG, anchor="w").pack(fill="x")
frame_out = tk.Frame(root, bg=C_TEXT_BG, bd=1, relief="solid")
frame_out.pack(fill="both", expand=True, pady=(4, 0))
text_out = tk.Text(
    frame_out, height=6, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=C_TEXT_BG, fg="#1d1d1f", state="disabled",
)
text_out.pack(fill="both", expand=True)

# 啟動
root.mainloop()
