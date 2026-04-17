# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "feedparser",
# ]
# ///

import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

import feedparser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RSS_LIST_FILE = os.path.join(BASE_DIR, "rss_list.json")
OBSIDIAN_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/RSS 訂閱"
)
HISTORY_FILE = os.path.join(OBSIDIAN_DIR, "history.json")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_feeds():
    if not os.path.exists(RSS_LIST_FILE):
        return []
    with open(RSS_LIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("feeds", [])


def save_feeds(feeds):
    tmp = RSS_LIST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"feeds": feeds}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RSS_LIST_FILE)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def format_last_sync(iso_str):
    if not iso_str:
        return "從未同步"
    try:
        return datetime.fromisoformat(iso_str).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str


def find_uv():
    for p in ["/Users/paulwu/.local/bin/uv", "/opt/homebrew/bin/uv", "/usr/local/bin/uv"]:
        if os.path.exists(p):
            return p
    return "uv"


# ---------------------------------------------------------------------------
# Feed dialog (新增 / 編輯)
# ---------------------------------------------------------------------------

class FeedDialog:
    def __init__(self, parent, title, *, feed=None, sections=None):
        self.result = None
        sections = sections or []

        dlg = tk.Toplevel(parent)
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=16, pady=14)
        frame.pack(fill=tk.BOTH, expand=True)

        # 來源名稱
        tk.Label(frame, text="來源名稱：").grid(row=0, column=0, sticky=tk.W, pady=5)
        self._name = tk.StringVar(value=feed.get("name", "") if feed else "")
        tk.Entry(frame, textvariable=self._name, width=42).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, pady=5
        )

        # URL
        tk.Label(frame, text="URL：").grid(row=1, column=0, sticky=tk.W, pady=5)
        self._url = tk.StringVar(value=feed.get("url", "") if feed else "")
        tk.Entry(frame, textvariable=self._url, width=36).grid(
            row=1, column=1, sticky=tk.EW, pady=5
        )
        tk.Button(frame, text="抓取標題", command=self._fetch_title).grid(
            row=1, column=2, padx=(6, 0)
        )

        # 分類
        tk.Label(frame, text="分類：").grid(row=2, column=0, sticky=tk.W, pady=5)
        default_section = feed.get("section", sections[0] if sections else "") if feed else (sections[0] if sections else "")
        self._section = tk.StringVar(value=default_section)
        ttk.Combobox(frame, textvariable=self._section, values=sections, width=39).grid(
            row=2, column=1, columnspan=2, sticky=tk.EW, pady=5
        )

        # 自動翻譯
        self._translate = tk.BooleanVar(value=feed.get("auto_translate", False) if feed else False)
        tk.Checkbutton(frame, text="啟用自動翻譯", variable=self._translate).grid(
            row=3, column=1, sticky=tk.W, pady=5
        )

        # 按鈕列
        btn_row = tk.Frame(frame)
        btn_row.grid(row=4, column=0, columnspan=3, pady=(10, 2))
        tk.Button(btn_row, text="確定", width=10, command=lambda: self._ok(dlg)).pack(
            side=tk.LEFT, padx=6
        )
        tk.Button(btn_row, text="取消", width=10, command=dlg.destroy).pack(
            side=tk.LEFT, padx=6
        )

        frame.columnconfigure(1, weight=1)
        self._dlg = dlg
        dlg.wait_window()

    def _fetch_title(self):
        url = self._url.get().strip()
        if not url:
            messagebox.showwarning("提示", "請先填入 URL", parent=self._dlg)
            return
        try:
            parsed = feedparser.parse(url)
            title = parsed.feed.get("title", "")
            if title:
                self._name.set(title)
            else:
                messagebox.showinfo("提示", "無法從 RSS 取得標題", parent=self._dlg)
        except Exception as e:
            messagebox.showerror("錯誤", f"抓取失敗：{e}", parent=self._dlg)

    def _ok(self, dlg):
        url = self._url.get().strip()
        if not url:
            messagebox.showwarning("提示", "URL 不能為空", parent=dlg)
            return
        name = self._name.get().strip() or url
        section = self._section.get().strip() or "未分類"
        self.result = {
            "name": name,
            "url": url,
            "section": section,
            "auto_translate": self._translate.get(),
        }
        dlg.destroy()


