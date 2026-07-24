"""gui.py — thin Tkinter front-end over the shared core pipeline (spec 10).

Operator flow:  choose file  ->  pick serial  ->  [設定開始]  ->  OK/NG table.
ALL logic lives in ipset.core.*; this module only renders and calls it, so
CLI and GUI always behave identically.

Requires python3-tkinter on the target (not in AlmaLinux minimal):
    sudo dnf install -y python3-tkinter

Apply runs on a worker thread; results are marshalled back with .after().
Python 3.9 compatible.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import loader, pipeline
from .core.applier import Applier, load_port_map
from .core.compare import summarize
from .core.logwriter import LogWriter, build_rows
from .core.reader import Reader

DEFAULT_CONFIG = os.path.join("config", "config_intel.ini")
DEFAULT_LOG = os.path.join("logs", "result.csv")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("6ポートLAN IP設定ツール")
        self.geometry("720x560")
        self._load_result = None
        self._busy = False
        self._build()

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
        self.serial_cb = ttk.Combobox(top, textvariable=self.serial_var, state="readonly", width=30)
        self.serial_cb.grid(row=2, column=1, sticky="w")
        self.serial_cb.bind("<<ComboboxSelected>>", lambda e: self._show_expected())
        top.columnconfigure(1, weight=1)

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
        serials = sorted(res.machines)
        self.serial_cb["values"] = serials
        if serials:
            self.serial_var.set(serials[0])
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
        return self._load_result.machines.get(self.serial_var.get())

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
                lw = LogWriter(DEFAULT_LOG)
                lw.write(build_rows(machine.sn, pairs, lw.now()))
                log_path = lw.path
            except Exception as e:  # noqa: BLE001
                log_path = "ログ保存失敗: %s" % e
        else:
            # dry-run: show planned commands as the "actual" column
            plans = pipeline.dry_plan(machine, port_map, applier)
            pairs, log_path = [], None
            for con_name, rp, cmds, err in plans:
                pairs.append((con_name, rp, cmds, err))
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
            if log_path:
                msg += "   ログ: %s" % log_path
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


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
