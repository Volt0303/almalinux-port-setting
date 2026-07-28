"""gui.py - thin Tkinter front-end over the shared core pipeline (spec 10).

Operator flow:  choose file  ->  pick serial  ->  [設定開始]  ->  OK/NG table.
ALL logic lives in ipset.core.*; this module only renders and calls it, so
CLI and GUI always behave identically.

Requires python3-tkinter on the target (not in AlmaLinux minimal):
    sudo dnf install -y python3-tkinter

Apply runs on a worker thread; results are marshalled back with .after().

Production conveniences (requested by the customer):
  * serial field is type-to-filter (enter part of a serial, pick from
    the candidate list) - faster for 400-unit production.
  * the run log is written to the operator's Desktop.
  * after a real commit+log, closing the window offers to self-uninstall
    the tool (reduces the pre-shipping cleanup work).

Python 3.9 compatible.
"""
from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import loader, pipeline
from .core.applier import Applier, load_port_map
from .core.compare import summarize
from .core.logwriter import LogWriter, build_rows
from .core.reader import Reader

DEFAULT_CONFIG = os.path.join("config", "config_intel.ini")
LOG_NAME = "result.csv"
INSTALL_DIR = "/opt/ipset"


# --------------------------------------------------------------------------
# Environment helpers (locale-aware Desktop, real user under sudo)
# --------------------------------------------------------------------------
def _real_home() -> str:
    """Home of the invoking user (not root, when launched via sudo)."""
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
    if user:
        try:
            import pwd
            return pwd.getpwnam(user).pw_dir
        except (KeyError, ImportError):
            pass
    return os.path.expanduser("~")


def desktop_dir() -> str:
    """The operator's Desktop folder (Japanese or English), else home."""
    home = _real_home()
    for name in ("デスクトップ", "Desktop"):
        d = os.path.join(home, name)
        if os.path.isdir(d):
            return d
    return home