# ---------------------------------------------------------------------------
# Section management dialog
# ---------------------------------------------------------------------------

class SectionDialog:
    def __init__(self, parent, feeds):
        self.feeds = [f.copy() for f in feeds]
        self.changed = False

        dlg = tk.Toplevel(parent)
        dlg.title("管理分類")
        dlg.geometry("340x280")
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.grab_set()

        frame = tk.Frame(dlg, padx=14, pady=14)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="分類清單（點兩下重新命名）：").pack(anchor=tk.W)

        list_frame = tk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self._listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.bind("<Double-1>", lambda _e: self._rename(dlg))

        btn_row = tk.Frame(frame)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="重新命名", command=lambda: self._rename(dlg)).pack(
            side=tk.LEFT, padx=3
        )
        tk.Button(btn_row, text="關閉", command=dlg.destroy).pack(side=tk.RIGHT, padx=3)

        self._refresh_list()
        dlg.wait_window()

    def _sections(self):
        seen = []
        for f in self.feeds:
            s = f.get("section", "未分類")
            if s not in seen:
                seen.append(s)
        return seen

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        counts = {}
        for f in self.feeds:
            s = f.get("section", "未分類")
            counts[s] = counts.get(s, 0) + 1
        for s in self._sections():
            self._listbox.insert(tk.END, f"{s}  ({counts.get(s, 0)} 個來源)")

    def _rename(self, parent):
        sel = self._listbox.curselection()
        if not sel:
            return
        sections = self._sections()
        old = sections[sel[0]]
        new = simpledialog.askstring("重新命名", "新分類名稱：", initialvalue=old, parent=parent)
        if new and new.strip() and new.strip() != old:
            new = new.strip()
            for f in self.feeds:
                if f.get("section") == old:
                    f["section"] = new
            self.changed = True
            self._refresh_list()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class RssManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RSS 來源管理")
        self.root.geometry("960x580")
        self.root.minsize(700, 400)

        self._feeds = []
        self._history = {}
        self._dirty = False
        self._sync_proc = None

        self._build_ui()
        self._load_data()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.root, pady=6, padx=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        for text, cmd in [
            ("新增來源", self._add_feed),
            ("編輯", self._edit_feed),
            ("刪除", self._delete_feed),
            ("管理分類", self._manage_sections),
        ]:
            tk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=3)

        self._sync_btn = tk.Button(toolbar, text="立即同步", command=self._sync_now)
        self._sync_btn.pack(side=tk.RIGHT, padx=3)

        # Treeview
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=6)

        cols = ("name", "url", "last_sync", "count", "translate")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", selectmode="browse")

        self._tree.heading("#0", text="")
        self._tree.heading("name", text="來源名稱")
        self._tree.heading("url", text="URL")
        self._tree.heading("last_sync", text="最近同步")
        self._tree.heading("count", text="已追蹤")
        self._tree.heading("translate", text="自動翻譯")

        self._tree.column("#0", width=14, minwidth=14, stretch=False)
        self._tree.column("name", width=220, minwidth=100)
        self._tree.column("url", width=380, minwidth=150)
        self._tree.column("last_sync", width=130, minwidth=100, anchor=tk.CENTER)
        self._tree.column("count", width=70, minwidth=50, anchor=tk.CENTER)
        self._tree.column("translate", width=70, minwidth=50, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.tag_configure("section", background="#e8ecf0", font=("", 10, "bold"))
        self._tree.bind("<Double-1>", lambda _e: self._edit_feed())

        # Status bar
        status_bar = tk.Frame(self.root, pady=5, padx=6)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_lbl = tk.Label(status_bar, text="", anchor=tk.W)
        self._status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        for text, cmd in [("儲存", self._save), ("重新載入", self._reload)]:
            tk.Button(status_bar, text=text, command=cmd).pack(side=tk.RIGHT, padx=3)

    # -----------------------------------------------------------------------
    # Data loading / refreshing
    # -----------------------------------------------------------------------

    def _load_data(self):
        self._feeds = load_feeds()
        self._history = load_history()
        self._refresh_tree()
        self._refresh_status()
        self._dirty = False
        self._update_title()

    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())

        # Group by section, preserving order
        section_order = []
        groups: dict[str, list] = {}
        for i, feed in enumerate(self._feeds):
            s = feed.get("section", "未分類")
            if s not in groups:
                groups[s] = []
                section_order.append(s)
            groups[s].append((i, feed))

        for si, section in enumerate(section_order):
            s_iid = f"s_{si}"
            self._tree.insert(
                "", tk.END, iid=s_iid,
                values=(section, "", "", "", ""),
                open=True,
                tags=("section",),
            )
            for fi, (idx, feed) in enumerate(groups[section]):
                url = feed.get("url", "")
                h = self._history.get(url, {})
                last_sync = format_last_sync(h.get("last_sync"))
                count = len(h.get("entries", []))
                short_url = url.replace("https://", "").replace("http://", "")
                translate_mark = "✓" if feed.get("auto_translate") else ""
                self._tree.insert(
                    s_iid, tk.END, iid=f"f_{idx}",
                    values=(feed.get("name", ""), short_url, last_sync, count, translate_mark),
                    tags=("feed",),
                )

    def _refresh_status(self):
        latest = None
        for h in self._history.values():
            ls = h.get("last_sync")
            if ls:
                try:
                    dt = datetime.fromisoformat(ls)
                    if latest is None or dt > latest:
                        latest = dt
                except Exception:
                    pass

        if latest:
            self._status_lbl.config(
                text=f"全域最近同步：{latest.astimezone().strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            self._status_lbl.config(text="尚未進行任何同步")

    def _update_title(self):
        self.root.title(("* " if self._dirty else "") + "RSS 來源管理")

    def _mark_dirty(self):
        self._dirty = True
        self._update_title()

    # -----------------------------------------------------------------------
    # Selection helper
    # -----------------------------------------------------------------------

    def _selected_feed_index(self):
        sel = self._tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if not iid.startswith("f_"):
            return None
        return int(iid[2:])

    def _sections(self):
        seen = []
        for f in self._feeds:
            s = f.get("section", "未分類")
            if s not in seen:
                seen.append(s)
        return seen

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _add_feed(self):
        dlg = FeedDialog(self.root, "新增來源", sections=self._sections())
        if dlg.result:
            self._feeds.append(dlg.result)
            self._refresh_tree()
            self._mark_dirty()

    def _edit_feed(self):
        idx = self._selected_feed_index()
        if idx is None:
            messagebox.showinfo("提示", "請先選擇一個來源")
            return
        dlg = FeedDialog(self.root, "編輯來源", feed=self._feeds[idx], sections=self._sections())
        if dlg.result:
            self._feeds[idx] = dlg.result
            self._refresh_tree()
            self._mark_dirty()

    def _delete_feed(self):
        idx = self._selected_feed_index()
        if idx is None:
            messagebox.showinfo("提示", "請先選擇一個來源")
            return
        name = self._feeds[idx].get("name", self._feeds[idx].get("url", ""))
        if messagebox.askyesno("確認刪除", f"確定要刪除「{name}」嗎？"):
            self._feeds.pop(idx)
            self._refresh_tree()
            self._mark_dirty()

    def _manage_sections(self):
        dlg = SectionDialog(self.root, self._feeds)
        if dlg.changed:
            self._feeds = dlg.feeds
            self._refresh_tree()
            self._mark_dirty()

    def _save(self):
        save_feeds(self._feeds)
        self._dirty = False
        self._update_title()

    def _reload(self):
        if self._dirty:
            if not messagebox.askyesno("確認", "有未儲存的變更，確定要放棄並重新載入嗎？"):
                return
        self._load_data()

    def _sync_now(self):
        if self._sync_proc and self._sync_proc.poll() is None:
            messagebox.showinfo("提示", "同步仍在進行中，請稍候…")
            return
        self._sync_btn.config(state=tk.DISABLED, text="同步中…")
        self._status_lbl.config(text="正在同步中，請稍候…")
        self._sync_proc = subprocess.Popen(
            [find_uv(), "run", "rss.py"],
            cwd=BASE_DIR,
        )
        threading.Thread(target=self._wait_for_sync, daemon=True).start()

    def _wait_for_sync(self):
        self._sync_proc.wait()
        self.root.after(0, self._on_sync_done)

    def _on_sync_done(self):
        self._sync_btn.config(state=tk.NORMAL, text="立即同步")
        self._history = load_history()
        self._refresh_tree()
        self._refresh_status()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    RssManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
