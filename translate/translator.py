#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Gemini 隨身翻譯 GUI
- 每次翻譯呼叫 gemini -p（非互動模式），乾淨無 TUI 干擾
- ⌘↩ 翻譯，Esc 關閉
- 支援同步多個翻譯，以 Tab 管理結果
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


# ── Tab 狀態 ──────────────────────────────────────────────────
tabs = []           # {"id": int, "source": str, "result": str, "status": str, "widget": Frame}
active_tab_id = None
tab_counter = 0


def _find_tab(tab_id):
    return next((t for t in tabs if t["id"] == tab_id), None)


def create_tab(source_text: str) -> int:
    global tab_counter, active_tab_id

    tab_counter += 1
    tid = tab_counter

    # 建立 Tab 按鈕區塊
    tab_frame = tk.Frame(frame_tabs, bg=C_BG, padx=2, pady=2)
    tab_frame.pack(side="left", padx=(0, 2))

    lbl = tk.Button(
        tab_frame, text=f"Tab {tid}", font=("Helvetica Neue", 10),
        relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
        command=lambda t=tid: switch_tab(t),
    )
    lbl.pack(side="left")

    close_btn = tk.Button(
        tab_frame, text="×", font=("Helvetica Neue", 10),
        relief="flat", bd=0, padx=4, pady=3, cursor="hand2",
        command=lambda t=tid: close_tab(t),
    )
    close_btn.pack(side="left")

    tabs.append({
        "id": tid,
        "source": source_text,
        "result": "翻譯中…",
        "status": "translating",
        "widget": tab_frame,
        "lbl": lbl,
        "close": close_btn,
    })

    # 顯示 Tab 列（第一次），確保在輸出區上方
    if not frame_tabs.winfo_ismapped():
        frame_tabs.pack(fill="x", pady=(0, 2), before=frame_out)

    switch_tab(tid)
    return tid


def close_tab(tab_id: int):
    global active_tab_id

    tab = _find_tab(tab_id)
    if not tab:
        return

    tab["widget"].destroy()
    tabs.remove(tab)

    if not tabs:
        active_tab_id = None
        frame_tabs.pack_forget()
        _set_output("", editable=False)
        return

    # 若關掉的是 active tab，切換到最後一個
    if active_tab_id == tab_id:
        switch_tab(tabs[-1]["id"])
    else:
        _refresh_tab_styles()


def switch_tab(tab_id: int):
    global active_tab_id
    active_tab_id = tab_id
    _refresh_tab_styles()
    update_output_display()


def _refresh_tab_styles():
    for t in tabs:
        is_active = t["id"] == active_tab_id
        bg = C_TEXT_BG if is_active else "#d1d1d6"
        fg = "#1d1d1f"
        t["widget"].config(bg=bg)
        t["lbl"].config(bg=bg, fg=fg)
        t["close"].config(bg=bg, fg="#555555")


def update_output_display():
    if active_tab_id is None:
        _set_output("", editable=False)
        return

    tab = _find_tab(active_tab_id)
    if not tab:
        return

    content = f"【原文】\n{tab['source']}\n\n{'─' * 20}\n\n【翻譯】\n{tab['result']}"
    _set_output(content, editable=False)


# ── UI 邏輯 ──────────────────────────────────────────────────
def translate_text():
    input_text = text_in.get("1.0", "end-1c").strip()
    if not input_text:
        return

    tab_id = create_tab(input_text)
    text_in.delete("1.0", tk.END)

    def run():
        result = _do_translate(input_text)
        def on_done():
            tab = _find_tab(tab_id)
            if tab:
                tab["result"] = result
                tab["status"] = "done"
                if active_tab_id == tab_id:
                    update_output_display()
        root.after(0, on_done)

    threading.Thread(target=run, daemon=True).start()


def _set_output(text: str, *, editable: bool):
    text_out.config(state="normal")
    text_out.delete("1.0", tk.END)
    text_out.insert(tk.END, text)
    if not editable:
        text_out.config(state="disabled")


def clear_all():
    text_in.delete("1.0", tk.END)
    text_in.focus_set()


def on_cmd_enter(event):
    translate_text()
    return "break"


# ── 建立主視窗 ──────────────────────────────────────────────
root = tk.Tk()
root.title("Gemini 隨身翻譯")
root.geometry("520x420")
root.minsize(380, 320)
root.resizable(True, True)
root.attributes("-topmost", True)
root.configure(bg="#f5f5f5", padx=14, pady=12)

FONT_LABEL = ("Helvetica Neue", 11)
FONT_TEXT  = ("Helvetica Neue", 14)
FONT_BTN   = ("Helvetica Neue", 12)
C_BG       = "#f5f5f5"
C_TEXT_BG  = "#ffffff"
C_BTN      = "#0071e3"
C_BTN_FG   = "#ffffff"

# 輸入區（縮小為 height=3）
tk.Label(root, text="輸入文字", font=FONT_LABEL, bg=C_BG, anchor="w").pack(fill="x")
frame_in = tk.Frame(root, bg=C_TEXT_BG, bd=1, relief="solid")
frame_in.pack(fill="x", pady=(4, 6))
text_in = tk.Text(
    frame_in, height=3, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=C_TEXT_BG, fg="#1d1d1f", insertbackground="#1d1d1f",
)
text_in.pack(fill="both", expand=True)
text_in.focus_set()
text_in.bind("<Command-Return>", on_cmd_enter)
text_in.bind("<Control-Return>", on_cmd_enter)

initial_text = os.environ.get("TRANSLATOR_INITIAL_TEXT", "").strip()
if initial_text:
    text_in.insert("1.0", initial_text)
    root.after(100, translate_text)

root.bind("<Escape>", lambda e: root.destroy())

# 按鈕列
frame_btns = tk.Frame(root, bg=C_BG)
frame_btns.pack(fill="x", pady=4)

btn_translate = tk.Button(
    frame_btns, text="翻譯  ⌘↩", font=FONT_BTN,
    bg=C_BTN, fg="#1d1d1f", activebackground="#005bbf",
    disabledforeground="#a0a0a0",
    relief="flat", padx=16, pady=6, cursor="hand2", command=translate_text,
)
btn_translate.pack(side="left")

tk.Button(
    frame_btns, text="清除", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2", command=clear_all,
).pack(side="left", padx=(8, 0))

tk.Button(
    frame_btns, text="📝 Apple Notes", font=FONT_BTN,
    bg="#e5e5ea", fg="#1d1d1f", activebackground="#d1d1d6",
    relief="flat", padx=12, pady=6, cursor="hand2",
    command=lambda: subprocess.Popen(["open", "-a", "Notes"]),
).pack(side="right")

# 輸出區（Tab 列 + 文字匡）
frame_out_wrapper = tk.Frame(root, bg=C_BG)
frame_out_wrapper.pack(fill="both", expand=True)

# Tab 頁籤列（初始隱藏）
frame_tabs = tk.Frame(frame_out_wrapper, bg=C_BG)
# 不 pack，等第一個 Tab 建立時才顯示

# 輸出文字匡
frame_out = tk.Frame(frame_out_wrapper, bg=C_TEXT_BG, bd=1, relief="solid")
frame_out.pack(fill="both", expand=True)
text_out = tk.Text(
    frame_out, font=FONT_TEXT, wrap="word",
    relief="flat", bd=6, bg=C_TEXT_BG, fg="#1d1d1f", state="disabled",
)
text_out.pack(fill="both", expand=True)

# 啟動
root.mainloop()