def _chown_to_user(path: str) -> None:
    """When running as root (sudo), hand a created file back to the user."""
    try:
        user = os.environ.get("SUDO_USER")
        if user and hasattr(os, "geteuid") and os.geteuid() == 0:
            import pwd
            pw = pwd.getpwnam(user)
            os.chown(path, pw.pw_uid, pw.pw_gid)
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def uninstall_tool(remove_log: bool, log_path=None):
    """Remove the installed tool from this machine. Returns [error, ...].

    Needs root for /opt/ipset and /etc/sudoers.d (the GUI runs under sudo).
    The Desktop log is kept unless remove_log is True.
    """
    targets = []
    if os.path.isdir(INSTALL_DIR):
        targets.append(INSTALL_DIR)
    targets.append("/usr/local/share/applications/ipset-gui.desktop")
    targets.append("/etc/sudoers.d/ipset")
    targets.append(os.path.join(desktop_dir(), "ipset-gui.desktop"))
    if remove_log and log_path:
        targets.append(log_path)

    errors = []
    for t in targets:
        try:
            if os.path.isdir(t):
                shutil.rmtree(t, ignore_errors=True)
            elif os.path.lexists(t):
                os.remove(t)
        except OSError as e:
            errors.append("%s: %s" % (t, e))
    return errors


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("6ポートLAN IP設定ツール")
        self.geometry("720x560")
        self._load_result = None
        self._busy = False
        self._all_serials = []
        self._commit_done = False       # a real commit+log completed this session
        self._commit_log_path = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- layout ---------------------------------------------------------
    def _build(self):
        pad = {"padx": 6, "pady": 4}

        top = ttk.Frame(self); top.pack(fill="x", **pad)
        ttk.Label(top, text="設定ファイル:").grid(row=0, column=0, sticky="w")
        self.file_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.file_var, width=58).grid(row=0, column=1, sticky="we")
        ttk.Button(top, text="参照...", command=self._browse).grid(row=0, column=2)

        ttk.Label(top, text="設定INI:").grid(row=1, column=0, sticky="w")
        self.config_var = tk.StringVar(value=DEFAULT_CONFIG)
        ttk.Entry(top, textvariable=self.config_var, width=58).grid(row=1, column=1, sticky="we")

        ttk.Label(top, text="対象シリアル:").grid(row=2, column=0, sticky="w")
        self.serial_var = tk.StringVar()
        self.serial_entry = ttk.Entry(top, textvariable=self.serial_var, width=32)
        self.serial_entry.grid(row=2, column=1, sticky="w")
        self.serial_entry.bind("<KeyRelease>", self._on_serial_key)
        self.serial_entry.bind("<Down>", self._serial_down)
        ttk.Label(top, text="（一部入力で候補表示）", foreground="#666").grid(
            row=2, column=2, sticky="w")
        top.columnconfigure(1, weight=1)

        # floating candidate list (overlaid with place(); does not reflow layout)
        self.serial_list = tk.Listbox(self, height=6, exportselection=False)
        self.serial_list.bind("<<ListboxSelect>>", self._pick_serial)
        self.serial_list.bind("<Return>", self._pick_serial)
        self.serial_list.bind("<Escape>", lambda e: self._hide_serial_list())

        # expected values
        ttk.Label(self, text="設定内容（期待値）").pack(anchor="w", **pad)
        self.exp_tree = self._make_tree(("LAN", "IF", "IP/Prefix"), heights=6)

        # actions
        act = ttk.Frame(self); act.pack(fill="x", **pad)
        self.dry_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(act, text="ドライラン（変更しない）", variable=self.dry_var).pack(side="left")
        self.start_btn = ttk.Button(act, text="設定開始", command=self._start)
        self.start_btn.pack(side="right")

        # results
        ttk.Label(self, text="設定結果").pack(anchor="w", **pad)
        self.res_tree = self._make_tree(("Port", "期待値", "実際値", "結果"), heights=7)
        self.res_tree.tag_configure("ok", foreground="green")
        self.res_tree.tag_configure("ng", foreground="red")

        self.status = tk.StringVar(value="ファイルを選択してください。")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(
            fill="x", side="bottom")

    def _make_tree(self, cols, heights):
        tree = ttk.Treeview(self, columns=cols, show="headings", height=heights)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=160 if c not in ("LAN", "Port", "結果") else 80)
        tree.pack(fill="x", padx=6)
        return tree

    # ---- serial type-to-filter -----------------------------------------
    def _on_serial_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right",
                            "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        txt = self.serial_var.get().strip()
        low = txt.lower()
        matches = [s for s in self._all_serials if low in s.lower()] if txt \
            else list(self._all_serials)

        self.serial_list.delete(0, "end")
        for s in matches:
            self.serial_list.insert("end", s)

        # exact full match -> hide list and show its expected values
        if txt in self._all_serials:
            self._hide_serial_list()
            self._show_expected()
        elif matches:
            self._show_serial_list(len(matches))
        else:
            self._hide_serial_list()
            self.exp_tree.delete(*self.exp_tree.get_children())

    def _show_serial_list(self, count):
        self.update_idletasks()
        x = self.serial_entry.winfo_rootx() - self.winfo_rootx()
        y = (self.serial_entry.winfo_rooty() - self.winfo_rooty()
             + self.serial_entry.winfo_height())
        w = self.serial_entry.winfo_width()
        self.serial_list.configure(height=min(6, max(1, count)))
        self.serial_list.place(x=x, y=y, width=w)
        self.serial_list.lift()

    def _hide_serial_list(self):
        self.serial_list.place_forget()

    def _serial_down(self, event):
        if self.serial_list.winfo_ismapped() and self.serial_list.size() > 0:
            self.serial_list.focus_set()
            self.serial_list.selection_clear(0, "end")
            self.serial_list.selection_set(0)
            self.serial_list.activate(0)
            return "break"

    def _pick_serial(self, event):
        sel = self.serial_list.curselection()
        if not sel:
            return
        value = self.serial_list.get(sel[0])
        self.serial_var.set(value)
        self._hide_serial_list()
        self.serial_entry.focus_set()
        self.serial_entry.icursor("end")
        self._show_expected()

    # ---- actions --------------------------------------------------------
    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV/Excel", "*.csv *.xlsx"), ("All", "*.*")])
        if path:
            self.file_var.set(path)
            self._load_file()

    def _load_file(self):
        res = loader.load(self.file_var.get())
        for w in res.warnings:
            self.status.set("警告: " + w)
        if not res.ok:
            messagebox.showerror("読込エラー", "\n".join(res.errors))
            return
        self._load_result = res
        self._all_serials = sorted(res.machines)
        self._hide_serial_list()
        if self._all_serials:
            self.serial_var.set(self._all_serials[0])
            self._show_expected()

    def _show_expected(self):
        self.exp_tree.delete(*self.exp_tree.get_children())
        m = self._current_machine()
        if not m:
            return
        try:
            port_map = load_port_map(self.config_var.get())
        except Exception:  # noqa: BLE001
            port_map = {}
        for row in m.ports:
            ifname = port_map.get(row.con_name, row.ifname) or "?"
            self.exp_tree.insert("", "end",
                                 values=(row.con_name, ifname,
                                         "%s / %s" % (row.ip_address, row.subnet)))

    def _current_machine(self):
        if not self._load_result:
            return None
        return self._load_result.machines.get(self.serial_var.get().strip())

    def _start(self):
        if self._busy:
            return
        m = self._current_machine()
        if not m:
            messagebox.showwarning("未選択", "ファイルとシリアルを選択してください。")
            return
        try:
            port_map = load_port_map(self.config_var.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("設定INIエラー", str(e))
            return
        commit = not self.dry_var.get()
        if commit and not messagebox.askyesno(
                "確認", "実際に設定を適用します。よろしいですか？"):
            return
        self._busy = True
        self.start_btn.config(state="disabled")
        self.status.set("設定中…")
        self.res_tree.delete(*self.res_tree.get_children())
        threading.Thread(target=self._worker, args=(m, port_map, commit),
                         daemon=True).start()

    def _worker(self, machine, port_map, commit):
        """Runs off the UI thread."""
        applier = Applier(dry_run=not commit)
        reader = Reader()
        if commit:
            pairs = pipeline.commit_machine(machine, port_map, applier, reader)
            log_path = None
            try:
                lw = LogWriter(os.path.join(desktop_dir(), LOG_NAME))
                lw.write(build_rows(machine.sn, pairs, lw.now()))
                _chown_to_user(lw.path)
                log_path = lw.path
            except Exception as e:  # noqa: BLE001
                log_path = "ログ保存失敗: %s" % e
        else:
            # dry-run: show planned commands as the "actual" column
            pairs = pipeline.dry_plan(machine, port_map, applier)
            log_path = None
        self.after(0, lambda: self._render(pairs, commit, log_path))

    def _render(self, pairs, commit, log_path):
        if commit:
            comparisons = [c for _, c in pairs]
            for c in comparisons:
                tag = "ok" if c.ok else "ng"
                self.res_tree.insert("", "end", tags=(tag,),
                                     values=(c.con_name, c.expected, c.actual,
                                             "OK" if c.ok else "NG"))
            ok, ng, all_ok = summarize(comparisons)
            msg = "結果: %s (OK=%d NG=%d)" % ("PASS" if all_ok else "FAIL", ok, ng)
            # a real, saved log enables the self-uninstall-on-close flow
            if log_path and not log_path.startswith("ログ保存失敗"):
                self._commit_done = True
                self._commit_log_path = log_path
                msg += "   ログ: %s" % log_path
            elif log_path:
                msg += "   %s" % log_path
            self.status.set(msg)
        else:
            for con_name, rp, cmds, err in pairs:
                actual = err if err else " ; ".join(cmds)
                tag = "ng" if err else "ok"
                self.res_tree.insert("", "end", tags=(tag,),
                                     values=(con_name, rp.cidr if rp else "-",
                                             actual, "PLAN"))
            self.status.set("ドライラン完了（変更なし）。")
        self._busy = False
        self.start_btn.config(state="normal")

    # ---- close / self-uninstall ----------------------------------------
    def _on_close(self):
        # only offer uninstall once real settings were applied AND logged
        if not self._commit_done:
            self.destroy()
            return
        ans = messagebox.askyesnocancel(
            "終了",
            "検査を終了します。\n\n"
            "このツールをこの端末から削除（アンインストール）しますか？\n\n"
            "・「はい」　　：ツールを削除して終了します\n"
            "・「いいえ」　：削除せず終了します\n"
            "・「キャンセル」：終了しません")
        if ans is None:
            return  # cancel -> keep window open
        if not ans:
            self.destroy()  # close without uninstalling
            return
        remove_log = messagebox.askyesno(
            "ログの削除",
            "ログ（CSV）も削除しますか？\n\n"
            "・「いいえ」：ログはデスクトップに残します（推奨）\n"
            "・「はい」　：ログも削除します")
        errors = uninstall_tool(remove_log, self._commit_log_path)
        if errors:
            messagebox.showwarning(
                "削除", "一部を削除できませんでした:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("削除", "ツールを削除しました。")
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
