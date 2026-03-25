#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pexpect"]
# ///
"""
Gemini 隨身翻譯 GUI
- 啟動時開啟單一 gemini CLI process（pexpect）
- 後續翻譯只透過 stdin/stdout 傳訊，不重啟 process
- ⌘↩ 翻譯，Esc 關閉
"""

import tkinter as tk
import threading
import os
import re

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

# 用兩個哨兵標記翻譯結果的頭尾，避免被 echo 或 prompt 干擾
_BEGIN = "XXTRANSBEGINXX"
_END   = "XXTRANSENDXX"

_INIT_MSG = (
    "你是翻譯工具。規則：若輸入為中文翻譯成英文，否則翻譯成繁體中文。"
    "僅輸出翻譯結果，不加解釋、引號或其他格式。"
    f"每次翻譯前輸出 {_BEGIN}，完成後輸出 {_END}。"
    f"請確認並回覆：{_BEGIN}已準備就緒{_END}"
)

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r')


def _strip(s: str) -> str:
    return _ANSI_RE.sub('', s).strip()


# ── 持久 Gemini Session ──────────────────────────────────────
class _GeminiSession:
    """整個 app 生命週期只建立一次的 gemini CLI session。"""

    def __init__(self):
        self._child = None
        self._lock  = threading.Lock()
        self._ready = threading.Event()
        self._error: str | None = None
        threading.Thread(target=self._init, daemon=True).start()

    def _init(self):
        try:
            import pexpect
            self._child = pexpect.spawn(
                "gemini", encoding="utf-8", timeout=60, env=os.environ.copy()
            )
            self._child.sendline(_INIT_MSG)
            self._child.expect(_END, timeout=30)
        except ImportError:
            self._error = "找不到 pexpect，請執行：pip3 install pexpect"
        except Exception as e:
            self._error = str(e)
        finally:
            self._ready.set()

    def translate(self, text: str, timeout: int = 30) -> str:
        """送出文字並等待翻譯結果（在背景 thread 呼叫）。"""
        if not self._ready.wait(timeout=35):
            return "錯誤：Gemini 初始化超時"
        if self._error:
            return f"錯誤：{self._error}"

        with self._lock:
            try:
                import pexpect
                self._child.sendline(text)
                self._child.expect(_BEGIN, timeout=timeout)
                self._child.expect(_END,   timeout=timeout)
                return _strip(self._child.before or "")
            except Exception as e:
                import pexpect as _px
                return "錯誤：翻譯超時" if isinstance(e, _px.TIMEOUT) else f"錯誤：{e}"


# 程式啟動時立即開始初始化（背景進行，不阻塞 UI）
_session = _GeminiSession()


# ── UI 邏輯 ──────────────────────────────────────────────────
def translate_text():
    input_text = text_in.get("1.0", "end-1c").strip()
    if not input_text:
        return

    btn_translate.config(state="disabled", text="翻譯中…")
    _set_output("翻譯中…", editable=False)

    def run():
        result = _session.translate(input_text)
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
