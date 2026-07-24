#!/usr/bin/env python3
"""
LYWARE — desktop GUI (stage 3a: Accounts tab functional)
========================================================
Plain Tkinter, Windows-7-style squared chrome, four ribbons + central pane.
Stage 2 built the shell; stage 3a wires the ACCOUNTS tab to lyware.py:
real themed tables for the four subtabs, all tools (Deposit, Withdraw,
Recharge, Convert, Business Expense, Show Transactions, Make New Account/Card,
Hide, Show Batches, Transaction Query, Show Graph) with confirmation popups,
and sub-page navigation with a back button.

Inventory / Sales / Home graphs are wired in later stages (3b, 3c).

Run:  python3 lyware_gui.py   (needs schema.sql + lyware.py beside it)
Persistent DB (lyware_gui.db). Settings has Load-sample-data and Reset.
Icons are emoji placeholders.
"""

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json as _json
from decimal import Decimal, InvalidOperation
from datetime import datetime

import lyware as L
import lyware_reports as R

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyware_gui.db")


def _today():
    return datetime.now().strftime("%Y-%m-%d")

LOGO_BLUE = "#00AAD4"   # the brand blue, constant across light/dark

THEMES = {
    "light": dict(
        bg="#FFFFFF", ribbon="#E7EBEF", panel="#F3F5F7", content="#FFFFFF",
        ribbon2="#DDE3E8", topbar="#EDF0F3",
        accent="#00AAD4", accent_dark="#0089AC", on_accent="#FFFFFF",
        text="#1B1D21", muted="#697483", divider="#D3D7DD", border="#C7CCD3",
        hover="#DCE6EA", card="#FFFFFF", row_alt="#F4F8FA", muted_row="#9AA0A8",
        group="#E3F4F9", group2="#FBEFD6", scroll="#BCC6CE", scroll_trough="#EDF0F3", logo=LOGO_BLUE,
        group_border="#1C9DBE",
    ),
    "dark": dict(
        bg="#1E1E22", ribbon="#26262C", panel="#222228", content="#1A1A1E",
        ribbon2="#2C2C34", topbar="#222228",
        accent="#6A5BC9", accent_dark="#4F4199", on_accent="#F2F0FB",
        text="#E4E2EC", muted="#9B98A8", divider="#36343E", border="#3A3844",
        hover="#2E2C36", card="#26262C", row_alt="#202026", muted_row="#6E6B7A",
        group="#2A2740", group2="#3A2F26", scroll="#43414E", scroll_trough="#222228", logo=LOGO_BLUE,
        group_border="#8E7BE0",
    ),
}

TABS = [
    ("Home",      "\U0001F3E0", []),
    ("Listings",  "\U0001F4C8", ["Catalogue", "All Listings", "eBay Listings", "Amazon Listings",
                                  "Facebook Listings", "In-Person Listings"]),
    ("Accounts",  "\U0001F3E6", ["All Transactions", "Cash Accounts",
                                  "Digital Funds Accounts", "Card Accounts"]),
    ("Inventory", "\U0001F4E6", ["Current Inventory", "Pending For Approval",
                                  "Shipping To Shop", "Purchases"]),
    ("Sales",     "\U0001F4B5", ["Sales Orders", "Shipping To Customers", "Finalized Sales"]),
    ("Reports",   "\U0001F4CB", ["Overview", "Logistics", "Financials", "Market & Catalogue",
                                  "USD Rate", "Accounts & FX", "Losses & Returns", "Export"]),
]

TOOLS = {
    ("Listings", "Catalogue"): [("\u2795", "Add Item"), ("\u270F\uFE0F", "Edit Item"),
                              ("\U0001F4D1", "Make Similar Item"),
                              ("\U0001F5D1\uFE0F", "Delete Item"), ("\U0001F648", "Hide / Unhide Item"),
                              ("\U0001F516", "Manage Vocabulary"), ("\U0001F4C8", "Market Value")],
    ("Listings", "All Listings"): [("\u2795", "Add Listing"), ("\u270F\uFE0F", "Edit Listing"), ("\U0001F4E5", "Archive / Restore"), ("\U0001F5D1\uFE0F", "Delete Listing"), ("\U0001F9EE", "Value Breakdown")],
    ("Listings", "eBay Listings"): [("\u2795", "Add Listing"), ("\u270F\uFE0F", "Edit Listing"), ("\U0001F4E5", "Archive / Restore"), ("\U0001F5D1\uFE0F", "Delete Listing"), ("\U0001F9EE", "Value Breakdown")],
    ("Listings", "Amazon Listings"): [("\u2795", "Add Listing"), ("\u270F\uFE0F", "Edit Listing"), ("\U0001F4E5", "Archive / Restore"), ("\U0001F5D1\uFE0F", "Delete Listing"), ("\U0001F9EE", "Value Breakdown")],
    ("Listings", "Facebook Listings"): [("\u2795", "Add Listing"), ("\u270F\uFE0F", "Edit Listing"), ("\U0001F4E5", "Archive / Restore"), ("\U0001F5D1\uFE0F", "Delete Listing"), ("\U0001F9EE", "Value Breakdown")],
    ("Listings", "In-Person Listings"): [("\u2795", "Add Listing"), ("\u270F\uFE0F", "Edit Listing"), ("\U0001F4E5", "Archive / Restore"), ("\U0001F5D1\uFE0F", "Delete Listing"), ("\U0001F9EE", "Value Breakdown")],
    ("Accounts", "All Transactions"): [("\U0001F50D", "Transaction Query"), ("\U0001F4CA", "Show Graph"), ("\u21A9\uFE0F", "Reverse Transaction"), ("\u270F\uFE0F", "Edit Transaction")],
    ("Accounts", "Cash Accounts"): [
        ("\u2B07\uFE0F", "Deposit Capital"), ("\u2B06\uFE0F", "Withdraw Capital"),
        ("\U0001F4B3", "Recharge A Card"), ("\U0001F504", "Convert"),
        ("\U0001F9FE", "Record Business Expense"), ("\U0001F4DC", "Show Transactions"),
        ("\u2795", "Make New Account"), ("\u270F\uFE0F", "Edit Account"), ("\U0001F6AB", "Hide Account"), ("\U0001F5D1\uFE0F", "Delete Account")],
    ("Accounts", "Digital Funds Accounts"): [
        ("\u2B07\uFE0F", "Deposit Capital"), ("\u2B06\uFE0F", "Withdraw Capital"),
        ("\U0001F4B3", "Recharge A Card"), ("\U0001F504", "Convert"),
        ("\U0001F9FE", "Record Business Expense"), ("\U0001F4DC", "Show Transactions"),
        ("\u2795", "Make New Account"), ("\u270F\uFE0F", "Edit Account"), ("\U0001F6AB", "Hide Account"), ("\U0001F5D1\uFE0F", "Delete Account")],
    ("Accounts", "Card Accounts"): [
        ("\U0001F9F1", "Show Batches Explicitly"), ("\U0001F4DC", "Show Transactions"),
        ("\U0001F9FE", "Record Business Expense"), ("\u2795", "Make New Card"),
        ("\u270F\uFE0F", "Edit Account"), ("\U0001F6AB", "Hide Card"), ("\U0001F5D1\uFE0F", "Delete Account")],
    ("Inventory", "Current Inventory"): [("\U0001F6D2", "Sell Order"), ("\U0001F50E", "View Specs"), ("\U0001F9EE", "Cost Breakdown"), ("\U0001F3F7\uFE0F", "Set Condition"), ("\u21A9\uFE0F", "Undo Last Step"), ("\U0001F5D1\uFE0F", "Write Off (damaged)")],
    ("Inventory", "Pending For Approval"): [("\u2705", "Accept Into Inventory"),
                                            ("\U0001F50E", "View Specs"), ("\U0001F9EE", "Cost Breakdown"), ("\U0001F3F7\uFE0F", "Set Condition"), ("\u21A9\uFE0F", "Undo Last Step"), ("\u21AA\uFE0F", "Reject / Return"), ("\u274C", "Cancel Item (seller)")],
    ("Inventory", "Shipping To Shop"): [("\U0001F69A", "Update Shipping Status"),
                                        ("\U0001F50E", "View Specs"), ("\U0001F3F7\uFE0F", "Edit Tracking #"),
                                        ("\u2702\uFE0F", "Split Shipment"), ("\u274C", "Cancel Item (seller)")],
    ("Inventory", "Purchases"): [("\U0001F6D2", "Make Purchase"), ("\U0001F50E", "View Specs")],
    ("Sales", "Sales Orders"): [("\U0001F504", "Update Sale Status"), ("\u270F\uFE0F", "Edit Buyer"), ("\U0001F6AB", "Void Order")],
    ("Sales", "Shipping To Customers"): [("\U0001F69A", "Update Status")],
    ("Sales", "Finalized Sales"): [("\U0001F4E6", "Show Order Items"), ("\u21A9\uFE0F", "Customer Return")],
}

QUICKSTART = [("\U0001F6D2", "New Purchase"), ("\U0001F9FE", "New Sale Order"),
              ("\U0001F4B3", "Recharge Card"), ("\U0001F4CA", "Show Statistics")]

# default quickstart actions (M14: these are now editable & persisted)
QS_DEFAULT = ["dialog:New Purchase", "dialog:New Sale Order", "dialog:Recharge Card", "tab:Home"]


def build_action_registry():
    """All operations the quickstart can hold: tabs, subtabs, and tools (disambiguated)."""
    reg = []  # (action_id, emoji, label, group)
    reg.append(("dialog:New Purchase", "\U0001F6D2", "New Purchase", "Shortcuts"))
    reg.append(("dialog:New Sale Order", "\U0001F9FE", "New Sale Order", "Shortcuts"))
    reg.append(("dialog:Recharge Card", "\U0001F4B3", "Recharge Card", "Shortcuts"))
    for name, icon, subs in TABS:
        reg.append((f"tab:{name}", icon, name, "Tabs"))
        for s in subs:
            reg.append((f"sub:{name}:{s}", icon, f"{name} \u203A {s}", "Subtabs"))
    seen = set()
    for (tab, sub), tools in TOOLS.items():
        for emoji, label in tools:
            aid = f"tool:{tab}:{sub}:{label}"
            # disambiguate same-named tools across subtabs (e.g. Add eBay Listing)
            disp = label
            same = [k for k in TOOLS if any(l == label for _, l in TOOLS[k])]
            if len(same) > 1:
                disp = f"{label} ({sub})" if sub else label
                if label == "Add Listing" and sub:
                    disp = "Add " + sub.replace(" Listings", "") + " Listing"
            reg.append((aid, emoji, disp, f"Tools \u2014 {tab}"))
    return reg

HOME_STATS = ["Current inventory", "Items shipping to shop", "Sales",
              "Items shipping to customers", "Total revenue", "Total expenses"]

TABW, SUBW, QSW, TOPH, BOTH = 56, 172, 58, 44, 46


def D(x):
    return f"{L.money(x):,.2f}"


def _num(s, field="value", signed=False):
    try:
        d = Decimal(str(s).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field}: enter a number")
    if d < 0 and not signed:
        raise ValueError(f"{field}: must not be negative")
    return d


# ---- advanced table filter: AND / OR / TO, optional col: targeting ---------
FILTER_HELP = ("Filter syntax:\n"
               "  plain text  \u2014 matches any cell\n"
               "  a AND b     \u2014 both must match\n"
               "  a OR b      \u2014 either matches\n"
               "  100 TO 500  \u2014 numeric or date range\n"
               "  col:term    \u2014 restrict to a column (e.g. Amount:100 TO 500)")


def _filter_number(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _match_condition(values, columns, cond):
    cond = cond.strip()
    if not cond:
        return True
    cells = list(values)
    if ":" in cond:                              # column targeting
        col, rest = cond.split(":", 1)
        key = col.strip().lower()
        idx = next((i for i, c in enumerate(columns) if key == c.lower() or key in c.lower()), None)
        if idx is not None:
            cells = [values[idx]]
            cond = rest.strip()
    parts = re.split(r"\s+TO\s+", cond, flags=re.IGNORECASE)
    if len(parts) == 2:                          # range
        lo, hi = parts[0].strip(), parts[1].strip()
        lo_n, hi_n = _filter_number(lo), _filter_number(hi)
        if lo_n is not None and hi_n is not None:
            return any(_filter_number(c) is not None and lo_n <= _filter_number(c) <= hi_n for c in cells)
        return any(lo.lower() <= str(c).lower() <= hi.lower() for c in cells)
    term = cond.lower()                          # substring
    return any(term in str(c).lower() for c in cells)


def _sortkey(v):
    """Sort key that orders numbers numerically and text alphabetically, mixing safely.
    A cell like '75 \u26A0' (the Days column's slow-stock marker) still sorts as the
    number 75 — otherwise clicking Days would exile exactly the old items you're
    hunting for into a separate alphabetic group."""
    s = str(v).strip().replace(",", "")
    if s in ("", "\u2014"):
        return (2, "")
    try:
        return (0, float(s))
    except ValueError:
        pass
    head = s.split()[0] if s.split() else s
    try:
        return (0, float(head))
    except ValueError:
        return (1, str(v).lower())


def _modalize(win):
    """Make a Toplevel modal, but robust to minimize/restore (BUG3). A held grab on a
    window that gets iconified can leave the app unrestorable from the taskbar, so we
    release the grab whenever the window is unmapped and re-acquire it when it is shown."""
    try:
        win.update_idletasks()
    except Exception:
        pass

    def _grab(*_):
        try:
            if win.winfo_exists() and win.winfo_viewable():
                win.grab_set()
        except Exception:
            pass

    def _ungrab(*_):
        try:
            win.grab_release()
        except Exception:
            pass
    win.bind("<Map>", _grab, add="+")
    win.bind("<Unmap>", _ungrab, add="+")
    win.protocol("WM_DELETE_WINDOW", lambda: (_ungrab(), win.destroy()))
    win.bind("<Escape>", lambda e: (_ungrab(), win.destroy()))
    try:                                             # QOL8: dialogs open centred over the app,
        master = win.master or win                   # not wherever the window manager drops them
        win.update_idletasks()
        w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
        h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        x = max(0, mx + (mw - w) // 2)
        y = max(0, my + (mh - h) // 3)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = min(x, max(0, sw - w)); y = min(y, max(0, sh - h))
        win.geometry(f"+{x}+{y}")
    except Exception:
        pass
    _grab()


def _match_row(values, columns, query):
    query = query.strip()
    if not query:
        return True
    for group in re.split(r"\s+OR\s+", query, flags=re.IGNORECASE):
        conds = re.split(r"\s+AND\s+", group, flags=re.IGNORECASE)
        if all(_match_condition(values, columns, c) for c in conds):
            return True
    return False


# ---- tooltip (flips to the left when there's no room on the right) ----------
class Tip:
    def __init__(self, widget, text, theme):
        self.widget, self.text, self.theme, self.tip = widget, text, theme, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _=None):
        if self.tip or not self.text:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        tk.Label(self.tip, text=self.text, bg=self.theme["text"], fg=self.theme["bg"],
                 font=("Segoe UI", 9), padx=6, pady=2, bd=0).pack()
        self.tip.update_idletasks()
        tw = self.tip.winfo_reqwidth()
        screen_w = self.widget.winfo_screenwidth()
        right_x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
        y = self.widget.winfo_rooty() + 4
        x = self.widget.winfo_rootx() - tw - 6 if right_x + tw > screen_w else right_x
        self.tip.wm_geometry(f"+{max(0, x)}+{y}")

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ---- modal form: builds fields, enforces required, confirms before save -----
class SearchPickerDialog(tk.Toplevel):
    """Searchable, scrollable picker for LONG option lists (hundreds of attribute or
    category names) — typing filters live, Enter picks the single match, double-click or
    the Select button picks the highlighted one. Reusable anywhere a column or name must
    be chosen from a big vocabulary."""
    def __init__(self, app, title, options, on_pick, subtitle=None):
        super().__init__(app)
        self.app, self.t, self.on_pick = app, app.t, on_pick
        self._all = list(options)
        t = self.t
        self.configure(bg=t["bg"]); self.title(title); self.transient(app)
        tk.Label(self, text=title, bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(14, 0))
        if subtitle:
            tk.Label(self, text=subtitle, bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9),
                     wraplength=340, justify="left").pack(anchor="w", padx=18)
        btnbar = tk.Frame(self, bg=t["bg"]); btnbar.pack(side="bottom", fill="x")
        tk.Button(btnbar, text="Cancel", command=self.destroy, relief="solid", bd=1,
                  bg=t["panel"], fg=t["text"], width=9).pack(side="right", padx=18, pady=10)
        tk.Button(btnbar, text="Select", command=self._pick, relief="solid", bd=1,
                  bg=t["accent"], fg=t["on_accent"], width=10,
                  font=("Segoe UI Semibold", 10)).pack(side="right", pady=10)
        srow = tk.Frame(self, bg=t["bg"]); srow.pack(fill="x", padx=18, pady=(8, 4))
        tk.Label(srow, text="\u2315", bg=t["bg"], fg=t["muted"]).pack(side="left")
        self.q = tk.StringVar()
        ent = tk.Entry(srow, textvariable=self.q, bg=t["panel"], fg=t["text"], relief="solid",
                       bd=1, insertbackground=t["text"])
        ent.pack(side="left", fill="x", expand=True, padx=(6, 0))
        ent.bind("<KeyRelease>", lambda e: self._refill())
        ent.bind("<Return>", lambda e: self._enter())
        ent.bind("<Down>", lambda e: (self.lb.focus_set(), self.lb.selection_clear(0, "end"),
                                      self.lb.selection_set(0), self.lb.activate(0)))
        host = tk.Frame(self, bg=t["bg"]); host.pack(fill="both", expand=True, padx=18, pady=4)
        self.lb = tk.Listbox(host, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                             selectbackground=t["accent"], selectforeground=t["on_accent"],
                             font=("Segoe UI", 10), activestyle="none", height=14)
        sb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar",
                           command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.lb.bind("<Double-1>", lambda e: self._pick())
        self.lb.bind("<Return>", lambda e: self._pick())
        self._refill()
        self.geometry("380x430")
        _modalize(self)
        ent.focus_set()

    def _refill(self):
        q = self.q.get().strip().lower()
        self._shown = [o for o in self._all if q in o.lower()] if q else list(self._all)
        self.lb.delete(0, "end")
        for o in self._shown:
            self.lb.insert("end", o)
        if self._shown:
            self.lb.selection_clear(0, "end"); self.lb.selection_set(0)

    def _enter(self):
        if len(self._shown) == 1:
            self.on_pick(self._shown[0]); self.destroy()
        else:
            self._pick()

    def _pick(self):
        sel = self.lb.curselection()
        if not sel or not self._shown:
            return
        val = self._shown[sel[0]]
        self.on_pick(val); self.destroy()


class FormDialog(tk.Toplevel):
    """
    fields: list of dicts:
      {key, label, type: text|number|option|capped, values?, default?, required?,
       max?, info?}  ('capped' clamps numeric input to max live)
    on_submit(values) runs after an "are you sure" confirm; raise to show an error.
    """
    def __init__(self, app, title, fields, on_submit):
        super().__init__(app)
        self.app, self.theme, self.on_submit, self.fields = app, app.t, on_submit, fields
        self.title(title)
        self.configure(bg=self.theme["bg"])
        self.resizable(False, False)
        self.transient(app)
        self.bind("<Return>", lambda e: self._submit())      # Enter submits, Esc cancels
        self.vars = {}
        t = self.theme

        tk.Label(self, text=title, bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 10))
        # buttons pinned FIRST so a tall field list can never push them off-screen
        btns = tk.Frame(self, bg=t["bg"])
        btns.pack(side="bottom", fill="x", padx=20, pady=16)
        tk.Button(btns, text="Cancel", command=self.destroy, relief="solid", bd=1,
                  bg=t["panel"], fg=t["text"], width=10, font=("Segoe UI", 10),
                  activebackground=t["hover"]).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Done", command=self._submit, relief="solid", bd=1,
                  bg=t["accent"], fg=t["on_accent"], width=12, font=("Segoe UI Semibold", 10),
                  activebackground=t["accent_dark"]).pack(side="right")
        if len(fields) > 12:                       # pathological forms scroll; normal ones don't
            holder = tk.Frame(self, bg=t["bg"]); holder.pack(fill="both", expand=True, padx=20)
            body = app._scroll_host(holder)
            self._needs_scroll = True
        else:
            body = tk.Frame(self, bg=t["bg"])
            body.pack(fill="both", expand=True, padx=20)
            self._needs_scroll = False

        for spec in fields:
            if spec.get("type") == "info":
                tk.Label(body, text=spec["label"], bg=t["bg"], fg=t["muted"],
                         font=("Segoe UI", 10), anchor="w", justify="left",
                         wraplength=360).pack(fill="x", pady=(2, 6))
                continue
            row = tk.Frame(body, bg=t["bg"])
            row.pack(fill="x", pady=5)
            tk.Label(row, text=spec["label"], bg=t["bg"], fg=t["muted"], width=18,
                     anchor="w", font=("Segoe UI", 10)).pack(side="left")
            if spec.get("type") == "option":
                var = tk.StringVar(value=spec.get("default", spec["values"][0]))
                om = ttk.OptionMenu(row, var, var.get(), *spec["values"],
                                    command=spec.get("on_change"))
                om.pack(side="left", fill="x", expand=True)
            else:
                var = tk.StringVar(value=str(spec.get("default", "")))
                ent = tk.Entry(row, textvariable=var, bg=t["panel"], fg=t["text"],
                               insertbackground=t["text"], relief="solid", bd=1,
                               font=("Segoe UI", 10))
                ent.pack(side="left", fill="x", expand=True, ipady=2)
                if spec.get("type") == "capped":
                    self._attach_cap(var, spec)
            self.vars[spec["key"]] = var

        self.update_idletasks()                    # QOL: open centred over the app window,
        try:                                       # capped to the screen so Done stays reachable
            sh = self.winfo_screenheight()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            if self._needs_scroll or h > sh - 80:
                self.resizable(False, True)
                self.geometry(f"{max(w, 460)}x{sh - 80}")
                self.update_idletasks()
            x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
            y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        _modalize(self)

    def _attach_cap(self, var, spec):
        state = {"last": ""}

        def on_change(*_):
            val = var.get()
            if val in ("", ".", "-"):
                state["last"] = val
                return
            try:
                d = Decimal(val.replace(",", ""))
            except InvalidOperation:
                var.set(state["last"])
                return
            mx = spec.get("max")
            if mx is not None and d > Decimal(str(mx)):
                d = Decimal(str(mx))
                var.set(f"{d:.4f}".rstrip("0").rstrip("."))
            state["last"] = var.get()
        var.trace_add("write", on_change)

    def set_cap(self, key, new_max):
        for spec in self.fields:
            if spec.get("key") == key:
                spec["max"] = new_max

    def _submit(self):
        values = {}
        for spec in self.fields:
            if spec.get("type") == "info":
                continue
            v = self.vars[spec["key"]].get().strip()
            if spec.get("required") and not v:
                messagebox.showerror("Missing field", f"{spec['label']} is required.", parent=self)
                return
            values[spec["key"]] = v
        if not messagebox.askyesno("Confirm", "Are you sure?", parent=self):
            return
        try:
            self.on_submit(values)
            self.destroy()
        except Exception as e:  # noqa
            messagebox.showerror("Could not complete", str(e), parent=self)


# ===========================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LYWARE")
        self.conn = L.open_or_create_db(DB_FILE)
        geo = L.get_pref(self.conn, "win.geometry", None)   # open where you left off
        self.geometry(geo if geo and "x" in str(geo) else "1280x740")
        self.minsize(1100, 640)
        if L.get_pref(self.conn, "win.zoomed", "") == "1":
            try:
                self.state("zoomed")
            except Exception:
                pass
        try:
            L.make_backup(DB_FILE, reason="startup")
        except Exception:
            pass
        self.theme_name = L.get_pref(self.conn, "theme", "light") or "light"
        self.cur_tab, self.cur_sub = "Home", None
        self.qs_collapsed = False
        self.cur_table = None
        self.cur_acct_type = None
        try:
            self.view_flags = dict(_json.loads(L.get_pref(self.conn, "ui.view_flags", "") or "{}"))
        except Exception:
            self.view_flags = {}
        self.filter_memory = {}                       # per-view filter text (session)
        # keyboard shortcuts: Ctrl+F -> table filter, F5 -> refresh current view
        self.bind_all("<Control-f>", self._focus_filter)
        self.bind_all("<Control-F>", self._focus_filter)
        self.bind_all("<F5>", lambda e: self.refresh())
        self.logo_img = None
        try:
            _logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyware_logo_small.png")
            if os.path.exists(_logo):
                self.logo_img = tk.PhotoImage(file=_logo)
        except Exception:
            self.logo_img = None
        self._build()
        _lt = L.get_pref(self.conn, "ui.last_tab", "Home") or "Home"
        _ls = L.get_pref(self.conn, "ui.last_sub", None)
        try:
            self.select_tab(_lt if _lt in [n for n, _i, _s in TABS] else "Home")
            if _ls and self.cur_tab != "Home":
                subs = dict((n, ss) for n, _i, ss in TABS).get(self.cur_tab) or []
                if _ls in subs:
                    self.select_sub(_ls)
        except Exception:
            self.select_tab("Home")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def t(self):
        return THEMES[self.theme_name]

    # ---- ttk styling for tables -------------------------------------------
    def _setup_ttk_style(self):
        t = self.t
        st = ttk.Style(self)
        st.theme_use("default")
        st.configure("Treeview", background=t["card"], fieldbackground=t["card"],
                     foreground=t["text"], rowheight=28, borderwidth=0, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", background=t["ribbon2"], foreground=t["muted"],
                     relief="flat", borderwidth=1, font=("Segoe UI Semibold", 10))
        st.map("Treeview", background=[("selected", t["accent"])],
               foreground=[("selected", t["on_accent"])])
        st.map("Treeview.Heading", background=[("active", t["hover"])])
        # slim flat scrollbars (VIS2) — no arrows, themed trough
        for orient in ("Vertical", "Horizontal"):
            st.layout(f"Lyware.{orient}.TScrollbar", [
                (f"{orient}.Scrollbar.trough", {"children": [
                    (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
                 "sticky": "nswe"})])
            st.configure(f"Lyware.{orient}.TScrollbar", troughcolor=t["scroll_trough"],
                         background=t["scroll"], borderwidth=0, relief="flat",
                         arrowcolor=t["scroll_trough"], width=11)
            st.map(f"Lyware.{orient}.TScrollbar", background=[("active", t["accent"])])
        st.configure("Vertical.TScrollbar", background=t["scroll"], troughcolor=t["scroll_trough"],
                     borderwidth=0, arrowcolor=t["scroll_trough"], width=11)
        st.configure("Horizontal.TScrollbar", background=t["scroll"], troughcolor=t["scroll_trough"],
                     borderwidth=0, arrowcolor=t["scroll_trough"], width=11)
        st.configure("TMenubutton", background=t["panel"], foreground=t["text"],
                     relief="solid", borderwidth=1)
        st.configure("TCombobox", fieldbackground=t["panel"], background=t["panel"],
                     foreground=t["text"], arrowcolor=t["muted"], bordercolor=t["border"],
                     lightcolor=t["border"], darkcolor=t["border"])
        st.map("TCombobox", fieldbackground=[("readonly", t["panel"])],
               foreground=[("readonly", t["text"])], selectbackground=[("!focus", t["panel"])])
        self.option_add("*TCombobox*Listbox.background", t["panel"])
        self.option_add("*TCombobox*Listbox.foreground", t["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", t["on_accent"])
        self.option_add("*TCombobox*Listbox.font", "{Segoe UI} 10")

    # ---- build the frame ---------------------------------------------------
    def _build(self):
        t = self.t
        self.configure(bg=t["bg"])
        self._setup_ttk_style()

        self.top = tk.Frame(self, bg=t["topbar"], height=TOPH)
        self.top.pack(side="top", fill="x")
        self.top.pack_propagate(False)
        if self.logo_img is not None:
            tk.Label(self.top, image=self.logo_img, bg=t["topbar"]).pack(side="left", padx=14)
        else:
            tk.Label(self.top, text="LYWARE", bg=t["topbar"], fg=t["logo"],
                     font=("Segoe UI Semibold", 15)).pack(side="left", padx=14)
        for emoji, label, cmd in [
            ("\U0001F319", "Toggle light / dark", self.toggle_theme),
            ("\u2699\uFE0F", "Settings", self.open_settings),
            ("\U0001F4DC", "Change log", self.open_log),
        ][::-1]:
            b = tk.Label(self.top, text=emoji, bg=t["topbar"], fg=t["text"],
                         font=("Segoe UI Emoji", 14), padx=10, cursor="hand2")
            b.pack(side="right", padx=2)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            self._hover_fade(b, t["topbar"], t["hover"])
            Tip(b, label, t)

        self.body = tk.Frame(self, bg=t["bg"])
        self.body.pack(side="top", fill="both", expand=True)

        self.tabbar = tk.Frame(self.body, bg=t["ribbon"], width=TABW)
        self.tabbar.pack(side="left", fill="y")
        self.tabbar.pack_propagate(False)
        self.tab_widgets = {}
        self.tab_bubbles = {}
        for name, icon, subs in TABS:
            holder = tk.Frame(self.tabbar, bg=t["ribbon"])
            holder.pack(side="top", fill="x")
            lbl = tk.Label(holder, text=icon, bg=t["ribbon"], fg=t["text"],
                           font=("Segoe UI Emoji", 20), height=2, cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, n=name: self.select_tab(n))
            Tip(lbl, name, t)
            bub = tk.Label(holder, text="", bg="#D9534F", fg="#FFFFFF",
                           font=("Segoe UI Semibold", 7))
            self.tab_bubbles[name] = bub
            tk.Frame(self.tabbar, bg=t["divider"], height=1).pack(fill="x")
            self.tab_widgets[name] = lbl

        self.subbar = tk.Frame(self.body, bg=t["accent"], width=SUBW)
        self.subbar.pack_propagate(False)
        self.sub_widgets = {}

        self.qsbar = tk.Frame(self.body, bg=t["ribbon2"], width=QSW)
        self.qs_handle = tk.Frame(self.body, bg=t["ribbon2"], width=14)
        self._build_quickstart()

        self.center = tk.Frame(self.body, bg=t["bg"])
        self.bottombar = tk.Frame(self.center, bg=t["accent_dark"], height=BOTH)
        self.bottombar.pack(side="bottom", fill="x")
        self.bottombar.pack_propagate(False)
        self.content_wrap = tk.Frame(self.center, bg=t["content"])
        self.content_wrap.pack(side="top", fill="both", expand=True)
        self._repack_body()

    def _repack_body(self):
        for w in (self.subbar, self.qsbar, self.qs_handle, self.center):
            w.pack_forget()
        if self.cur_sub is not None and self._subs_for(self.cur_tab):
            self.subbar.pack(side="left", fill="y", after=self.tabbar)
        if self.qs_collapsed:
            self.qs_handle.pack(side="right", fill="y")
        else:
            self.qsbar.pack(side="right", fill="y")
        self.center.pack(side="left", fill="both", expand=True)

    def _qs_items(self):
        raw = L.get_pref(self.conn, "quickstart", None)
        ids = [x for x in raw.split("\u241F") if x] if raw else list(QS_DEFAULT)
        reg = {a: (e, lbl) for a, e, lbl, _ in build_action_registry()}
        return [(a, reg[a][0], reg[a][1]) for a in ids if a in reg]

    def _build_quickstart(self):
        t = self.t
        for w in self.qsbar.winfo_children() + self.qs_handle.winfo_children():
            w.destroy()
        cb = tk.Label(self.qsbar, text="\u00BB", bg=t["ribbon2"], fg=t["muted"],
                      font=("Segoe UI", 13), cursor="hand2")
        cb.pack(side="top", fill="x", pady=(6, 2))
        cb.bind("<Button-1>", lambda e: self.toggle_quickstart())
        Tip(cb, "Collapse quickstart", t)
        tk.Frame(self.qsbar, bg=t["divider"], height=1).pack(fill="x")
        for aid, emoji, label in self._qs_items():
            b = tk.Label(self.qsbar, text=emoji, bg=t["ribbon2"], fg=t["text"],
                         font=("Segoe UI Emoji", 18), height=2, cursor="hand2")
            b.pack(side="top", fill="x")
            b.bind("<Button-1>", lambda e, a=aid: self._run_action(a))
            self._hover_fade(b, t["ribbon2"], t["hover"])
            Tip(b, label, t)
            tk.Frame(self.qsbar, bg=t["divider"], height=1).pack(fill="x")
        plus = tk.Label(self.qsbar, text="\u2795", bg=t["ribbon2"], fg=t["muted"],
                        font=("Segoe UI Emoji", 13), height=2, cursor="hand2")
        plus.pack(side="bottom", fill="x")
        plus.bind("<Button-1>", lambda e: QuickstartEditor(self))
        self._hover_fade(plus, t["ribbon2"], t["hover"])
        Tip(plus, "Customize quickstart", t)
        eb = tk.Label(self.qs_handle, text="\u00AB", bg=t["ribbon2"], fg=t["muted"],
                      font=("Segoe UI", 13), cursor="hand2")
        eb.pack(side="top", fill="x", pady=(6, 2))
        eb.bind("<Button-1>", lambda e: self.toggle_quickstart())
        Tip(eb, "Show quickstart", t)

    def _run_action(self, aid):
        """Execute a quickstart action: a dialog shortcut, a tab/subtab jump, or a tool."""
        if aid.startswith("dialog:"):
            name = aid.split(":", 1)[1]
            if name == "New Purchase":
                MakePurchaseDialog(self)
            elif name == "New Sale Order":
                self.select_tab("Inventory"); self.select_sub("Current Inventory")
                messagebox.showinfo("New sale order",
                                    "Select one or more in-stock items, then use 'Sell Order'.", parent=self)
            elif name == "Recharge Card":
                self.select_tab("Accounts"); self.select_sub("Cash Accounts")
                messagebox.showinfo("Recharge", "Pick the funding account, then use 'Recharge A Card'.",
                                    parent=self)
        elif aid.startswith("tab:"):
            self.select_tab(aid.split(":", 1)[1])
        elif aid.startswith("sub:"):
            _, tab, sub = aid.split(":", 2)
            self.select_tab(tab); self.select_sub(sub)
        elif aid.startswith("tool:"):
            _, tab, sub, label = aid.split(":", 3)
            self.select_tab(tab)
            if sub:
                self.select_sub(sub)
            self._dispatch_tool(label)

    # ---- navigation --------------------------------------------------------
    def _subs_for(self, tab):
        return dict((n, s) for n, _, s in TABS)[tab]

    # ---- QOL7: logistics notification counts -------------------------------
    NOTIFY_SUBS = {
        ("Inventory", "Shipping To Shop"):
            "SELECT COUNT(*) FROM inventory_items i JOIN inventory_statuses st ON i.status=st.status "
            "WHERE st.stage='shipping'",
        ("Inventory", "Pending For Approval"):
            "SELECT COUNT(*) FROM inventory_items WHERE status='Pending Approval'",
        ("Sales", "Sales Orders"):
            "SELECT COUNT(*) FROM sales_orders WHERE status='Order Placed'",
        ("Sales", "Shipping To Customers"):
            "SELECT COUNT(*) FROM sales_orders WHERE status='Shipping'",
    }

    def _sub_count(self, tab, sub):
        sql = self.NOTIFY_SUBS.get((tab, sub))
        if not sql:
            return 0
        try:
            return self.conn.execute(sql).fetchone()[0]
        except Exception:
            return 0

    def _tab_has_alerts(self, tab):
        return any(self._sub_count(tab, s) > 0 for s in self._subs_for(tab))

    def _update_tab_bubbles(self):
        for name, bub in self.tab_bubbles.items():
            if self._tab_has_alerts(name):
                bub.configure(text="!")
                bub.place(relx=1.0, y=2, anchor="ne", x=-2)
            else:
                bub.place_forget()

    def select_tab(self, name):
        self.cur_tab = name
        subs = self._subs_for(name)
        self.cur_sub = subs[0] if subs else None
        for n, lbl in self.tab_widgets.items():
            on = (n == name)
            lbl.configure(bg=self.t["accent"] if on else self.t["ribbon"],
                          fg=self.t["on_accent"] if on else self.t["text"])
        self._update_tab_bubbles()
        self._build_subbar()
        self._repack_body()
        self._build_bottom()
        self._render_content()

    def _build_subbar(self):
        t = self.t
        for w in self.subbar.winfo_children():
            w.destroy()
        self.sub_widgets = {}
        subs = self._subs_for(self.cur_tab)
        if not subs:
            return
        tk.Label(self.subbar, text=self.cur_tab.upper(), bg=t["accent"], fg=t["on_accent"],
                 font=("Segoe UI Semibold", 10), anchor="w", padx=12).pack(fill="x", pady=(10, 6))
        for s in subs:
            holder = tk.Frame(self.subbar, bg=t["accent"])
            holder.pack(fill="x")
            lbl = tk.Label(holder, text=s, bg=t["accent"], fg=t["on_accent"], anchor="w",
                           padx=16, pady=8, font=("Segoe UI", 10), cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, n=s: self.select_sub(n))
            cnt = self._sub_count(self.cur_tab, s)
            if cnt > 0:
                bub = tk.Label(holder, text=str(cnt), bg="#D9534F", fg="#FFFFFF",
                               font=("Segoe UI Semibold", 8), padx=4)
                bub.place(relx=1.0, rely=0.5, anchor="e", x=-8)
                lbl.bind("<Button-1>", lambda e, n=s: self.select_sub(n), add="+")
            tk.Frame(self.subbar, bg=t["accent_dark"], height=1).pack(fill="x")
            self.sub_widgets[s] = lbl
        self._mark_subselection()

    def _mark_subselection(self):
        for s, lbl in self.sub_widgets.items():
            on = (s == self.cur_sub)
            lbl.configure(font=("Segoe UI", 10, "bold" if on else "normal"),
                          bg=self.t["accent_dark"] if on else self.t["accent"])

    def select_sub(self, name):
        self.cur_sub = name
        self._mark_subselection()
        self._build_bottom()
        self._render_content()

    def _build_bottom(self):
        t = self.t
        for w in self.bottombar.winfo_children():
            w.destroy()
        tools = TOOLS.get((self.cur_tab, self.cur_sub), [])
        if not tools:
            tk.Label(self.bottombar, text="", bg=t["accent_dark"]).pack(side="left", padx=8)
            self._backup_status_label(t)
            return
        for emoji, label in tools:
            b = tk.Label(self.bottombar, text=emoji, bg=t["accent_dark"], fg=t["on_accent"],
                         font=("Segoe UI Emoji", 15), padx=10, cursor="hand2")
            b.pack(side="left", padx=2, pady=4)
            b.bind("<Button-1>", lambda e, n=label: self._dispatch_tool(n))
            self._hoverable(b, t["accent_dark"], t["accent"])
            Tip(b, label, t)
        self._backup_status_label(t)

    def _backup_status_label(self, t):
        """QOL: keep the safety net visible — last backup time, click for Settings."""
        try:
            snaps = L.list_backups(DB_FILE)
            if snaps:
                from datetime import datetime as _dt
                ts = _dt.fromtimestamp(os.path.getmtime(snaps[0][0]))
                txt = ("Last backup: today " + ts.strftime("%H:%M")
                       if ts.date() == _dt.now().date()
                       else "Last backup: " + ts.strftime("%Y-%m-%d %H:%M"))
            else:
                txt = "No backups yet"
        except Exception:
            return
        lbl = tk.Label(self.bottombar, text=txt, bg=t["accent_dark"], fg=t["on_accent"],
                       font=("Segoe UI", 8), cursor="hand2")
        lbl.pack(side="right", padx=10)
        lbl.bind("<Button-1>", lambda e: self.open_settings())
        Tip(lbl, "Snapshots live in lyware_backups/ next to the database.\n"
                 "Click to open Settings (manual backup, export, restore).", t)

    # ---- tool dispatch -----------------------------------------------------
    def _dispatch_tool(self, label):
        handlers = {
            "Deposit Capital": self.tool_deposit,
            "Withdraw Capital": self.tool_withdraw,
            "Recharge A Card": self.tool_recharge,
            "Convert": self.tool_convert,
            "Record Business Expense": self.tool_business_expense,
            "Show Transactions": self.tool_show_transactions,
            "Reverse Transaction": self.tool_reverse_transaction,
            "Edit Transaction": self.tool_edit_transaction,
            "Make New Account": self.tool_make_account,
            "Make New Card": self.tool_make_card,
            "Hide Account": self.tool_hide_account,
            "Hide Card": self.tool_hide_account,
            "Show Batches Explicitly": self.tool_show_batches,
            "Transaction Query": self.tool_txn_query,
            "Show Graph": self.tool_show_graph,
            "Sell Order": self.tool_sell_order,
            "Accept Into Inventory": self.tool_accept_inventory,
            "Update Shipping Status": self.tool_update_shipping,
            "Make Purchase": self.tool_make_purchase,
            "Update Sale Status": self.tool_update_sale_status,
            "Update Status": self.tool_update_customer_status,
            "Add Listing": self.tool_add_listing,
            "Add Item": self.tool_add_catalog_item,
            "Edit Item": self.tool_edit_catalog_item,
            "Make Similar Item": self.tool_make_similar_item,
            "Set Condition": self.tool_set_condition,
            "Delete Item": self.tool_delete_catalog_item,
            "Hide / Unhide Item": self.tool_hide_catalog_item,
            "Edit Listing": self.tool_edit_listing,
            "Delete Listing": self.tool_delete_listing,
            "Edit Account": self.tool_edit_account,
            "Delete Account": self.tool_delete_account,
            "Edit Buyer": self.tool_edit_buyer,
            "Manage Vocabulary": self.tool_manage_vocab,
            "Value Breakdown": self.tool_listing_breakdown,
            "Cost Breakdown": self.tool_cost_breakdown,
            "Split Shipment": self.tool_split_shipment,
            "Edit Tracking #": self.tool_edit_tracking,
            "Show Order Items": self.tool_order_items,
            "Cancel Item (seller)": self.tool_cancel_item,
            "Reject / Return": self.tool_reject_item,
            "Write Off (damaged)": self.tool_write_off,
            "Customer Return": self.tool_customer_return,
            "Void Order": self.tool_void_order,
            "View Specs": self.tool_view_specs,
            "Archive / Restore": self.tool_archive_listing,
            "Undo Last Step": self.tool_undo_last_step,
            "Market Value": self.tool_market_value,
        }
        fn = handlers.get(label)
        if fn:
            fn()
        else:
            messagebox.showinfo("Tool", f"'{label}' is wired in a later stage.", parent=self)

    # ---- content scaffolding ----------------------------------------------
    def _scrollable(self, parent):
        t = self.t
        canvas = tk.Canvas(parent, bg=t["content"], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", style="Lyware.Vertical.TScrollbar",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=t["content"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 30), "units"))
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-2, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(2, "units"))
        return inner

    def _content_reset(self):
        for w in self.content_wrap.winfo_children():
            w.destroy()
        return self._scrollable(self.content_wrap)

    def _title(self, inner, text, subtitle=None):
        t = self.t
        tk.Label(inner, text=text, bg=t["content"], fg=t["text"],
                 font=("Segoe UI Semibold", 20), anchor="w").pack(fill="x", padx=24, pady=(18, 2))
        if subtitle:
            tk.Label(inner, text=subtitle, bg=t["content"], fg=t["muted"],
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=24, pady=(0, 8))

    def _render_content(self):
        self.cur_table = None
        inner = self._content_reset()
        crumb = self.cur_tab if self.cur_sub is None else f"{self.cur_tab}  \u203A  {self.cur_sub}"
        if self.cur_tab == "Accounts":
            self._render_accounts(inner, crumb)
        elif self.cur_tab == "Inventory":
            self._render_inventory(inner, crumb)
        elif self.cur_tab == "Sales":
            self._render_sales(inner, crumb)
        elif self.cur_tab == "Listings":
            self._render_listings(inner, crumb)
        elif self.cur_tab == "Reports":
            self._render_reports(inner, crumb)
        elif self.cur_tab == "Home":
            self._title(inner, "Home", "Balances and a snapshot of the business")
            self._render_home(inner)
        else:
            self._title(inner, crumb)

    # ---- Accounts rendering ------------------------------------------------
    def _render_accounts(self, inner, crumb):
        sub = self.cur_sub
        if sub == "All Transactions":
            self._title(inner, crumb, "Every transaction across all accounts")
            rows = []
            for r in self.conn.execute(
                    "SELECT t.trnsid, a.account_name, t.type, tt.category, t.amount, t.currency, t.date "
                    "FROM all_transactions t JOIN accounts a ON t.acctid=a.acctid "
                    "JOIN transaction_types tt ON t.type=tt.type ORDER BY t.trnsid DESC"):
                rows.append((str(r["trnsid"]),
                             (r["trnsid"], r["account_name"], r["type"], r["category"],
                              D(r["amount"]), r["currency"], r["date"])))
            self.cur_table = self._make_table(
                inner, ["ID", "Account", "Type", "Category", "Amount", "Cur", "Date"],
                [50, 170, 140, 90, 120, 60, 100], rows, multi=True)
        else:
            atype = {"Cash Accounts": "Cash", "Digital Funds Accounts": "Digital Funds",
                     "Card Accounts": "Card"}[sub]
            self.cur_acct_type = atype
            self._title(inner, crumb, f"Your {atype} accounts — highlight a row, then use a tool below")
            if atype == "Card":
                cols, widths = ["ID", "Card Name", "Type", "Balance USD", "Balance LYD", "Created"], \
                    [50, 220, 100, 130, 130, 100]
            else:
                cols, widths = ["ID", "Account Name", "Type", "Balance LYD", "Balance USD", "Created"], \
                    [50, 220, 120, 140, 140, 100]
            rows = []
            for a in L.list_accounts(self.conn, atype):
                lyd, usd = D(L.lyd_balance(self.conn, a["acctid"])), D(L.fx_balance(self.conn, a["acctid"], "USD"))
                created = (a["created_at"] or "")[:10] or "\u2014"
                vals = ((a["acctid"], a["account_name"], a["account_type"], usd, lyd, created) if atype == "Card"
                        else (a["acctid"], a["account_name"], a["account_type"], lyd, usd, created))
                rows.append((str(a["acctid"]), vals))
            self.cur_table = self._make_table(inner, cols, widths, rows)

    # ---- table builder with simple substring filter ------------------------
    def _make_table(self, parent, columns, widths, rows, multi=False, height=14, cols_button=None):
        t = self.t
        norm = [(r[0], tuple(r[1]), (len(r) > 2 and r[2]), (r[3] if len(r) > 3 else None)) for r in rows]
        has_groups = any(n[3] for n in norm)
        if has_groups:                                   # M1: leading bracket column for groups
            disp_cols = ["\u2502"] + list(columns)
            disp_widths = [24] + list(widths)
            data_off = 1
        else:
            disp_cols, disp_widths, data_off = list(columns), list(widths), 0

        bar = tk.Frame(parent, bg=t["content"])
        bar.pack(fill="x", padx=24, pady=(4, 2))
        tk.Label(bar, text="Filter:", bg=t["content"], fg=t["muted"],
                 font=("Segoe UI", 10)).pack(side="left")
        is_main = parent.winfo_toplevel() is self     # popups keep their own transient filters
        fkey = (self.cur_tab, self.cur_sub)
        fvar = tk.StringVar(value=(self.filter_memory.get(fkey, "") if is_main else ""))
        ent = tk.Entry(bar, textvariable=fvar, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                       insertbackground=t["text"], width=40, font=("Segoe UI", 10))
        ent.pack(side="left", padx=6, ipady=1)
        if is_main:                                   # QOL: the filter survives tab switching
            fvar.trace_add("write", lambda *_: self.filter_memory.__setitem__(fkey, fvar.get()))
        ent.bind("<Escape>", lambda e: (fvar.set(""), tree.focus_set()))
        self._filter_entry = ent                      # Ctrl+F focuses the current table's filter
        hint = tk.Label(bar, text="\u2753", bg=t["content"], fg=t["muted"],
                        font=("Segoe UI", 10), cursor="hand2")
        hint.pack(side="left")
        Tip(hint, FILTER_HELP, t)
        if cols_button:
            cb = tk.Button(bar, text="Columns \u25BE", command=cols_button, relief="solid", bd=1,
                           bg=t["panel"], fg=t["text"], font=("Segoe UI", 9))
            cb.pack(side="left", padx=(10, 0))
        count = tk.Label(bar, text=f"{len(norm)} row(s)", bg=t["content"], fg=t["muted"],
                         font=("Segoe UI", 9))
        count.pack(side="right")

        wrap = tk.Frame(parent, bg=t["content"], highlightthickness=1,
                        highlightbackground=t["border"], highlightcolor=t["border"])
        wrap.pack(fill="both", expand=True, padx=24, pady=(2, 16))
        tree = ttk.Treeview(wrap, columns=disp_cols, show="headings", height=height,
                            selectmode="extended" if multi else "browse")
        tree.tag_configure("muted", foreground=t["muted_row"])
        tree.tag_configure("odd", background=t["row_alt"])
        tree.tag_configure("even", background=t["card"])
        tree.tag_configure("group_a", background=t["group"])         # M1: alternating group shades
        tree.tag_configure("group_b", background=t["group2"])
        sort_state = {"col": None, "dir": None}

        def cycle_sort(di):                                          # M7: 3-state column sort
            if sort_state["col"] != di:
                sort_state["col"], sort_state["dir"] = di, "desc"
            else:
                sort_state["dir"] = {"desc": "asc", "asc": None, None: "desc"}[sort_state["dir"]]
                if sort_state["dir"] is None:
                    sort_state["col"] = None
            for j, c in enumerate(disp_cols):
                if has_groups and j == 0:
                    continue
                lbl = columns[j - data_off]
                if sort_state["col"] == j - data_off and sort_state["dir"]:
                    lbl += "  \u25BC" if sort_state["dir"] == "desc" else "  \u25B2"
                tree.heading(c, text=lbl)
            refresh_view()

        for j, (c, w) in enumerate(zip(disp_cols, disp_widths)):
            if has_groups and j == 0:
                tree.heading(c, text="")
                tree.column(c, width=w, anchor="center", stretch=False, minwidth=w)
            else:
                tree.heading(c, text=c, command=lambda di=j - data_off: cycle_sort(di))
                # last column stretches to absorb spare width so the table fills its frame
                # (no dead gap on the right) and resizing other columns reflows cleanly
                tree.column(c, width=w, anchor="w", stretch=(j == len(disp_cols) - 1),
                            minwidth=40)
        tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", style="Lyware.Vertical.TScrollbar", command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", style="Lyware.Horizontal.TScrollbar",
                            command=tree.xview)
        seps = []

        def reposition_seps():                                       # M8: vertical column separators
            # Whole body guarded: a pending after()/scroll callback can fire just after a
            # re-render destroyed this table — placing separators on a dead tree must be a
            # silent no-op, not a Tcl error.
            try:
                if not tree.winfo_exists():
                    return
                f0 = tree.xview()[0]; vw = tree.winfo_width()
                live = [tree.column(c, "width") for c in disp_cols]
                total = sum(live) or 1; offset = f0 * total
                xs, cum = [], 0
                for w in live[:-1]:                                  # live widths follow drag-resizing
                    cum += w; x = cum - offset
                    if 1 < x < vw - 1:
                        xs.append(x)
                while len(seps) < len(xs):                           # reuse frames -> no flicker on drag
                    seps.append(tk.Frame(wrap, bg=t["divider"]))
                while len(seps) > len(xs):
                    seps.pop().destroy()
                for ln, x in zip(seps, xs):
                    ln.place(in_=tree, x=x, y=0, relheight=1.0, width=1)
            except Exception:
                return

        def xscroll(*a):
            hsb.set(*a); reposition_seps()
        tree.configure(yscrollcommand=sb.set, xscrollcommand=xscroll)
        sb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        tree.bind("<Configure>", lambda e: reposition_seps(), add="+")
        # a column drag-resize emits motion/release on the tree but no Configure — track both
        tree.bind("<B1-Motion>", lambda e: reposition_seps(), add="+")
        tree.bind("<ButtonRelease-1>", lambda e: reposition_seps(), add="+")

        # Deduped, cancellable scheduling: the 12ms settle-timer is registered on the App at
        # Tcl level, so if the table (or the whole window) is torn down before it fires, Tcl
        # raises 'invalid command name' before any Python guard can run. Cancel on destroy.
        _sep_job = {"id": None}

        def _sched_seps():
            if _sep_job["id"] is not None:
                try:
                    self.after_cancel(_sep_job["id"])
                except Exception:
                    pass

            def _fire():
                _sep_job["id"] = None
                reposition_seps()
            try:
                _sep_job["id"] = self.after(12, _fire)
            except Exception:
                _sep_job["id"] = None

        def _cancel_seps(_e=None):
            if _sep_job["id"] is not None:
                try:
                    self.after_cancel(_sep_job["id"])
                except Exception:
                    pass
                _sep_job["id"] = None
        tree.bind("<Destroy>", _cancel_seps, add="+")

        group_parity = {}

        def parity(gid):
            if gid not in group_parity:
                group_parity[gid] = len(group_parity) % 2
            return group_parity[gid]

        def brackets_for(subset):
            out = []
            n = len(subset)
            for i, (_iid, _v, _m, gid) in enumerate(subset):
                if not gid:
                    out.append(""); continue
                top = (i == 0 or subset[i - 1][3] != gid)
                bot = (i == n - 1 or subset[i + 1][3] != gid)
                out.append("\u250C" if top and not bot else "\u2514" if bot and not top
                           else "\u2502" if not top else "\u25AA")
            return out

        def populate(subset):
            tree.delete(*tree.get_children())
            group_parity.clear()
            brk = brackets_for(subset) if has_groups else None
            for i, (iid, vals, muted, gid) in enumerate(subset):
                tags = []
                if gid:
                    tags.append("group_a" if parity(gid) == 0 else "group_b")
                else:
                    tags.append("odd" if i % 2 else "even")
                if muted:
                    tags.append("muted")
                rowvals = ((brk[i],) + tuple(vals)) if has_groups else tuple(vals)
                tree.insert("", "end", iid=iid, values=rowvals, tags=tuple(tags))
            _sched_seps()

        def current_view():
            q = fvar.get().strip()
            base = norm if not q else [r for r in norm if _match_row(r[1], columns, q)]
            ci = sort_state["col"]
            if ci is not None and sort_state["dir"]:
                base = sorted(base, key=lambda r: _sortkey(r[1][ci] if ci < len(r[1]) else ""),
                              reverse=(sort_state["dir"] == "desc"))
            return base

        def refresh_view():
            view = current_view()
            populate(view)
            count.configure(text=(f"{len(view)} row(s)" if len(view) == len(norm)
                                  else f"{len(view)} / {len(norm)} row(s)"))
        fvar.trace_add("write", lambda *_: refresh_view())

        def edit_cell(event):                                        # M9: in-cell cursor (select/copy)
            iid = tree.identify_row(event.y); col = tree.identify_column(event.x)
            if not iid or not col:
                return
            if has_groups and col == "#1":
                return
            box = tree.bbox(iid, col)
            if not box:
                return
            x, y, w, h = box
            val = tree.set(iid, col)
            ed = tk.Entry(tree, bg=t["card"], fg=t["text"], relief="solid", bd=1,
                          insertbackground=t["accent"], font=("Segoe UI", 10))
            ed.insert(0, val); ed.select_range(0, "end"); ed.icursor("end")
            ed.place(x=x, y=y, width=w, height=h); ed.focus_set()
            for ev in ("<FocusOut>", "<Escape>", "<Return>"):
                ed.bind(ev, lambda e: ed.destroy())
        tree.bind("<Double-1>", edit_cell, add="+")

        # --- QOL: live selection totals in the count label ---------------------------
        _money_words = ("cost", "value", "price", "revenue", "volume", "amount", "total")

        def _cellnum(v):
            try:
                return float(str(v).replace(",", "").replace("\u26A0", "").strip())
            except ValueError:
                return None

        def on_select(_e=None):
            sel = tree.selection()
            if len(sel) < 2:
                view = current_view()
                count.configure(text=(f"{len(view)} row(s)" if len(view) == len(norm)
                                      else f"{len(view)} / {len(norm)} row(s)"))
                return
            for j, h in enumerate(columns):
                if any(w in h.lower() for w in _money_words):
                    vals = [_cellnum(tree.item(i)["values"][j + data_off]) for i in sel]
                    nums = [v for v in vals if v is not None]
                    if nums:
                        count.configure(text=f"{len(sel)} selected \u00B7 {D(sum(nums))} ({h})")
                        return
            count.configure(text=f"{len(sel)} selected")
        tree.bind("<<TreeviewSelect>>", on_select, add="+")

        # --- QOL: right-click context menu (row tools + copy + jump to catalogue) ----
        def context_menu(event):
            iid = tree.identify_row(event.y)
            if not iid:
                return
            if iid not in tree.selection():
                tree.selection_set(iid)
            tree.focus(iid)
            col = tree.identify_column(event.x)
            menu = tk.Menu(tree, tearoff=0, bg=t["panel"], fg=t["text"],
                           activebackground=t["accent"], activeforeground=t["on_accent"])
            if tree is self.cur_table:
                for _icon, lbl in TOOLS.get((self.cur_tab, self.cur_sub), []):
                    menu.add_command(label=lbl, command=lambda n=lbl: self._dispatch_tool(n))
                if self.cur_tab == "Inventory":
                    menu.add_separator()
                    menu.add_command(label="Show in Catalogue",
                                     command=lambda: self._show_in_catalog_from_row(iid))
                menu.add_separator()

            def copy_cell():
                try:
                    v = tree.set(iid, col)
                except Exception:
                    v = ""
                self.clipboard_clear(); self.clipboard_append(str(v))

            def copy_row():
                vals = tree.item(iid)["values"][data_off:]
                self.clipboard_clear(); self.clipboard_append("\t".join(str(v) for v in vals))
            menu.add_command(label="Copy cell", command=copy_cell)
            menu.add_command(label="Copy row", command=copy_row)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        tree.bind("<Button-3>", context_menu, add="+")

        refresh_view()
        return tree

    def _show_in_catalog_from_row(self, iid):
        """Jump from an operational row to its catalogue entry (selected and visible)."""
        if self.cur_sub == "Purchases":
            r = self.conn.execute("SELECT catid FROM purchase_lines WHERE polnid=?", (iid,)).fetchone()
        else:
            r = self.conn.execute("SELECT catid FROM inventory_items WHERE lywrid=?", (iid,)).fetchone()
        if not r or r["catid"] is None:
            messagebox.showinfo("No catalogue link", "This row isn't linked to a catalogue item.",
                                parent=self)
            return
        catid = str(r["catid"])
        self.filter_memory[("Listings", "Catalogue")] = ""    # a stale filter could hide it
        self.select_tab("Listings"); self.select_sub("Catalogue")
        try:
            self.cur_table.selection_set(catid); self.cur_table.focus(catid); self.cur_table.see(catid)
        except Exception:  # noqa
            pass

    def _copy_popup(self, text):
        """QOL5: a small read-only selectable popup for copying a cell value."""
        t = self.t
        win = tk.Toplevel(self); win.title("Copy"); win.configure(bg=t["bg"]); win.transient(self)
        tk.Label(win, text="Select & copy (read-only)", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(10, 2))
        e = tk.Entry(win, bg=t["panel"], fg=t["text"], relief="solid", bd=1, width=max(20, min(len(text) + 4, 60)),
                     insertbackground=t["text"], font=("Consolas", 10))
        e.insert(0, text); e.configure(state="readonly")
        e.pack(padx=12, pady=4, ipady=2)

        def do_copy():
            self.clipboard_clear(); self.clipboard_append(text)
        tk.Button(win, text="Copy", command=do_copy, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=8).pack(side="right", padx=12, pady=8)
        tk.Button(win, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=8).pack(side="right", pady=8)
        _modalize(win)

    def _toggle_bar(self, inner, key, label):
        t = self.t
        bar = tk.Frame(inner, bg=t["content"])
        bar.pack(fill="x", padx=24, pady=(2, 0))
        var = tk.BooleanVar(value=self.view_flags.get(key, False))

        def on():
            self.view_flags[key] = var.get()
            self._render_content()
        tk.Checkbutton(bar, text=label, variable=var, command=on, bg=t["content"], fg=t["muted"],
                       selectcolor=t["panel"], activebackground=t["content"], activeforeground=t["text"],
                       font=("Segoe UI", 9), bd=0, highlightthickness=0).pack(side="left")
        return var.get()

    # ---- detailed tables with persistent show/hide catalog columns ---------
    def _optional_columns(self):
        """Catalogue-derived columns available to any item table: core + used attributes."""
        return ["Category", "Manufacturer", "Model"] + L.used_attribute_names(self.conn)

    def _visible_optional(self, table_key):
        raw = L.get_pref(self.conn, f"cols.{table_key}", "")
        chosen = [c for c in (raw.split("\u241F") if raw else []) if c]
        avail = self._optional_columns()
        return [c for c in chosen if c in avail]

    def _open_column_picker(self, table_key):
        t = self.t
        avail = self._optional_columns()
        visible = set(self._visible_optional(table_key))
        win = tk.Toplevel(self); win.title("Columns"); win.configure(bg=t["bg"]); win.transient(self)
        tk.Label(win, text="Show extra columns", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(win, text="Core fields and catalogue attributes. Choices are saved.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        box = tk.Frame(win, bg=t["bg"]); box.pack(fill="both", expand=True, padx=16, pady=8)
        vars_ = {}
        for c in avail:
            v = tk.BooleanVar(value=(c in visible))
            vars_[c] = v
            tk.Checkbutton(box, text=c, variable=v, bg=t["bg"], fg=t["text"], selectcolor=t["panel"],
                           activebackground=t["bg"], font=("Segoe UI", 10), bd=0,
                           highlightthickness=0, anchor="w").pack(fill="x")
        if not avail:
            tk.Label(box, text="(no catalogue attributes yet)", bg=t["bg"], fg=t["muted"]).pack(anchor="w")

        def apply():
            chosen = [c for c in avail if vars_[c].get()]
            L.set_pref(self.conn, f"cols.{table_key}", "\u241F".join(chosen))
            win.destroy()
            self._render_content()
        btns = tk.Frame(win, bg=t["bg"]); btns.pack(fill="x", padx=16, pady=12)
        tk.Button(btns, text="Cancel", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Apply", command=apply, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=10).pack(side="right")
        _modalize(win)

    def _detailed_table(self, inner, table_key, base_cols, base_widths, base_rows,
                        multi=False, height=14, breakdown_before=None):
        """base_rows: list of (iid, base_values_tuple, catid[, muted]). Appends the chosen
        catalogue/attribute columns (persisted per table_key). If breakdown_before is set
        (a column name), a separately-toggled cost-breakdown column group (M8/M11) is
        inserted before that column. iid is the lywrid string for cost lookups."""
        vis = self._visible_optional(table_key)
        bd_cols = ["Item cost", "Intl ship", "Local ship", "Add. cost"]
        show_bd = bool(self.view_flags.get(f"bd.{table_key}", False)) and breakdown_before
        columns, widths = [], []
        for c, w in zip(base_cols, base_widths):
            if show_bd and c == breakdown_before:
                columns += bd_cols; widths += [85] * len(bd_cols)
            columns.append(c); widths.append(w)
        columns += vis; widths += [120] * len(vis)
        rows = []
        for r in base_rows:
            iid, base_vals, catid = r[0], r[1], r[2]
            muted = r[3] if len(r) > 3 else False
            gid = r[4] if len(r) > 4 else None
            detail = L.item_detail(self.conn, catid)
            extra = tuple(detail.get(col, "\u2014") or "\u2014" for col in vis)
            vals = []
            for c, v in zip(base_cols, base_vals):
                if show_bd and c == breakdown_before:
                    try:
                        bd = L.item_cost_breakdown(self.conn, int(iid))
                        vals += [D(bd["item_cost"]), D(bd["intl_shipping"]),
                                 D(bd["local_shipping"]), D(bd["additional"])]
                    except Exception:
                        vals += ["\u2014"] * len(bd_cols)
                vals.append(v)
            rows.append((iid, tuple(vals) + extra, muted, gid))
        return self._make_table(inner, columns, widths, rows, multi=multi, height=height,
                                cols_button=lambda: self._open_column_picker(table_key))

    def _selected_id(self, multi=False):
        tree = self.cur_table
        if tree is None:
            return [] if multi else None
        sel = tree.selection()
        if not sel:
            return [] if multi else None
        return [int(s) for s in sel] if multi else int(sel[0])

    def _need_row(self):
        i = self._selected_id()
        if i is None:
            messagebox.showinfo("Select a row", "Highlight a row in the table first.", parent=self)
        return i

    def _acct_label(self, acctid):
        a = self.conn.execute("SELECT account_name FROM accounts WHERE acctid=?", (acctid,)).fetchone()
        return a["account_name"] if a else f"#{acctid}"

    def _modalize(self, win):
        _modalize(win)

    def _snapshot(self, reason="edit"):
        """Take a safety backup of the DB before a destructive operation."""
        try:
            L.make_backup(DB_FILE, reason=reason)
        except Exception:
            pass

    def _on_close(self):
        """Persist session state (window, place, toggles) so the app reopens where you left it."""
        try:
            zoomed = "0"
            try:
                zoomed = "1" if self.state() == "zoomed" else "0"
            except Exception:
                pass
            L.set_pref(self.conn, "win.zoomed", zoomed)
            if zoomed != "1":
                L.set_pref(self.conn, "win.geometry", self.geometry())
            L.set_pref(self.conn, "ui.last_tab", self.cur_tab or "Home")
            L.set_pref(self.conn, "ui.last_sub", self.cur_sub or "")
            L.set_pref(self.conn, "ui.view_flags", _json.dumps(self.view_flags))
        except Exception:  # never block closing
            pass
        self.destroy()

    def _focus_filter(self, _e=None):
        ent = getattr(self, "_filter_entry", None)
        try:
            if ent and ent.winfo_exists():
                ent.focus_set(); ent.select_range(0, "end")
        except Exception:  # noqa
            pass
        return "break"

    def refresh(self):
        self._render_content()
        if hasattr(self, "tab_bubbles"):
            self._update_tab_bubbles()
            self._build_subbar()

    # ---- Accounts tools ----------------------------------------------------
    def tool_deposit(self):
        i = self._need_row()
        if i is None:
            return
        FormDialog(self, f"Add Funds to {self.cur_acct_type} Account",
                   [{"key": "info", "type": "info",
                     "label": f"Account: {self._acct_label(i)}   (LYD only)"},
                    {"key": "amount", "label": "Amount (LYD)", "type": "number", "required": True}],
                   lambda v: (L.deposit_lyd(self.conn, i, _num(v["amount"], "Amount")), self.refresh()))

    def tool_withdraw(self):
        i = self._need_row()
        if i is None:
            return
        bal = L.lyd_balance(self.conn, i)
        FormDialog(self, f"Withdraw from {self.cur_acct_type} Account",
                   [{"key": "info", "type": "info",
                     "label": f"Account: {self._acct_label(i)}   Balance: {D(bal)} LYD   (LYD only)"},
                    {"key": "amount", "label": "Amount (LYD)", "type": "number", "required": True}],
                   lambda v: (L.withdraw_lyd(self.conn, i, _num(v["amount"], "Amount")), self.refresh()))

    def tool_recharge(self):
        i = self._need_row()
        if i is None:
            return
        cards = L.list_accounts(self.conn, "Card")
        if not cards:
            messagebox.showerror("No cards", "Make a Card account first before recharging.", parent=self)
            return
        cmap = {f'{c["account_name"]} (#{c["acctid"]})': c["acctid"] for c in cards}
        last_card = L.get_pref(self.conn, "last.recharge_card", None)
        default_card = None
        if last_card:
            for disp, aid in cmap.items():
                if str(aid) == last_card:
                    default_card = disp
        FormDialog(self, "Recharge a Card",
                   [{"key": "info", "type": "info", "label": f"Funded by: {self._acct_label(i)} (LYD spent)"},
                    {"key": "card", "label": "Target card", "type": "option", "values": list(cmap),
                     "default": default_card},
                    {"key": "usd", "label": "USD amount", "type": "number", "required": True},
                    {"key": "rate", "label": "Rate (LYD per USD)", "type": "number"},
                    {"key": "info2", "type": "info",
                     "label": "\u2014 or, to cover seller rounding, leave Rate blank and enter what you "
                              "actually paid below; the exact rate is computed for you."},
                    {"key": "lyd", "label": "LYD paid (optional)", "type": "number"}],
                   lambda v: (L.recharge_card(self.conn, i, cmap[v["card"]], "USD",
                                              _num(v["usd"], "USD amount"),
                                              rate=_num(v["rate"], "Rate") if v.get("rate", "").strip() else None,
                                              lyd_paid=_num(v["lyd"], "LYD paid") if v.get("lyd", "").strip() else None),
                              L.set_pref(self.conn, "last.recharge_card", str(cmap[v["card"]])),
                              self.refresh()))

    def tool_convert(self):
        i = self._need_row()
        if i is None:
            return
        ConvertDialog(self, i)

    def tool_reverse_transaction(self):
        if self.cur_sub != "All Transactions":
            messagebox.showinfo("Reverse", "Open the All Transactions list, then select the "
                                "transaction to reverse.", parent=self)
            return
        i = self._need_row()
        if i is None:
            return
        info = self.conn.execute(
            "SELECT t.type, t.amount, t.currency, a.account_name FROM all_transactions t "
            "JOIN accounts a ON t.acctid=a.acctid WHERE t.trnsid=?", (i,)).fetchone()
        if not info:
            return
        ok, reason = L.transaction_reversibility(self.conn, i)
        if not ok:
            messagebox.showinfo("Can't reverse this one", reason, parent=self)
            return
        if messagebox.askyesno("Reverse transaction",
                               f"Reverse #{i}: {info['type']} {D(info['amount'])} {info['currency']} "
                               f"on {info['account_name']}?\n\nThis undoes its money effect completely "
                               "(any linked transfer/conversion legs go too). It can't be un-done except "
                               "by re-entering the transaction.", parent=self):
            self._snapshot("reverse-transaction")
            try:
                L.reverse_transaction(self.conn, i)
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not reverse", str(e), parent=self)

    def tool_edit_transaction(self):
        if self.cur_sub != "All Transactions":
            messagebox.showinfo("Edit", "Open the All Transactions list, then select the transaction "
                                "to edit.", parent=self)
            return
        i = self._need_row()
        if i is None:
            return
        t = self.conn.execute("SELECT type, amount, currency, date FROM all_transactions WHERE trnsid=?",
                              (i,)).fetchone()
        if not t:
            return
        if t["type"] not in L._EDITABLE_TYPES or t["currency"] != "LYD":
            messagebox.showinfo("Edit unavailable",
                                "Only simple LYD cash transactions (deposit, withdrawal, business "
                                "expense, FX adjustment) can be edited directly.\n\nFor a recharge, "
                                "transfer, purchase, sale or shipping payment, reverse it and re-enter "
                                "it instead.", parent=self)
            return
        cur_amt = str(D(abs(Decimal(str(t["amount"])))))
        FormDialog(self, f"Edit transaction #{i}",
                   [{"key": "info", "type": "info",
                     "label": f"{t['type']} on {t['date']} — currently {cur_amt} LYD."},
                    {"key": "amt", "label": "New amount (LYD)", "type": "number", "default": cur_amt},
                    {"key": "date", "label": "New date", "type": "text", "default": t["date"]}],
                   lambda v: (self._snapshot("edit-transaction"),
                              L.edit_transaction(self.conn, i,
                                                 new_amount=_num(v["amt"], "Amount") if v["amt"].strip() else None,
                                                 new_date=v["date"].strip() or None),
                              self.refresh()))

    def tool_business_expense(self):
        i = self._need_row()
        if i is None:
            return
        cur = "USD" if self.cur_acct_type == "Card" else "LYD"
        FormDialog(self, "Record Business Expense",
                   [{"key": "info", "type": "info",
                     "label": f"Account: {self._acct_label(i)}   Currency: {cur}"
                              + ("   (drawn from FX batches)" if cur == "USD" else "")},
                    {"key": "amount", "label": f"Amount ({cur})", "type": "number", "required": True},
                    {"key": "category", "label": "Category", "type": "text"},
                    {"key": "desc", "label": "Description", "type": "text"}],
                   lambda v: (L.record_business_expense(self.conn, i, _num(v["amount"], "Amount"), cur,
                                                        v["category"] or None, v["desc"] or None),
                              self.refresh()))

    def tool_make_account(self):
        atype = self.cur_acct_type
        FormDialog(self, f"Make New {atype} Account",
                   [{"key": "name", "label": "Account name", "type": "text", "required": True}],
                   lambda v: (L.add_account(self.conn, v["name"], atype), self.refresh()))

    def tool_make_card(self):
        FormDialog(self, "Make New Card",
                   [{"key": "name", "label": "Card name", "type": "text", "required": True}],
                   lambda v: (L.add_account(self.conn, v["name"], "Card"), self.refresh()))

    def tool_hide_account(self):
        i = self._need_row()
        if i is None:
            return
        bal_l, bal_u = L.lyd_balance(self.conn, i), L.fx_balance(self.conn, i, "USD")
        note = ""
        if bal_l != 0 or bal_u != 0:
            note = f"\n\nNote: this account still holds {D(bal_l)} LYD / {D(bal_u)} USD. " \
                   "Hidden accounts still count in totals; you can unhide from Settings."
        if messagebox.askyesno("Hide account",
                               f"Hide '{self._acct_label(i)}'?{note}", parent=self):
            L.hide_account(self.conn, i)
            self.refresh()

    def tool_show_transactions(self):
        i = self._need_row()
        if i is None:
            return
        name = self._acct_label(i)
        is_card = self.cur_acct_type == "Card"

        def render(inner):
            self._title(inner, f"Transactions — {name}")
            rows = []
            for r in self.conn.execute(
                    "SELECT t.trnsid, t.type, tt.category, t.amount, t.currency, t.date, t.time "
                    "FROM all_transactions t JOIN transaction_types tt ON t.type=tt.type "
                    "WHERE t.acctid=? ORDER BY t.trnsid DESC", (i,)):
                rows.append((str(r["trnsid"]),
                             (r["trnsid"], r["type"], r["category"], D(r["amount"]),
                              r["currency"], r["date"], r["time"])))
            self._make_table(inner, ["ID", "Type", "Category", "Amount", "Cur", "Date", "Time"],
                             [50, 150, 100, 120, 60, 100, 90], rows, multi=True)
        self._show_subpage(render)

    def tool_show_batches(self):
        i = self._need_row()
        if i is None:
            return
        name = self._acct_label(i)

        def render(inner):
            self._title(inner, f"FX batches — {name}", "FIFO order; oldest consumed first")
            rows = []
            for b in self.conn.execute(
                    "SELECT bachid, currency, fx_amount, rate, lyd_cost, fx_remaining, source, date_acquired "
                    "FROM fx_batches WHERE acctid=? ORDER BY bachid", (i,)):
                rows.append((str(b["bachid"]),
                             (b["bachid"], b["currency"], D(b["fx_amount"]), D(b["rate"]),
                              D(b["lyd_cost"]), D(b["fx_remaining"]), b["source"], b["date_acquired"])))
            self._make_table(inner, ["Batch", "Cur", "Original", "Rate", "LYD cost",
                                     "Remaining", "Source", "Acquired"],
                             [60, 55, 110, 90, 120, 110, 110, 110], rows)
        self._show_subpage(render)

    def tool_txn_query(self):
        ids = self._selected_id(multi=True)
        if not ids:
            messagebox.showinfo("Select rows", "Highlight one or more transactions (Ctrl/Shift-click).",
                                parent=self)
            return
        FormDialog(self, "Transaction Query",
                   [{"key": "info", "type": "info", "label": f"{len(ids)} transaction(s) selected."},
                    {"key": "op", "label": "Operation", "type": "option",
                     "values": ["Sum (net)", "Statistics", "Breakdown by category"]}],
                   lambda v: self._run_txn_query(ids, v["op"]))

    def _run_txn_query(self, ids, op):
        ph = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT t.amount, t.currency, tt.category FROM all_transactions t "
            f"JOIN transaction_types tt ON t.type=tt.type WHERE t.trnsid IN ({ph})", ids).fetchall()
        lyd = [L.money(r["amount"]) for r in rows if r["currency"] == "LYD"]

        def render(inner):
            self._title(inner, "Query result", f"{len(ids)} transaction(s) — {op}")
            box = tk.Frame(inner, bg=self.t["card"], highlightbackground=self.t["border"],
                           highlightthickness=1)
            box.pack(fill="x", padx=24, pady=10)

            def line(k, val):
                r = tk.Frame(box, bg=self.t["card"]); r.pack(fill="x", padx=16, pady=4)
                tk.Label(r, text=k, bg=self.t["card"], fg=self.t["muted"],
                         font=("Segoe UI", 11), width=24, anchor="w").pack(side="left")
                tk.Label(r, text=val, bg=self.t["card"], fg=self.t["text"],
                         font=("Segoe UI Semibold", 12), anchor="w").pack(side="left")

            if op == "Breakdown by category":
                cats = {}
                for r in rows:
                    if r["currency"] == "LYD":
                        cats[r["category"]] = cats.get(r["category"], L.money(0)) + L.money(r["amount"])
                for c, val in sorted(cats.items()):
                    line(c, f"{D(val)} LYD")
                if not cats:
                    line("(no LYD rows)", "—")
            elif op == "Statistics":
                if lyd:
                    s = sum(lyd, Decimal("0"))
                    line("Count (LYD rows)", str(len(lyd)))
                    line("Sum", f"{D(s)} LYD")
                    line("Average", f"{D(s / len(lyd))} LYD")
                    line("Min", f"{D(min(lyd))} LYD")
                    line("Max", f"{D(max(lyd))} LYD")
                else:
                    line("(no LYD rows)", "—")
            else:
                line("Net sum (LYD rows)", f"{D(sum(lyd, Decimal('0')))} LYD")
                line("Rows included", f"{len(lyd)} of {len(ids)}")
                tk.Label(inner, text="Net sum treats inflows as + and outflows as -, so a set of "
                         "revenue and expense rows yields the profit.", bg=self.t["content"],
                         fg=self.t["muted"], font=("Segoe UI", 10), anchor="w",
                         wraplength=560, justify="left").pack(fill="x", padx=24, pady=4)
        self._show_subpage(render)

    def tool_show_graph(self):
        ids = self._selected_id(multi=True)
        if not ids:
            messagebox.showinfo("Select rows", "Highlight one or more transactions to graph.", parent=self)
            return
        ph = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT t.amount, t.date FROM all_transactions t "
            f"WHERE t.trnsid IN ({ph}) AND t.currency='LYD' ORDER BY t.trnsid", ids).fetchall()
        vals = [float(L.money(r["amount"])) for r in rows]
        labels = [r["date"][5:] for r in rows]

        def render(inner):
            self._title(inner, "Transaction graph", "Selected LYD transactions")
            if not vals:
                tk.Label(inner, text="No LYD transactions in the selection.", bg=self.t["content"],
                         fg=self.t["muted"], font=("Segoe UI", 12)).pack(padx=24, pady=20)
                return
            self._draw_bars(inner, vals, labels)
        self._show_subpage(render)

    def _draw_bars(self, parent, values, labels):
        t = self.t
        W, H, pad = 640, 280, 40
        cv = tk.Canvas(parent, width=W, height=H, bg=t["card"], highlightthickness=1,
                       highlightbackground=t["border"])
        cv.pack(padx=24, pady=12, anchor="w")
        lo, hi = min(values + [0]), max(values + [0])
        rng = (hi - lo) or 1
        zero_y = H - pad - (0 - lo) / rng * (H - 2 * pad)
        cv.create_line(pad, zero_y, W - pad, zero_y, fill=t["muted"])
        n = len(values)
        bw = (W - 2 * pad) / max(n, 1) * 0.6
        for k, v in enumerate(values):
            cx = pad + (W - 2 * pad) * (k + 0.5) / max(n, 1)
            y = H - pad - (v - lo) / rng * (H - 2 * pad)
            col = t["accent"] if v >= 0 else "#D9534F"
            cv.create_rectangle(cx - bw / 2, min(y, zero_y), cx + bw / 2, max(y, zero_y),
                                fill=col, outline="")
            if n <= 16:
                cv.create_text(cx, H - pad + 12, text=labels[k], fill=t["muted"], font=("Segoe UI", 8))

    # ---- Inventory rendering ----------------------------------------------
    def _render_inventory(self, inner, crumb):
        sub = self.cur_sub
        vs = L.variant_suffix_map(self.conn)
        if sub == "Current Inventory":
            self._title(inner, crumb, "Items in stock — highlight one or more, then Sell Order")
            show_sold = self._toggle_bar(inner, "inv_sold", "Show sold items (muted)")
            self._toggle_bar(inner, "bd.inventory", "Show cost breakdown columns")
            rows = []

            def _days(r):                        # days sitting in stock; slow stock is tied-up capital
                if not r["date_entered_inventory"]:
                    return "\u2014"
                d = self.conn.execute("SELECT CAST(julianday('now') - julianday(?) AS INTEGER) AS d",
                                      (r["date_entered_inventory"],)).fetchone()["d"] or 0
                d = max(0, d)
                return f"{d} \u26A0" if d > 60 else str(d)
            for r in self.conn.execute(
                    "SELECT i.lywrid, i.catid, pl.item_name, i.total_cost, i.status, "
                    "i.date_entered_inventory, i.condition, i.condition_note "
                    "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
                    "WHERE i.status='In Stock' ORDER BY i.lywrid"):
                rows.append((str(r["lywrid"]), (r["lywrid"], r["item_name"] + vs.get(r["catid"], ""), self._cond(r),
                             D(r["total_cost"]) if r["total_cost"] is not None else "\u2014",
                             r["status"], r["date_entered_inventory"] or "\u2014", _days(r)), r["catid"]))
            if show_sold:
                for r in self.conn.execute(
                        "SELECT i.lywrid, i.catid, pl.item_name, i.total_cost, i.status, "
                        "i.date_entered_inventory, i.condition, i.condition_note "
                        "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
                        "WHERE i.status IN ('Sold Pending','Sold') ORDER BY i.lywrid"):
                    rows.append((str(r["lywrid"]), (r["lywrid"], r["item_name"] + vs.get(r["catid"], ""), self._cond(r),
                                 D(r["total_cost"]) if r["total_cost"] is not None else "\u2014",
                                 r["status"], r["date_entered_inventory"] or "\u2014", "\u2014"), r["catid"], True))
            self.cur_table = self._detailed_table(inner, "inventory",
                ["ID", "Item", "Condition", "Total cost", "Status", "Entered", "Days"],
                [50, 210, 115, 100, 95, 95, 60], rows, multi=True, breakdown_before="Total cost")
        elif sub == "Pending For Approval":
            self._title(inner, crumb, "Awaiting your OK into inventory — select, then Accept Into Inventory")
            self._toggle_bar(inner, "bd.pending", "Show cost breakdown columns")
            rows = []
            for r in self.conn.execute(
                    "SELECT i.lywrid, i.catid, pl.item_name, i.status, po.order_date, "
                    "i.condition, i.condition_note "
                    "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
                    "JOIN purchase_orders po ON pl.poid=po.poid "
                    "WHERE i.status='Pending Approval' ORDER BY i.lywrid"):
                bd = L.item_cost_breakdown(self.conn, r["lywrid"])   # BUG1: item + shipping, not item only
                rows.append((str(r["lywrid"]), (r["lywrid"], r["item_name"] + vs.get(r["catid"], ""), self._cond(r), D(bd["total"]),
                             r["status"], r["order_date"] or "\u2014"), r["catid"]))
            self.cur_table = self._detailed_table(inner, "pending",
                ["ID", "Item", "Condition", "Cost (w/ shipping)", "Status", "Purchased"],
                [50, 200, 120, 120, 100, 95], rows, multi=True,
                breakdown_before="Cost (w/ shipping)")
        elif sub == "Shipping To Shop":
            self._title(inner, crumb, "On the way to the shop — grouped by shipment. Select an item then "
                                      "Update Shipping Status (acts on the whole group) or Split Shipment.")
            show_done = self._toggle_bar(inner, "ship_done", "Show completed (muted)")
            show_track = self._toggle_bar(inner, "ship_track", "Show tracking number column")
            # map each item to its CURRENT-leg shipment (the most recent one it belongs to —
            # an intl->local item is in both, and we want the local one while it's in local transit)
            ship_of, size_of = {}, {}
            for r in self.conn.execute(
                    "SELECT si.lywrid, si.shipid, "
                    "(SELECT COUNT(*) FROM shipment_items s2 WHERE s2.shipid=si.shipid) AS n "
                    "FROM shipment_items si ORDER BY si.shipid ASC"):
                ship_of[r["lywrid"]] = r["shipid"]; size_of[r["lywrid"]] = r["n"]
            track_of = {}
            fwd_of = {}
            # an item's tracking number AND freight forwarder ride its INTERNATIONAL leg;
            # keep them visible through the local leg too ("which box / who carried this?")
            for r in self.conn.execute(
                    "SELECT si.lywrid, isp.tracking_number, isp.freight_forwarder_name "
                    "FROM shipment_items si "
                    "JOIN international_shipping isp ON isp.shipid=si.shipid ORDER BY si.shipid ASC"):
                if r["tracking_number"]:
                    track_of[r["lywrid"]] = r["tracking_number"]
                if r["freight_forwarder_name"]:
                    fwd_of[r["lywrid"]] = r["freight_forwarder_name"]
            rows = []
            base = ("SELECT i.lywrid, i.polnid, i.catid, pl.item_name, i.status, po.delivery_method "
                    "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
                    "JOIN purchase_orders po ON pl.poid=po.poid "
                    "JOIN inventory_statuses st ON i.status=st.status ")
            live = list(self.conn.execute(base + "WHERE st.stage='shipping'"))
            live.sort(key=lambda r: (ship_of.get(r["lywrid"], 0), r["lywrid"]))

            def datecols(lid):
                d = L.item_shipping_dates(self.conn, lid)
                return (d["us_warehouse"] or "\u2014", d["libya_warehouse"] or "\u2014",
                        d["local_sent"] or "\u2014", d["local_office"] or "\u2014",
                        d["picked_up"] or "\u2014")

            def trackcol(lid):
                return (track_of.get(lid) or "\u2014",) if show_track else ()
            for r in live:
                ship = ship_of.get(r["lywrid"])
                gid = ship if size_of.get(r["lywrid"], 1) > 1 else None
                rows.append((str(r["lywrid"]), (r["lywrid"], r["polnid"], f"#{ship}" if ship else "\u2014",
                             fwd_of.get(r["lywrid"]) or "\u2014", *trackcol(r["lywrid"]),
                             r["item_name"] + vs.get(r["catid"], ""), r["status"], r["delivery_method"] or "\u2014",
                             *datecols(r["lywrid"])), r["catid"], False, gid))
            if show_done:
                for r in self.conn.execute(base + "AND st.stage!='shipping' AND i.lywrid IN "
                                           "(SELECT lywrid FROM shipment_items)"):
                    ship = ship_of.get(r["lywrid"])
                    rows.append((str(r["lywrid"]), (r["lywrid"], r["polnid"], f"#{ship}" if ship else "\u2014",
                                 fwd_of.get(r["lywrid"]) or "\u2014", *trackcol(r["lywrid"]),
                                 r["item_name"] + vs.get(r["catid"], ""), r["status"], r["delivery_method"] or "\u2014",
                                 *datecols(r["lywrid"])), r["catid"], True))
            track_hdr = (["Tracking #"] if show_track else [])
            track_w = ([120] if show_track else [])
            self.cur_table = self._detailed_table(inner, "shipping_shop",
                ["ID", "Line", "Shipment", "Forwarder", *track_hdr, "Item", "Status", "Method",
                 "US whse", "LY whse", "Local sent", "Local office", "Picked up"],
                [45, 45, 80, 120, *track_w, 180, 125, 85, 90, 90, 90, 90, 90], rows)
        elif sub == "Purchases":
            self._title(inner, crumb, "Every purchased item — Make Purchase to add more")
            rows = []
            for r in self.conn.execute(
                    "SELECT pl.polnid, pl.catid, pl.item_name, po.vendor_name, po.purchaser_name, "
                    "po.order_date, pl.unit_price_allocated, pl.currency, po.delivery_method "
                    "FROM purchase_lines pl JOIN purchase_orders po ON pl.poid=po.poid "
                    "ORDER BY pl.polnid DESC"):
                rows.append((str(r["polnid"]), (r["polnid"], r["item_name"] + vs.get(r["catid"], ""), r["vendor_name"],
                             r["purchaser_name"] or "\u2014", r["order_date"],
                             D(r["unit_price_allocated"]), r["currency"],
                             r["delivery_method"] or "\u2014"), r["catid"]))
            self.cur_table = self._detailed_table(inner, "purchases",
                ["Line", "Item", "Vendor", "Purchaser", "Date", "Unit price", "Cur", "Method"],
                [50, 200, 120, 110, 100, 100, 50, 100], rows)

    def tool_sell_order(self):
        ids = self._selected_id(multi=True)
        if not ids:
            messagebox.showinfo("Select items", "Highlight one or more in-stock items.", parent=self)
            return
        SellOrderDialog(self, ids)

    def tool_accept_inventory(self):
        ids = self._selected_id(multi=True)
        if not ids:
            messagebox.showinfo("Select items", "Highlight one or more pending items.", parent=self)
            return
        AcceptInventoryDialog(self, ids)

    def tool_update_shipping(self):
        i = self._need_row()
        if i is None:
            return
        UpdateShippingDialog(self, i)

    def tool_edit_tracking(self):
        """Edit the tracking number of the selected item's INTERNATIONAL shipment. Tracking
        lives on the international leg, so this works whether the item is still in intl
        transit or has moved to its local leg. The number is per-shipment, so the whole
        group updates together."""
        i = self._need_row()
        if i is None:
            return
        row = self.conn.execute(
            "SELECT isp.shipid, isp.tracking_number, "
            "(SELECT COUNT(*) FROM shipment_items s2 WHERE s2.shipid=isp.shipid) AS n "
            "FROM shipment_items si JOIN international_shipping isp ON isp.shipid=si.shipid "
            "WHERE si.lywrid=? LIMIT 1", (int(i),)).fetchone()
        if not row:
            messagebox.showinfo("No international shipment",
                                "This item has no international shipment leg, so there's no "
                                "tracking number to edit.", parent=self)
            return
        shipid, current, n = row["shipid"], row["tracking_number"] or "", row["n"]

        def _save(vals):
            L.update_international_shipment(self.conn, shipid,
                                           tracking_number=(vals["tracking"].strip() or None))
            self.refresh()
        scope = f" ({n} items in group)" if n > 1 else ""
        FormDialog(self, f"Edit tracking # — shipment #{shipid}{scope}",
                   [{"key": "tracking", "label": "Tracking number", "type": "text",
                     "default": current}],
                   on_submit=_save)

    def tool_split_shipment(self):
        i = self._need_row()
        if i is None:
            return
        # find the item's current shipment among pre-transit shipments
        row = self.conn.execute(
            "SELECT s.shipid FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "WHERE si.lywrid=? ORDER BY s.shipid DESC LIMIT 1", (i,)).fetchone()
        if not row:
            messagebox.showinfo("No shipment", "That item isn't in a shipment group.", parent=self)
            return
        if L.get_item_status(self.conn, i) != "Awaiting Shipment":
            messagebox.showinfo("Can't split", "Items can only be split before the shipment starts "
                                "(while Awaiting Shipment).", parent=self)
            return
        SplitShipmentDialog(self, row["shipid"])

    def tool_cost_breakdown(self):
        i = self._need_row()
        if i is None:
            return
        bd = L.item_cost_breakdown(self.conn, i)
        self._breakdown_popup(f"Cost breakdown — item #{i}", [
            ("Item cost", bd["item_cost"]), ("International shipping", bd["intl_shipping"]),
            ("Local shipping", bd["local_shipping"]), ("Additional cost", bd["additional"]),
            ("Total", bd["total"])])

    def _row_catid(self):
        """Resolve the highlighted operational row to its catalogue id (inventory/shipping/
        pending rows are keyed by lywrid; purchase rows by polnid)."""
        i = self._need_row()
        if i is None:
            return None
        if self.cur_sub == "Purchases":
            r = self.conn.execute("SELECT catid FROM purchase_lines WHERE polnid=?", (i,)).fetchone()
        else:
            r = self.conn.execute("SELECT catid FROM inventory_items WHERE lywrid=?", (i,)).fetchone()
        if not r or r["catid"] is None:
            messagebox.showinfo("No catalogue link", "This row isn't linked to a catalogue item.",
                                parent=self)
            return None
        return r["catid"]

    def _fit_window(self, win, w, h):
        """Size a popup but never taller than the screen, so its content + buttons stay reachable."""
        win.update_idletasks()
        sh = win.winfo_screenheight()
        sw = win.winfo_screenwidth()
        h = min(h, max(320, sh - 80))
        w = min(w, max(360, sw - 40))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _scroll_host(self, parent):
        """A vertically scrollable region filling `parent`; returns the inner frame to pack into.
        Used by popups whose content can grow unboundedly (attribute lists, batch lists, etc.)."""
        t = self.t
        host = tk.Frame(parent, bg=t["bg"]); host.pack(fill="both", expand=True)
        canvas = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=t["bg"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wid = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(wid, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        def _wheel(e):
            delta = int(-e.delta / 30) if getattr(e, "delta", 0) else (-2 if getattr(e, "num", 0) == 4 else 2)
            canvas.yview_scroll(delta, "units")
        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", _wheel),
                                          canvas.bind_all("<Button-4>", _wheel),
                                          canvas.bind_all("<Button-5>", _wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"),
                                          canvas.unbind_all("<Button-4>"),
                                          canvas.unbind_all("<Button-5>")))
        return inner

    def tool_view_specs(self):
        catid = self._row_catid()
        if catid is not None:
            self._specs_popup(catid)

    def _specs_popup(self, catid):
        t = self.t
        d = L.get_catalog_item(self.conn, catid)
        if not d:
            return
        it = d["item"]
        win = tk.Toplevel(self); win.configure(bg=t["bg"]); win.title("Item specs"); win.transient(self)
        variant = it["variant"] if "variant" in it.keys() else "A"
        tk.Label(win, text=it["display_name"], bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14), wraplength=380, justify="left").pack(
            anchor="w", padx=20, pady=(16, 0))
        tk.Label(win, text=f"Variant {variant}  \u00B7  catalogue #{catid}", bg=t["bg"],
                 fg=t["accent"], font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 8))
        # Close pinned to the bottom BEFORE the (scrollable) body, so it never scrolls away
        btnbar = tk.Frame(win, bg=t["bg"]); btnbar.pack(side="bottom", fill="x")
        tk.Button(btnbar, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=20, pady=10)
        wrap = tk.Frame(win, bg=t["bg"]); wrap.pack(fill="both", expand=True, padx=20, pady=4)
        body_outer = tk.Frame(wrap, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
        body_outer.pack(fill="both", expand=True)
        body = self._scroll_host(body_outer)

        def line(k, v):
            r = tk.Frame(body, bg=t["card"]); r.pack(fill="x", padx=12, pady=3)
            tk.Label(r, text=k, bg=t["card"], fg=t["muted"], width=14, anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Label(r, text=v or "\u2014", bg=t["card"], fg=t["text"], anchor="w",
                     font=("Segoe UI", 10), wraplength=240, justify="left").pack(side="left")
        line("Category", it["category"]); line("Manufacturer", it["manufacturer"])
        line("Model", it["model_name"])
        tk.Label(body, text="Attributes", bg=t["card"], fg=t["muted"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(8, 0))
        if d["attributes"]:
            for n, v in d["attributes"]:
                line(n, v)
        else:
            tk.Label(body, text="(none recorded)", bg=t["card"], fg=t["muted"],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=2)
        self._fit_window(win, 420, 460)
        _modalize(win)

    def tool_undo_last_step(self):
        """Walk the selected unit one step back (accept -> Pending, or a shipping step for
        the whole group) — unwinding any cost-adjustment money the step moved. The same
        engine as the shipping dialog's undo, reachable from the item itself."""
        i = self._need_row()
        if i is None:
            return
        ok, why = L.can_reverse_last_status(self.conn, int(i))
        if not ok:
            messagebox.showinfo("Can't undo this step", why, parent=self)
            return
        st = L.get_item_status(self.conn, int(i))
        if not messagebox.askyesno("Undo last step",
                                   f"Unit #{i} is '{st}'. Step it back one stage? Any money the "
                                   "step moved (cost-adjustment expense or refund) is unwound too.",
                                   parent=self):
            return
        try:
            L.reverse_last_status(self.conn, int(i), _today())
            self.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not undo", str(e), parent=self)

    def tool_archive_listing(self):
        i = self._need_row()
        if i is None:
            return
        r = self.conn.execute("SELECT is_archived FROM all_listings WHERE lsid=?", (i,)).fetchone()
        if not r:
            return
        arch = not bool(r["is_archived"])
        L.set_listing_archived(self.conn, int(i), arch)
        messagebox.showinfo("Listing " + ("archived" if arch else "restored"),
                            ("It stays on record but no longer counts toward market value."
                             if arch else "It counts toward market value again."), parent=self)
        self.refresh()

    def tool_market_value(self):
        if self.cur_sub == "Catalogue":
            catid = self._need_row()
        else:
            catid = self._row_catid()
        if catid is not None:
            self._market_popup(catid)

    def _market_popup(self, catid, days=90):
        t = self.t
        mv = L.market_value(self.conn, catid, days=days)
        usd = L.market_value(self.conn, catid, platforms=("eBay", "Amazon"), currency="USD", days=days)
        trend = L.market_value_trend(self.conn, catid)
        win = tk.Toplevel(self); win.configure(bg=t["bg"]); win.title("Market value"); win.transient(self)
        btnbar = tk.Frame(win, bg=t["bg"]); btnbar.pack(side="bottom", fill="x")
        tk.Button(btnbar, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=20, pady=10)
        other = "All time" if days else "Last 90 days"
        tk.Button(btnbar, text=other, relief="solid", bd=1, bg=t["panel"], fg=t["text"],
                  command=lambda: (win.destroy(),
                                   self._market_popup(catid, days=None if days else 90))
                  ).pack(side="left", padx=20, pady=10)
        if usd["count"]:
            _rate = L.get_market_rate(self.conn)
            _eq = (f" \u2248 {D(usd['avg'] * _rate)} LYD @ {D(_rate)}" if _rate is not None else "")
            tk.Label(win, text=f"Sourcing side (eBay + Amazon, USD): {usd['count']} listing(s), "
                     f"avg {D(usd['avg'])}{_eq}, range {D(usd['min'])}\u2013{D(usd['max'])} USD",
                     bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9), wraplength=470,
                     justify="left").pack(side="bottom", anchor="w", padx=20, pady=(2, 0))
        if trend:
            line = "   ".join(f"{ym}: {D(md)} (n={k})" for ym, md, k in trend[-6:])
            tk.Label(win, text="Median by month \u00B7 " + line, bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI", 9), wraplength=480, justify="left").pack(
                side="bottom", anchor="w", padx=20, pady=(2, 0))
        tk.Label(win, text=L.catalog_label(self.conn, catid), bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13), wraplength=470, justify="left").pack(
            anchor="w", padx=20, pady=(16, 2))
        scope = f"last {days} days" if days else "all time"
        span = (f" \u00B7 dated {mv['date_from']} \u2192 {mv['date_to']}"
                if mv["date_from"] else "")
        tk.Label(win, text=f"Local resale market (Facebook + In-Person, LYD) \u2014 active listings, "
                 f"{scope}{span}", bg=t["bg"], fg=t["accent"], font=("Segoe UI", 10),
                 wraplength=480, justify="left").pack(anchor="w", padx=20)
        stat = tk.Frame(win, bg=t["bg"]); stat.pack(fill="x", padx=20, pady=6)
        if mv["count"]:
            for k, v in [("Listings", mv["count"]), ("Min", D(mv["min"])), ("Average", D(mv["avg"])),
                         ("Median", D(mv["median"])), ("Max", D(mv["max"]))]:
                cell = tk.Frame(stat, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
                cell.pack(side="left", expand=True, fill="x", padx=2)
                tk.Label(cell, text=str(k), bg=t["card"], fg=t["muted"], font=("Segoe UI", 8)).pack(pady=(4, 0))
                tk.Label(cell, text=str(v), bg=t["card"], fg=t["text"],
                         font=("Segoe UI Semibold", 11)).pack(pady=(0, 4))
        else:
            tk.Label(stat, text="No local listings yet \u2014 add Facebook listings for this item to "
                     "build a market picture.", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9),
                     wraplength=470, justify="left").pack(anchor="w")
        host = tk.Frame(win, bg=t["bg"]); host.pack(fill="both", expand=True, padx=20, pady=4)
        rows = [(str(l["lsid"]), (l["platform"], D(l["price"]), l["seller"] or "\u2014",
                 l["date"] or "\u2014")) for l in mv["listings"]]
        self._make_table(host, ["Platform", "Price (LYD)", "Seller", "Date"],
                         [90, 110, 140, 100], rows)
        self._fit_window(win, 520, 520)
        _modalize(win)

    def tool_listing_breakdown(self):
        i = self._need_row()
        if i is None:
            return
        rows = L.listing_value_breakdown(self.conn, int(i))
        t = self.t
        win = tk.Toplevel(self); win.title("Listing value breakdown"); win.configure(bg=t["bg"])
        win.transient(self)
        tk.Label(win, text=f"Listing #{i} — per-item value", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Button(win, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="bottom", anchor="e", padx=18, pady=(0, 12))
        total = sum(float(r["line_total"]) for r in rows)
        tk.Label(win, text=f"Total listing value: {D(total)}", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 11)).pack(side="bottom", anchor="e", padx=18, pady=8)
        holder = tk.Frame(win, bg=t["bg"]); holder.pack(fill="both", expand=True, padx=18)
        tree = ttk.Treeview(holder, columns=("item", "qty", "unit", "line"), show="headings", height=8)
        tsb = ttk.Scrollbar(holder, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=tree.yview)
        tree.configure(yscrollcommand=tsb.set)
        for c, txt, w in [("item", "Item", 180), ("qty", "Qty", 50), ("unit", "Unit price", 90),
                          ("line", "Line total", 90)]:
            tree.heading(c, text=txt); tree.column(c, width=w)
        tree.pack(side="left", fill="both", expand=True); tsb.pack(side="right", fill="y")
        for r in rows:
            up = D(r["unit_price"]) if r["unit_price"] is not None else "\u2014"
            tree.insert("", "end", values=(r["display_name"], r["quantity"], up, D(r["line_total"])))
        self._fit_window(win, 440, 360)
        _modalize(win)

    def _breakdown_popup(self, title, rows):
        t = self.t
        win = tk.Toplevel(self); win.title(title); win.configure(bg=t["bg"]); win.transient(self)
        win.geometry("360x300")
        tk.Label(win, text=title, bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(16, 8))
        body = tk.Frame(win, bg=t["bg"]); body.pack(fill="x", padx=18)
        for i, (label, value) in enumerate(rows):
            is_total = (label == "Total")
            r = tk.Frame(body, bg=t["bg"]); r.pack(fill="x", pady=(6 if is_total else 2))
            if is_total:
                tk.Frame(body, bg=t["divider"], height=1).pack(fill="x", before=r)
            tk.Label(r, text=label, bg=t["bg"], fg=t["text"] if is_total else t["muted"],
                     font=("Segoe UI Semibold" if is_total else "Segoe UI", 11), anchor="w").pack(side="left")
            tk.Label(r, text=D(value), bg=t["bg"], fg=t["text"],
                     font=("Segoe UI Semibold" if is_total else "Segoe UI", 11)).pack(side="right")
        tk.Button(win, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=18, pady=14)
        _modalize(win)

    def tool_make_purchase(self):
        MakePurchaseDialog(self)

    # ---- Sales rendering ---------------------------------------------------
    def _render_sales(self, inner, crumb):
        sub = self.cur_sub
        vs = L.variant_suffix_map(self.conn)
        if sub == "Sales Orders":
            self._title(inner, crumb, "Committed orders (atomized, grouped by order) — select a row, "
                                      "then Update Sale Status")
            show_moved = self._toggle_bar(inner, "ord_moved", "Show shipping/finalized (muted)")
            q = ("SELECT s.slsid, i.catid, so.sale_order_id, so.buyer_name, pl.item_name, s.sale_price, "
                 "so.requires_shipping, so.status, so.date_committed FROM sales s "
                 "JOIN sales_orders so ON s.sale_order_id=so.sale_order_id "
                 "JOIN inventory_items i ON s.lywrid=i.lywrid "
                 "JOIN purchase_lines pl ON i.polnid=pl.polnid ")
            rows = []
            for r in self.conn.execute(q + "WHERE so.status='Order Placed' ORDER BY so.sale_order_id, s.slsid"):
                rows.append((str(r["slsid"]), (r["sale_order_id"], r["buyer_name"] or "\u2014", r["item_name"] + vs.get(r["catid"], ""),
                             D(r["sale_price"]), "yes" if r["requires_shipping"] else "no", r["status"],
                             r["date_committed"] or "\u2014"), r["catid"]))
            if show_moved:
                for r in self.conn.execute(q + "WHERE so.status!='Order Placed' ORDER BY so.sale_order_id, s.slsid"):
                    rows.append((str(r["slsid"]), (r["sale_order_id"], r["buyer_name"] or "\u2014", r["item_name"] + vs.get(r["catid"], ""),
                                 D(r["sale_price"]), "yes" if r["requires_shipping"] else "no", r["status"],
                                 r["date_committed"] or "\u2014"), r["catid"], True))
            self.cur_table = self._detailed_table(inner, "sales_orders",
                ["Order", "Buyer", "Item", "Price", "Ship?", "Status", "Committed"],
                [60, 130, 200, 90, 55, 100, 100], rows)
        elif sub == "Shipping To Customers":
            self._title(inner, crumb, "Orders in transit to customers — select, then Update Status")
            rows = []
            for r in self.conn.execute(
                    "SELECT so.sale_order_id, so.buyer_name, COUNT(s.slsid) AS items, "
                    "SUM(s.sale_price) AS revenue, so.date_arrived_customer, so.date_finalized "
                    "FROM sales_orders so JOIN sales s ON s.sale_order_id=so.sale_order_id "
                    "WHERE so.status='Shipping' GROUP BY so.sale_order_id ORDER BY so.sale_order_id"):
                rows.append((str(r["sale_order_id"]), (r["sale_order_id"], r["buyer_name"] or "\u2014",
                             r["items"], D(r["revenue"]), r["date_arrived_customer"] or "\u2014",
                             r["date_finalized"] or "\u2014")))
            self.cur_table = self._make_table(
                inner, ["Order", "Buyer", "Items", "Revenue", "Arrived", "Payment approved"],
                [70, 170, 60, 130, 110, 130], rows)
        elif sub == "Finalized Sales":
            self._title(inner, crumb, "Completed sales and their profit")
            rows = []
            for r in self.conn.execute(
                    "SELECT so.sale_order_id, so.buyer_name, COUNT(s.slsid) AS items, "
                    "SUM(s.sale_price) AS revenue, so.date_finalized "
                    "FROM sales_orders so JOIN sales s ON s.sale_order_id=so.sale_order_id "
                    "WHERE so.status='Finalized' GROUP BY so.sale_order_id ORDER BY so.sale_order_id DESC"):
                profit = L.order_profit(self.conn, r["sale_order_id"])
                rows.append((str(r["sale_order_id"]), (r["sale_order_id"], r["buyer_name"] or "\u2014",
                             r["items"], D(r["revenue"]), D(profit), r["date_finalized"] or "\u2014")))
            self.cur_table = self._make_table(inner, ["Order", "Buyer", "Items", "Revenue", "Profit", "Finalized"],
                                              [70, 200, 70, 140, 140, 110], rows)
            self.cur_table.bind("<Double-1>", self._open_order_items, add="+")

    def _open_order_items(self, event):
        iid = event.widget.identify_row(event.y)
        if iid:
            self._show_order_items(int(iid))

    def tool_order_items(self):
        """M10: open the order's constituent items for the highlighted row."""
        soid = self._selected_id()
        if soid is None:
            messagebox.showinfo("Select an order", "Highlight a finalized order first.", parent=self)
            return
        self._show_order_items(int(soid))

    def _show_order_items(self, soid):
        """M6: expand a (grouped) sale order into its atomized constituent units."""
        t = self.t
        win = tk.Toplevel(self); win.title(f"Order #{soid} items"); win.configure(bg=t["bg"])
        win.transient(self)
        tk.Label(win, text=f"Order #{soid} — constituent items", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(win, text="Inventory is atomized; each unit below tracks to one inventory item.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=18)
        tk.Button(win, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="bottom", anchor="e", padx=18, pady=(0, 12))
        holder = tk.Frame(win, bg=t["bg"]); holder.pack(fill="both", expand=True, padx=18, pady=8)
        tree2 = ttk.Treeview(holder, columns=("lyw", "item", "cost", "price"), show="headings", height=8)
        tsb = ttk.Scrollbar(holder, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=tree2.yview)
        tree2.configure(yscrollcommand=tsb.set)
        for c, txt, w in [("lyw", "Unit #", 60), ("item", "Item", 240), ("cost", "Cost", 90),
                          ("price", "Sale price", 90)]:
            tree2.heading(c, text=txt); tree2.column(c, width=w)
        tree2.pack(side="left", fill="both", expand=True); tsb.pack(side="right", fill="y")
        vs = L.variant_suffix_map(self.conn)
        for r in L.order_items_detail(self.conn, soid):
            tree2.insert("", "end", values=(r["lywrid"], r["item_name"] + vs.get(r["catid"], "") if "catid" in r.keys() else r["item_name"],
                         D(r["total_cost"]) if r["total_cost"] is not None else "\u2014", D(r["sale_price"])))
        self._fit_window(win, 520, 360)
        self._modalize(win)

    def tool_update_sale_status(self):
        sel = self.cur_table.selection() if self.cur_table else None
        if not sel:
            messagebox.showinfo("Select an order", "Highlight a row from an order first.", parent=self)
            return
        order = int(self.cur_table.item(sel[0])["values"][0])
        UpdateSaleStatusDialog(self, order)

    def tool_update_customer_status(self):
        order = self._selected_id()
        if order is None:
            messagebox.showinfo("Select an order", "Highlight an order first.", parent=self)
            return
        ShipCustomerDialog(self, order)

    # ---- Listings rendering -----------------------------------------------
    def _listing_summary(self, lsid):
        lines = L.get_listing_items(self.conn, lsid)
        if not lines:
            return "\u2014"
        return ", ".join(f'{r["quantity"]}\u00D7 {r["display_name"]}' for r in lines)

    @staticmethod
    def _cond(r):
        """Format a unit's condition + optional note for a table cell."""
        try:
            c = r["condition"] or "Used"
            note = r["condition_note"]
        except (KeyError, IndexError):
            c, note = "Used", None
        return f"{c} \u00B7 {note}" if note else c

    def _render_listings(self, inner, crumb):
        sub = self.cur_sub

        def price(p):
            return D(p) if p is not None else "\u2014"

        def val(lsid):
            tv = L.listing_total(self.conn, lsid)
            return D(tv) if tv else "\u2014"

        if sub == "Catalogue":
            self._render_catalog(inner, crumb)
            return
        if sub == "All Listings":
            self._title(inner, crumb, "Every listing across all platforms")
            rows = [(str(r["lsid"]), (r["lsid"], r["platform"], r["listing_name"] or "\u2014",
                     self._listing_summary(r["lsid"]),
                     r["seller_name"] or "\u2014", r["seller_link"] or "\u2014", val(r["lsid"]),
                     r["currency"] or "\u2014", r["date_of_listing"] or "\u2014"),
                     bool(r["is_archived"]))
                    for r in self.conn.execute(
                        "SELECT lsid, platform, listing_name, seller_name, seller_link, price, "
                        "currency, phone_number, date_of_listing, is_archived "
                        "FROM all_listings ORDER BY lsid DESC")]
            self.cur_table = self._make_table(
                inner, ["ID", "Platform", "Name", "Items", "Seller", "Seller link", "Value", "Cur", "Date"],
                [40, 80, 130, 180, 95, 140, 80, 45, 90], rows)
        elif sub == "eBay Listings":
            self._title(inner, crumb, "eBay listings")
            rows = [(str(r["lsid"]), (r["lsid"], r["ebay_item_number"] or "\u2014", r["listing_name"] or "\u2014",
                     self._listing_summary(r["lsid"]), r["seller_name"] or "\u2014", r["seller_link"] or "\u2014",
                     val(r["lsid"]), r["currency"] or "\u2014", r["date_of_listing"] or "\u2014"),
                     bool(r["is_archived"]))
                    for r in self.conn.execute(
                        "SELECT al.lsid, eb.ebay_item_number, al.listing_name, al.seller_name, al.seller_link, "
                        "al.currency, al.phone_number, al.date_of_listing, al.is_archived FROM all_listings al "
                        "JOIN ebay_listings eb ON eb.lsid=al.lsid WHERE al.platform='eBay' ORDER BY al.lsid DESC")]
            self.cur_table = self._make_table(
                inner, ["ID", "Item #", "Name", "Items", "Seller", "Seller link", "Value", "Cur", "Date"],
                [40, 100, 120, 150, 90, 130, 75, 45, 85], rows)
        elif sub == "Amazon Listings":
            self._title(inner, crumb, "Amazon listings")
            rows = [(str(r["lsid"]), (r["lsid"], r["asin"] or "\u2014", r["listing_name"] or "\u2014",
                     self._listing_summary(r["lsid"]), r["seller_name"] or "\u2014", r["seller_link"] or "\u2014",
                     val(r["lsid"]), r["currency"] or "\u2014", r["date_of_listing"] or "\u2014"),
                     bool(r["is_archived"]))
                    for r in self.conn.execute(
                        "SELECT al.lsid, am.asin, al.listing_name, al.seller_name, al.seller_link, al.currency, "
                        "al.phone_number, al.date_of_listing, al.is_archived FROM all_listings al "
                        "JOIN amazon_listings am ON am.lsid=al.lsid WHERE al.platform='Amazon' ORDER BY al.lsid DESC")]
            self.cur_table = self._make_table(
                inner, ["ID", "ASIN", "Name", "Items", "Seller", "Seller link", "Value", "Cur", "Date"],
                [40, 100, 120, 150, 90, 130, 75, 45, 85], rows)
        elif sub == "Facebook Listings":
            self._title(inner, crumb, "Facebook Marketplace listings")
            rows = [(str(r["lsid"]), (r["lsid"], r["listing_name"] or "\u2014", self._listing_summary(r["lsid"]),
                     r["seller_name"] or "\u2014", r["seller_link"] or "\u2014",
                     val(r["lsid"]), r["currency"] or "\u2014", r["date_of_listing"] or "\u2014"),
                     bool(r["is_archived"]))
                    for r in self.conn.execute(
                        "SELECT al.lsid, al.listing_name, al.seller_name, al.seller_link, al.currency, "
                        "al.phone_number, al.date_of_listing, al.is_archived "
                        "FROM all_listings al JOIN facebook_listings fb ON fb.lsid=al.lsid "
                        "WHERE al.platform='Facebook' ORDER BY al.lsid DESC")]
            self.cur_table = self._make_table(
                inner, ["ID", "Name", "Items", "Seller", "Seller link", "Value", "Cur", "Date"],
                [40, 130, 200, 110, 140, 80, 50, 95], rows)
        elif sub == "In-Person Listings":
            self._title(inner, crumb, "In-person / local listings")
            rows = [(str(r["lsid"]), (r["lsid"], r["listing_name"] or "\u2014", self._listing_summary(r["lsid"]),
                     r["seller_name"] or "\u2014", r["phone_number"] or "\u2014",
                     val(r["lsid"]), r["currency"] or "\u2014", r["date_of_listing"] or "\u2014"),
                     bool(r["is_archived"]))
                    for r in self.conn.execute(
                        "SELECT al.lsid, al.listing_name, ip.seller_name, al.currency, al.phone_number, "
                        "al.date_of_listing, al.is_archived FROM all_listings al "
                        "JOIN inperson_listings ip ON ip.lsid=al.lsid "
                        "WHERE al.platform='In-Person' ORDER BY al.lsid DESC")]
            self.cur_table = self._make_table(
                inner, ["ID", "Name", "Items", "Seller", "Phone", "Value", "Cur", "Date"],
                [40, 140, 220, 120, 120, 80, 50, 95], rows)

    def _render_catalog(self, inner, crumb):
        self._title(inner, crumb, "Your item-type repository — listings and purchases pick from here")
        rows = []
        mv = L.market_value_map(self.conn)
        summaries = {a["catid"]: a["s"] for a in self.conn.execute(
            "SELECT catid, GROUP_CONCAT(attr_name || ': ' || attr_value, ', ') AS s FROM ("
            "SELECT catid, attr_name, attr_value FROM catalog_attributes "
            "ORDER BY catid, sort_order, catattrid) GROUP BY catid")}
        for r in self.conn.execute("SELECT * FROM catalog_items ORDER BY catid DESC"):
            summary = summaries.get(r["catid"]) or "\u2014"
            created = (r["created_at"] or "")[:10] or "\u2014"
            hidden = bool(r["is_hidden"]) if "is_hidden" in r.keys() else False
            name = r["display_name"] + ("  \U0001F648 hidden" if hidden else "")
            m = mv.get(r["catid"])
            local = (f'{D(m["avg"])}  ({D(m["min"])}\u2013{D(m["max"])}, n={m["n"]})'
                     if m and m["avg"] is not None else "\u2014")
            variant = r["variant"] if "variant" in r.keys() else "A"
            rows.append((str(r["catid"]), (r["catid"], name, variant, r["category"],
                         r["manufacturer"] or "\u2014", r["model_name"] or "\u2014", summary,
                         local, created), hidden))
        self.cur_table = self._make_table(
            inner, ["ID", "Display name", "Var", "Category", "Manufacturer", "Model",
                    "Attributes", "Local value (LYD)", "Created"],
            [44, 180, 50, 90, 100, 110, 210, 170, 90], rows)

    def tool_add_catalog_item(self):
        CatalogItemDialog(self)

    def tool_edit_catalog_item(self):
        if self.cur_sub != "Catalogue":
            return
        i = self._need_row()
        if i is None:
            return
        CatalogItemDialog(self, catid=i)

    def tool_make_similar_item(self):
        if self.cur_sub != "Catalogue":
            return
        i = self._need_row()
        if i is None:
            return
        CatalogItemDialog(self, clone_from=i)

    def tool_set_condition(self):
        if self.cur_sub not in ("Current Inventory", "Pending For Approval"):
            messagebox.showinfo("Set condition", "Open Current Inventory or Pending For Approval, "
                                "then select an item.", parent=self)
            return
        i = self._need_row()
        if i is None:
            return
        r = self.conn.execute("SELECT condition, condition_note FROM inventory_items WHERE lywrid=?",
                              (i,)).fetchone()
        if not r:
            return
        FormDialog(self, f"Condition of item #{i}",
                   [{"type": "info", "label": "Per-unit only. Reports still group by catalogue item, so "
                     "used and unused units roll up together (just 'HP', not 'used HP')."},
                    {"key": "cond", "label": "Condition", "type": "option",
                     "values": ["Used", "Unused"], "default": r["condition"] or "Used"},
                    {"key": "note", "label": "Note (e.g. Grade A, open box)", "type": "text",
                     "default": r["condition_note"] or ""}],
                   lambda v: (L.set_item_condition(self.conn, i, v["cond"], v["note"].strip() or None),
                              self.refresh()))

    def tool_delete_catalog_item(self):
        if self.cur_sub != "Catalogue":
            return
        i = self._need_row()
        if i is None:
            return
        u = L.catalog_usage(self.conn, i)
        if any(u.values()):
            if messagebox.askyesno("In use — hide instead?",
                                   f"'{L.catalog_label(self.conn, i)}' is used by "
                                   f"{u['listings']} listing(s), {u['purchases']} purchase(s) and "
                                   f"{u['inventory']} inventory unit(s), so it can't be deleted without "
                                   "breaking history.\n\nHide it from pickers instead?", parent=self):
                L.hide_catalog_item(self.conn, i)
                self.refresh()
            return
        if messagebox.askyesno("Delete catalogue item",
                               f"Delete '{L.catalog_label(self.conn, i)}'? It is unused.", parent=self):
            self._snapshot("delete-catalog")
            try:
                L.delete_catalog_item(self.conn, i)
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not delete", str(e), parent=self)

    def tool_hide_catalog_item(self):
        if self.cur_sub != "Catalogue":
            return
        i = self._need_row()
        if i is None:
            return
        row = self.conn.execute("SELECT display_name, is_hidden FROM catalog_items WHERE catid=?",
                                (i,)).fetchone()
        if row["is_hidden"]:
            L.unhide_catalog_item(self.conn, i)
        else:
            L.hide_catalog_item(self.conn, i)
        self.refresh()

    def tool_edit_listing(self):
        i = self._need_row()
        if i is None:
            return
        ListingDialog(self, edit_lsid=i)

    def tool_delete_listing(self):
        i = self._need_row()
        if i is None:
            return
        u = L.listing_usage(self.conn, i)
        if u["purchases"]:
            messagebox.showinfo("Can't delete", "A purchase was recorded from this listing, so it can't "
                                "be deleted (that would orphan the purchase). Edit it instead.", parent=self)
            return
        if messagebox.askyesno("Delete listing", f"Delete listing #{i}?", parent=self):
            self._snapshot("delete-listing")
            try:
                L.delete_listing(self.conn, i)
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not delete", str(e), parent=self)

    def tool_edit_account(self):
        i = self._need_row()
        if i is None:
            return
        EditAccountDialog(self, i)

    def tool_delete_account(self):
        i = self._need_row()
        if i is None:
            return
        u = L.account_usage(self.conn, i)
        if any(u.values()):
            if messagebox.askyesno("Has activity — hide instead?",
                                   "This account has transactions, so deleting it would break the ledger.\n\n"
                                   "Hide it instead?", parent=self):
                L.hide_account(self.conn, i)
                self.refresh()
            return
        if messagebox.askyesno("Delete account", f"Delete account #{i}? It is unused.", parent=self):
            self._snapshot("delete-account")
            try:
                L.delete_account(self.conn, i)
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not delete", str(e), parent=self)

    def tool_edit_buyer(self):
        i = self._need_row()
        if i is None:
            return
        o = self.conn.execute("SELECT sale_order_id, buyer_name, buyer_phone FROM sales s "
                              "JOIN sales_orders so ON s.sale_order_id=so.sale_order_id WHERE s.slsid=?",
                              (i,)).fetchone()
        if not o:
            o = self.conn.execute("SELECT sale_order_id, buyer_name, buyer_phone FROM sales_orders "
                                  "WHERE sale_order_id=?", (i,)).fetchone()
        if not o:
            return
        EditBuyerDialog(self, o["sale_order_id"], o["buyer_name"] or "", o["buyer_phone"] or "")

    # ---- Phase 3: exception events ----------------------------------------
    def _acct_map(self):
        m = {"\u2014 none \u2014": None}
        for a in L.list_accounts(self.conn):
            m[f'{a["account_name"]} ({a["account_type"]})'] = a["acctid"]
        return m

    def _resolve_order(self, i):
        r = self.conn.execute("SELECT sale_order_id FROM sales WHERE slsid=?", (i,)).fetchone()
        if r:
            return r["sale_order_id"]
        r = self.conn.execute("SELECT sale_order_id FROM sales_orders WHERE sale_order_id=?", (i,)).fetchone()
        return r["sale_order_id"] if r else None

    def tool_cancel_item(self):
        i = self._need_row()
        if i is None:
            return
        amap = self._acct_map()
        FormDialog(self, "Cancel item (seller cancelled)", [
            {"type": "info", "label": "Marks this unit Cancelled and (optionally) records the seller's "
             "refund. Other items in the same shipment are unaffected. Shipping already paid stays a "
             "sunk cost unless the seller refunded it too."},
            {"key": "amt", "label": "Refund amount", "type": "number", "default": "0"},
            {"key": "cur", "label": "Currency", "type": "option", "values": ["LYD", "USD"]},
            {"key": "rate", "label": "Rate (if USD)", "type": "number", "default": "0"},
            {"key": "acct", "label": "Refund into", "type": "option", "values": list(amap)}],
            lambda v: (self._snapshot("cancel-item"),
                       L.cancel_item(self.conn, i, _today(),
                                     refund_amount=_num(v["amt"], "Refund") if v["amt"].strip() else 0,
                                     refund_currency=v["cur"], refund_acctid=amap[v["acct"]],
                                     refund_rate=_num(v["rate"], "Rate") if v["cur"] == "USD" and v["rate"].strip() else None),
                       self.refresh()))

    def tool_reject_item(self):
        i = self._need_row()
        if i is None:
            return
        amap = self._acct_map()
        FormDialog(self, "Reject at approval", [
            {"type": "info", "label": "Reject this unit instead of accepting it. Write it off (scrap) or "
             "send it back to the seller. Its purchase cost is already booked as an expense."},
            {"key": "outcome", "label": "Outcome", "type": "option",
             "values": ["Write off (scrap)", "Return to seller"]},
            {"key": "amt", "label": "Refund / extra cost", "type": "number", "default": "0"},
            {"key": "cur", "label": "Currency", "type": "option", "values": ["LYD", "USD"]},
            {"key": "rate", "label": "Rate (if USD)", "type": "number", "default": "0"},
            {"key": "acct", "label": "Account", "type": "option", "values": list(amap)}],
            lambda v: (self._snapshot("reject-item"), self._do_reject(i, v, amap), self.refresh()))

    def _do_reject(self, lywrid, v, amap):
        rate = _num(v["rate"], "Rate") if v["cur"] == "USD" and v["rate"].strip() else None
        amt = _num(v["amt"], "Amount") if v["amt"].strip() else 0
        if v["outcome"].startswith("Write off"):
            L.write_off_item(self.conn, lywrid, _today(), extra_expense=amt, expense_currency=v["cur"],
                             expense_acctid=amap[v["acct"]])
        else:
            L.return_to_seller(self.conn, lywrid, _today(), refund_amount=amt, refund_currency=v["cur"],
                               refund_acctid=amap[v["acct"]], refund_rate=rate)

    def tool_write_off(self):
        i = self._need_row()
        if i is None:
            return
        amap = self._acct_map()
        FormDialog(self, "Write off (damaged)", [
            {"type": "info", "label": "Scraps a damaged in-stock unit. Its cost is already a sunk "
             "expense; you may optionally record an extra cost (e.g. disposal)."},
            {"key": "amt", "label": "Extra expense (optional)", "type": "number", "default": "0"},
            {"key": "cur", "label": "Currency", "type": "option", "values": ["LYD", "USD"]},
            {"key": "acct", "label": "Pay extra from", "type": "option", "values": list(amap)},
            {"key": "note", "label": "Note", "type": "text", "default": ""}],
            lambda v: (self._snapshot("write-off"),
                       L.write_off_item(self.conn, i, _today(),
                                        extra_expense=_num(v["amt"], "Expense") if v["amt"].strip() else 0,
                                        expense_currency=v["cur"], expense_acctid=amap[v["acct"]],
                                        note=v["note"] or None),
                       self.refresh()))

    def tool_customer_return(self):
        i = self._need_row()
        if i is None:
            return
        # On Finalized Sales the row is a sale ORDER (possibly multi-unit); resolve to its sold units.
        soid = i if self.conn.execute("SELECT 1 FROM sales_orders WHERE sale_order_id=?", (i,)).fetchone() \
            else self._resolve_order(i)
        if soid is None:
            return
        units = self.conn.execute(
            "SELECT s.lywrid, pl.item_name FROM sales s JOIN inventory_items inv ON s.lywrid=inv.lywrid "
            "JOIN purchase_lines pl ON inv.polnid=pl.polnid WHERE s.sale_order_id=? "
            "AND inv.status IN ('Sold','Sold Pending') ORDER BY s.lywrid", (soid,)).fetchall()
        if not units:
            messagebox.showinfo("Customer return", "This order has no returnable (sold) units.", parent=self)
            return
        if len(units) == 1:
            self._customer_return_form(units[0]["lywrid"], units[0]["item_name"])
        else:
            self._pick_unit_dialog(f"Order #{soid} — choose unit to return", units,
                                   self._customer_return_form)

    def _pick_unit_dialog(self, title, units, then_fn):
        t = self.t
        win = tk.Toplevel(self); win.title(title); win.configure(bg=t["bg"]); win.transient(self)
        win.geometry("420x320")
        tk.Label(win, text=title, bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(16, 8))
        for u in units:
            tk.Button(win, text=f"#{u['lywrid']}  {u['item_name']}", anchor="w", relief="solid", bd=1,
                      bg=t["panel"], fg=t["text"], font=("Segoe UI", 10),
                      command=lambda lyw=u["lywrid"], nm=u["item_name"]: (win.destroy(), then_fn(lyw, nm))
                      ).pack(fill="x", padx=18, pady=3)
        tk.Button(win, text="Cancel", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=18, pady=12)
        self._modalize(win)

    def _customer_return_form(self, lywrid, item_name):
        amap = self._acct_map()
        FormDialog(self, f"Customer return — #{lywrid} {item_name}", [
            {"type": "info", "label": "Records a customer returning this unit. Refunds them (reduces "
             "net revenue), then restocks the unit or closes it as returned."},
            {"key": "amt", "label": "Refund to customer", "type": "number", "default": "0"},
            {"key": "cur", "label": "Currency", "type": "option", "values": ["LYD", "USD"]},
            {"key": "acct", "label": "Refund from", "type": "option", "values": list(amap)},
            {"key": "fate", "label": "Then", "type": "option",
             "values": ["Restock (back to In Stock)", "Close (Customer Returned)"]}],
            lambda v: (self._snapshot("customer-return"),
                       L.customer_return(self.conn, lywrid, _today(),
                                         refund_amount=_num(v["amt"], "Refund") if v["amt"].strip() else 0,
                                         refund_currency=v["cur"], refund_acctid=amap[v["acct"]],
                                         restock=v["fate"].startswith("Restock")),
                       self.refresh()))

    def tool_void_order(self):
        i = self._need_row()
        if i is None:
            return
        soid = self._resolve_order(i)
        if soid is None:
            return
        if messagebox.askyesno("Void order", f"Void order #{soid}? Items return to stock and the order "
                               "is removed. (Use Customer Return for a finalized order.)", parent=self):
            self._snapshot("void-order")
            try:
                L.void_sale_order(self.conn, soid)
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not void", str(e), parent=self)

    def tool_manage_vocab(self):
        VocabularyDialog(self)

    def tool_add_listing(self):
        platform = {"eBay Listings": "eBay", "Amazon Listings": "Amazon",
                    "Facebook Listings": "Facebook", "In-Person Listings": "In-Person"}.get(self.cur_sub)
        ListingDialog(self, platform)

    # ---- Reports rendering -------------------------------------------------
    def _report_card(self, inner, title, lines):
        """lines: list of (label, value, kind) with kind in normal|total|sub|gap."""
        t = self.t
        card = tk.Frame(inner, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
        card.pack(fill="x", padx=24, pady=10)
        tk.Label(card, text=title, bg=t["card"], fg=t["text"],
                 font=("Segoe UI Semibold", 13), anchor="w").pack(fill="x", padx=18, pady=(12, 6))
        for label, value, kind in lines:
            if kind == "gap":
                tk.Frame(card, bg=t["card"], height=6).pack()
                continue
            row = tk.Frame(card, bg=t["card"]); row.pack(fill="x", padx=18, pady=2)
            pad = "      " if kind == "sub" else ""
            fnt = ("Segoe UI Semibold", 12) if kind == "total" else ("Segoe UI", 11)
            fg = t["text"] if kind == "total" else t["muted"]
            tk.Label(row, text=pad + label, bg=t["card"], fg=fg, font=fnt, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=t["card"], fg=t["text"], font=fnt, anchor="e").pack(side="right")
        tk.Frame(card, bg=t["card"], height=8).pack()

    def _type_total(self, ttype):
        r = self.conn.execute("SELECT COALESCE(SUM(amount),0) AS s FROM all_transactions "
                              "WHERE type=? AND currency='LYD'", (ttype,)).fetchone()
        return L.money(r["s"])

    # ---- Reports: shared filter bar ---------------------------------------
    def _report_filter_bar(self, parent, fields, on_apply, export=None):
        """A reusable filter row. `fields` is any of: date_from, date_to, platform,
        account, category, status. Returns a getter that yields the filter dict."""
        t = self.t
        bar = tk.Frame(parent, bg=t["content"]); bar.pack(fill="x", padx=24, pady=(8, 0))
        holders = {}

        def lab(txt):
            tk.Label(bar, text=txt, bg=t["content"], fg=t["muted"],
                     font=("Segoe UI", 9)).pack(side="left", padx=(8, 2))
        for fld in fields:
            if fld in ("date_from", "date_to"):
                lab("From" if fld == "date_from" else "To")
                v = tk.StringVar(); holders[fld] = ("date", v)
                tk.Entry(bar, textvariable=v, width=11, bg=t["panel"], fg=t["text"], relief="solid",
                         bd=1, insertbackground=t["text"]).pack(side="left")
            elif fld == "platform":
                lab("Platform"); v = tk.StringVar(value="All"); holders[fld] = ("plain", v, "platform")
                ttk.OptionMenu(bar, v, "All", "All", "eBay", "Amazon", "Facebook", "In-Person").pack(side="left")
            elif fld == "account":
                lab("Account")
                amap = {"All": None}
                for a in L.list_accounts(self.conn, include_hidden=True):
                    amap[a["account_name"]] = a["acctid"]
                v = tk.StringVar(value="All"); holders[fld] = ("map", v, amap, "acctid")
                ttk.OptionMenu(bar, v, "All", *amap.keys()).pack(side="left")
            elif fld == "category":
                lab("Category"); cats = ["All"] + L.list_categories(self.conn)
                v = tk.StringVar(value="All"); holders[fld] = ("plain", v, "category")
                ttk.OptionMenu(bar, v, "All", *cats).pack(side="left")
            elif fld == "status":
                lab("Status")
                sts = ["All"] + [r["status"] for r in
                                 self.conn.execute("SELECT status FROM inventory_statuses ORDER BY status")]
                v = tk.StringVar(value="All"); holders[fld] = ("plain", v, "status")
                ttk.OptionMenu(bar, v, "All", *sts).pack(side="left")

        def getf():
            f = {}
            for fld, h in holders.items():
                if h[0] == "date":
                    if h[1].get().strip():
                        f[fld] = h[1].get().strip()
                elif h[0] == "plain":
                    if h[1].get() != "All":
                        f[h[2]] = h[1].get()
                elif h[0] == "map":
                    if h[2].get(h[1].get()) is not None:
                        f[h[3]] = h[2][h[1].get()]
            return f
        tk.Button(bar, text="Apply", command=lambda: on_apply(getf()), relief="solid", bd=1,
                  bg=t["accent"], fg=t["on_accent"], font=("Segoe UI", 9)).pack(side="left", padx=10)
        if export:
            tk.Button(bar, text="\u2193 Export to Calc", command=lambda: export(getf()), relief="solid",
                      bd=1, bg=t["panel"], fg=t["text"], font=("Segoe UI", 9)).pack(side="left")
        return getf

    def _export_report(self, key, filt, custom_cols=None, summary=False):
        if not R.openpyxl_available():
            messagebox.showinfo("Export to Calc", "Spreadsheet export needs the 'openpyxl' package.\n\n"
                                "Install it once with:\n    pip install openpyxl", parent=self)
            return
        default = f"lyware_{key}_{_today()}.xlsx"
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=default,
                                            filetypes=[("LibreOffice Calc / Excel", "*.xlsx")], parent=self)
        if not path:
            return
        try:
            if summary:
                R.build_summary_report(self.conn, filt, path)
            elif custom_cols is not None:
                R.build_custom_report(self.conn, key, custom_cols, filt, path)
            else:
                R.build_report(self.conn, key, filt, path)
            messagebox.showinfo("Exported", f"Saved:\n{path}\n\nOpen it in LibreOffice Calc — totals "
                                "recalculate automatically.", parent=self)
        except Exception as e:  # noqa
            messagebox.showerror("Export failed", str(e), parent=self)

    def _render_reports(self, inner, crumb):
        sub = self.cur_sub
        if sub == "Overview":
            self._render_report_overview(inner, crumb)
        elif sub == "Logistics":
            self._render_report_logistics(inner, crumb)
        elif sub == "Financials":
            self._render_report_financials(inner, crumb)
        elif sub == "Market & Catalogue":
            self._render_report_market(inner, crumb)
        elif sub == "USD Rate":
            self._render_report_usdrate(inner, crumb)
        elif sub == "Accounts & FX":
            self._render_report_accounts(inner, crumb)
        elif sub == "Losses & Returns":
            self._render_report_losses(inner, crumb)
        elif sub == "Export":
            self._render_report_export(inner, crumb)

    def _render_report_overview(self, inner, crumb):
        c = self.conn
        self._title(inner, crumb, "A snapshot across logistics, money and stock")
        holder = {"box": None}

        def render(filt):
            if holder["box"]:
                holder["box"].destroy()
            box = tk.Frame(inner, bg=self.t["content"]); box.pack(fill="x")
            holder["box"] = box
            fs = L.financial_summary(c, filt)
            ds = L.dashboard_summary(c)
            self._report_card(box, "Profit & loss (filtered window)", [
                ("Revenue", D(fs["revenue"]), "normal"),
                ("Expenses", "(" + D(fs["expense"]) + ")", "sub"),
                ("FX gain / (loss)", D(fs["fx_gain_loss"]), "sub"),
                ("Net", D(fs["net"]), "total")])
            self._report_card(box, "Inventory & logistics (now)", [
                ("Units in stock", str(ds["instock_units"]), "normal"),
                ("Stock value at cost (LYD)", D(ds["instock_value"]), "total"),
                ("Pending approval", str(ds["pending_units"]), "sub"),
                ("In shipping pipeline", str(ds["shipping_units"]), "sub"),
                ("Shipping to customers", str(ds["to_customer_units"]), "sub"),
                ("Sold (lifetime)", str(ds["sold_units"]), "sub")])
            self._report_card(box, "Cash (now)", [
                ("Total LYD across accounts", D(ds["cash_lyd"]), "total"),
                ("Total USD across accounts", D(ds["cash_usd"]), "total")])
            aging = L.inventory_aging(c)
            self._report_card(box, "Inventory aging (days in stock \u2014 slow stock is tied-up capital)", [
                (f"{b['bucket']} days", f"{b['count']} unit(s) \u00B7 {D(b['value'])} LYD",
                 ("total" if b is aging[-1] and b["count"] else "normal")) for b in aging])
        getf = self._report_filter_bar(inner, ["date_from", "date_to"], render,
                                       export=lambda f: self._export_report("summary", f, summary=True))
        render(getf())

    def _render_report_logistics(self, inner, crumb):
        c = self.conn
        self._title(inner, crumb, "The full inbound timeline of every unit")
        host = {"tbl": None}

        def render(filt):
            if host["tbl"] and host["tbl"].master:
                host["tbl"].master.destroy()
            wrap = tk.Frame(inner, bg=self.t["content"]); wrap.pack(fill="both", expand=True)
            rows = []
            for r in L.logistics_report(c, filt):
                rows.append((str(r["lywrid"]), (r["lywrid"], r["item"], r["status"], r["method"] or "\u2014",
                             r["purchased"] or "\u2014", r["us_warehouse"] or "\u2014",
                             r["libya_warehouse"] or "\u2014", r["local_sent"] or "\u2014",
                             r["local_office"] or "\u2014", r["picked_up"] or "\u2014")))
            host["tbl"] = self._make_table(
                wrap, ["Unit", "Item", "Status", "Method", "Purchased", "US whse", "LY whse",
                       "Local sent", "Local office", "Picked up"],
                [50, 190, 120, 90, 95, 95, 95, 95, 95, 95], rows, height=16)
        getf = self._report_filter_bar(inner, ["category", "status"], render,
                                       export=lambda f: self._export_report("logistics", f))
        render(getf())

    def _render_report_financials(self, inner, crumb):
        c = self.conn
        self._title(inner, crumb, "Atomized revenue and expenses — filter by window or account")
        host = {"box": None}

        def render(filt):
            if host["box"]:
                host["box"].destroy()
            box = tk.Frame(inner, bg=self.t["content"]); box.pack(fill="both", expand=True)
            host["box"] = box
            fs = L.financial_summary(c, filt)
            lines = [("Revenue", D(fs["revenue"]), "normal"),
                     ("Expenses", "(" + D(fs["expense"]) + ")", "total")]
            for tp, amt in sorted(fs["expense_by_type"].items()):
                lines.append(("    " + tp.replace("_", " "), "(" + D(amt) + ")", "sub"))
            lines += [("FX gain / (loss)", D(fs["fx_gain_loss"]), "sub"),
                      ("Net", D(fs["net"]), "total")]
            self._report_card(box, "Summary", lines)
            rows = [(str(r["trnsid"]), (r["trnsid"], r["date"], r["account_name"], r["type"],
                     r["category"], D(r["amount"]), r["currency"]))
                    for r in L.transactions_report(c, filt)]
            self._make_table(box, ["ID", "Date", "Account", "Type", "Category", "Amount", "Cur"],
                             [50, 100, 160, 130, 90, 120, 50], rows, multi=True, height=12)
        getf = self._report_filter_bar(inner, ["date_from", "date_to", "account"], render,
                                       export=lambda f: self._export_report("transactions", f))
        render(getf())

    def _render_report_losses(self, inner, crumb):
        c = self.conn
        self._title(inner, crumb, "Cancelled, written-off and returned units — your loss & recovery ledger")
        host = {"box": None}

        def render(filt):
            if host["box"]:
                host["box"].destroy()
            box = tk.Frame(inner, bg=self.t["content"]); box.pack(fill="both", expand=True)
            host["box"] = box
            ls = L.losses_summary(c, filt)
            bits = ", ".join(f"{k}: {v}" for k, v in ls["by_status"].items()) or "none"
            self._report_card(box, "Summary", [
                ("Closed units", str(ls["count"]), "normal"),
                ("By outcome", bits, "sub"),
                ("Sunk cost (owned units lost)", D(ls["sunk_cost"]), "sub"),
                ("Recovered / refunded (net)", D(ls["recovery"]), "sub"),
                ("Net impact", D(ls["net"]), "total")])
            rows = []
            for r in L.losses_report(c, filt):
                rows.append((str(r["lywrid"]), (r["lywrid"], r["item"], r["status"],
                             r["date"] or "\u2014", D(r["cost"]), D(r["recovery"]), D(r["net"]),
                             r["note"] or "\u2014")))
            self._make_table(box, ["Unit", "Item", "Outcome", "Date", "Sunk cost", "Recovery",
                                   "Net", "Note"],
                             [50, 180, 130, 95, 110, 110, 110, 160], rows, height=12)
        getf = self._report_filter_bar(inner, ["date_from", "date_to", "status", "category"], render,
                                       export=lambda f: self._export_report("losses", f))
        render(getf())

    def _render_report_market(self, inner, crumb):
        c = self.conn
        t = self.t
        self._title(inner, crumb, "Per-item market research across listings, purchases and sales")
        alltime = self._toggle_bar(inner, "mkt_alltime",
                                   "All time \u2014 ignore the 90-day market window "
                                   "(archived listings stay excluded)")
        # --- attribute columns: shown right after the item name; items missing ANY
        #     selected attribute are excluded (a precise product-class lens) ---
        sel_attrs = list(self.view_flags.get("mkt_attrs") or [])
        abar = tk.Frame(inner, bg=t["content"]); abar.pack(fill="x", padx=24, pady=(0, 2))
        tk.Label(abar, text="Attribute columns:", bg=t["content"], fg=t["muted"],
                 font=("Segoe UI", 9)).pack(side="left")

        def _set_attrs(new):
            self.view_flags["mkt_attrs"] = new
            self._render_content()

        for a in sel_attrs:
            tk.Button(abar, text=f"{a} \u2715", relief="solid", bd=1, bg=t["panel"], fg=t["text"],
                      font=("Segoe UI", 9),
                      command=lambda a=a: _set_attrs([x for x in sel_attrs if x != a])
                      ).pack(side="left", padx=3)

        def _add_attr():
            taken = {x.lower() for x in sel_attrs}
            opts = [n for n in L.list_attribute_names(c) if n.lower() not in taken]
            if not opts:
                messagebox.showinfo("No attributes", "Every attribute is already a column.",
                                    parent=self)
                return
            SearchPickerDialog(self, "Add attribute column", opts,
                               lambda v: _set_attrs(sel_attrs + [v]),
                               subtitle="Items without this attribute will be hidden from "
                                        "the report.")
        tk.Button(abar, text="\uFF0B Add column", relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], font=("Segoe UI", 9), command=_add_attr).pack(side="left", padx=6)
        if sel_attrs:
            tk.Label(abar, text="(items missing any of these are hidden)", bg=t["content"],
                     fg=t["muted"], font=("Segoe UI", 8)).pack(side="left", padx=6)
        host = {"box": None}

        def render(filt):
            if host["box"]:
                host["box"].destroy()
            box = tk.Frame(inner, bg=self.t["content"]); box.pack(fill="both", expand=True)
            host["box"] = box
            rows = []
            days = None if alltime else 90
            amap = L.catalog_attributes_map(c) if sel_attrs else {}
            keys = [a.lower() for a in sel_attrs]
            for r in L.catalog_performance(c, filt, market_days=days):
                if sel_attrs:
                    have = amap.get(r["catid"], {})
                    if not all(k in have for k in keys):
                        continue
                    attr_vals = [(have.get(k) or "").strip() or "\u2014" for k in keys]
                else:
                    attr_vals = []
                m = lambda v: D(v) if v is not None else "\u2014"
                local = (f'{D(r["local_value_avg"])} (n={r["local_value_n"]})'
                         if r["local_value_avg"] is not None else "\u2014")
                rows.append((str(r["catid"]), (r["item"], *attr_vals, r["category"], local,
                             r["times_listed"], m(r["avg_listing_price"]), r["qty_purchased"],
                             m(r["avg_purchase_cost"]), r["qty_sold"], m(r["avg_sale_price"]),
                             D(r["sale_volume"]), m(r["avg_margin"]))))
            scope = "all time" if alltime else "90d"
            headers = ["Item", *sel_attrs, "Category", f"Local value ({scope})", "Listed",
                       "Avg list (LYD)", "Bought", "Avg cost", "Sold", "Avg sale",
                       "Volume", "Avg margin"]
            widths = [160, *([90] * len(sel_attrs)), 90, 130, 55, 90, 55, 90, 50, 90, 95, 90]
            tbl = self._make_table(box, headers, widths, rows, height=14)
            tbl.bind("<Double-1>", lambda e: self._market_drilldown(e), add="+")
            tk.Label(box, text="Double-click an item for its listings and sales; the drilldown's "
                     "\U0001F4C8 button opens the full market-value view.",
                     bg=self.t["content"], fg=self.t["muted"], font=("Segoe UI", 9)).pack(
                anchor="w", padx=24, pady=(0, 8))
        getf = self._report_filter_bar(inner, ["platform", "category", "date_from", "date_to"], render,
                                       export=lambda f: self._export_report("catalogue", f))
        render(getf())

    def _market_drilldown(self, event):
        iid = event.widget.identify_row(event.y)
        if not iid:
            return
        catid = int(iid)
        t = self.t
        win = tk.Toplevel(self); win.title("Item detail"); win.configure(bg=t["bg"])
        win.transient(self); win.geometry("640x460")
        head = tk.Frame(win, bg=t["bg"]); head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text=L.catalog_label(self.conn, catid), bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        tk.Button(head, text="\U0001F4C8 Market value", relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], font=("Segoe UI", 9),
                  command=lambda: self._market_popup(catid)).pack(side="right")
        nb = tk.Frame(win, bg=t["bg"]); nb.pack(fill="both", expand=True, padx=18, pady=6)
        tk.Label(nb, text="Listings", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        lt = ttk.Treeview(nb, columns=("plat", "qty", "price"), show="headings", height=6)
        for cc, txt, w in [("plat", "Platform", 120), ("qty", "Qty", 60), ("price", "Unit price", 110)]:
            lt.heading(cc, text=txt); lt.column(cc, width=w)
        lt.pack(fill="x")
        for r in self.conn.execute(
                "SELECT al.platform, li.quantity, li.unit_price FROM listing_items li "
                "JOIN all_listings al ON li.lsid=al.lsid WHERE li.catid=? ORDER BY al.lsid DESC", (catid,)):
            lt.insert("", "end", values=(r["platform"], r["quantity"],
                      D(r["unit_price"]) if r["unit_price"] is not None else "\u2014"))
        tk.Label(nb, text="Sales", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(8, 0))
        stt = ttk.Treeview(nb, columns=("order", "price", "status"), show="headings", height=6)
        for cc, txt, w in [("order", "Order", 70), ("price", "Sale price", 110), ("status", "Status", 110)]:
            stt.heading(cc, text=txt); stt.column(cc, width=w)
        stt.pack(fill="x")
        for r in self.conn.execute(
                "SELECT so.sale_order_id, s.sale_price, so.status FROM sales s "
                "JOIN sales_orders so ON s.sale_order_id=so.sale_order_id JOIN inventory_items i "
                "ON s.lywrid=i.lywrid WHERE i.catid=? ORDER BY so.sale_order_id DESC", (catid,)):
            stt.insert("", "end", values=(r["sale_order_id"], D(r["sale_price"]), r["status"]))
        tk.Button(win, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=18, pady=12)
        self._modalize(win)

    def _render_report_usdrate(self, inner, crumb):
        """The CURRENT market USD->LYD rate used to value LISTED items in reports.
        Deliberately separate from FX batches: batches freeze what your OWNED dollars
        cost you (cost basis, set at purchase); this rate answers what a $-priced
        listing is worth on the street today, and it changes often."""
        t = self.t
        self._title(inner, crumb, "The market rate that converts USD listing values to LYD in reports")
        cur = L.get_market_rate(self.conn)
        card = tk.Frame(inner, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
        card.pack(fill="x", padx=24, pady=(8, 4))
        top = tk.Frame(card, bg=t["card"]); top.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(top, text="Current market rate", bg=t["card"], fg=t["muted"],
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Label(top, text=(f"1 USD = {D(cur)} LYD" if cur is not None else "not set"),
                 bg=t["card"], fg=(t["accent"] if cur is not None else t["muted"]),
                 font=("Segoe UI Semibold", 16)).pack(side="right")
        row = tk.Frame(card, bg=t["card"]); row.pack(fill="x", padx=16, pady=(2, 6))
        tk.Label(row, text="New rate (LYD per 1 USD)", bg=t["card"], fg=t["muted"],
                 font=("Segoe UI", 10)).pack(side="left")
        rv = tk.StringVar()
        ent = tk.Entry(row, textvariable=rv, width=12, bg=t["panel"], fg=t["text"], relief="solid",
                       bd=1, insertbackground=t["text"])
        ent.pack(side="left", padx=8)

        def apply_rate(_e=None):
            try:
                L.set_market_rate(self.conn, _num(rv.get(), "Market rate"))
                self.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Could not set rate", str(e), parent=self)
        ent.bind("<Return>", apply_rate)
        tk.Button(row, text="Set rate", command=apply_rate, relief="solid", bd=1,
                  bg=t["accent"], fg=t["on_accent"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(card, text="Affects the LYD value of USD-priced LISTINGS everywhere in reports, "
                 "the moment you change it. It never touches FX batches or item cost basis \u2014 "
                 "those stay frozen at the rate your dollars were actually bought at.",
                 bg=t["card"], fg=t["muted"], font=("Segoe UI", 9), wraplength=760,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 12))
        tk.Label(inner, text="Rate history", bg=t["content"], fg=t["text"],
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=24, pady=(10, 0))
        rows = [(str(i), (f'1 USD = {D(h["rate"])} LYD', h["date"], h["time"]))
                for i, h in enumerate(L.market_rate_history(self.conn))]
        self.cur_table = self._make_table(inner, ["Rate", "Date", "Time"],
                                          [220, 120, 100], rows, height=10)

    def _render_report_accounts(self, inner, crumb):
        c = self.conn
        self._title(inner, crumb, "Account balances and the USD conversion market over time")
        arows = [(str(r["acctid"]), (r["acctid"], r["account"], r["type"], D(r["lyd"]), D(r["usd"]),
                  "hidden" if r["hidden"] else "active", r["created"]))
                 for r in L.accounts_report(c)]
        tk.Label(inner, text="Accounts", bg=self.t["content"], fg=self.t["text"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=24, pady=(6, 0))
        self._make_table(inner, ["ID", "Account", "Type", "LYD", "USD", "State", "Created"],
                         [50, 200, 120, 140, 140, 80, 100], arows, height=7)
        tk.Label(inner, text="USD conversion market (rate = LYD per USD)", bg=self.t["content"],
                 fg=self.t["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=24, pady=(10, 0))
        host = {"tbl": None}

        def render(filt):
            if host["tbl"] and host["tbl"].master:
                host["tbl"].master.destroy()
            wrap = tk.Frame(inner, bg=self.t["content"]); wrap.pack(fill="both", expand=True)
            rows = [(str(i), (r["date"], r["account"], D(r["usd"]), D(r["lyd_cost"]), D(r["rate"]),
                     r["source"])) for i, r in enumerate(L.fx_report(c, filt))]
            host["tbl"] = self._make_table(
                wrap, ["Date", "Account", "USD", "LYD cost", "Rate", "Source"],
                [100, 180, 110, 120, 90, 110], rows, height=9)
        getf = self._report_filter_bar(inner, ["date_from", "date_to", "account"], render,
                                       export=lambda f: self._export_report("fx", f))
        render(getf())

    def _render_report_export(self, inner, crumb):
        self._title(inner, crumb, "Generate print-ready LibreOffice Calc workbooks")
        t = self.t
        if not R.openpyxl_available():
            tk.Label(inner, text="Spreadsheet export needs the 'openpyxl' package. Install it once with:\n"
                     "    pip install openpyxl", bg=t["content"], fg=t["muted"], font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", padx=24, pady=12)
        # shared filter applied to whichever report you export
        getf = self._report_filter_bar(inner, ["date_from", "date_to", "platform", "category",
                                               "account", "status"], lambda f: None)
        tk.Label(inner, text="The filter above is applied to whichever report you export. "
                 "Pick a preset, or build a custom one.", bg=t["content"], fg=t["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(2, 8))
        grid = tk.Frame(inner, bg=t["content"]); grid.pack(fill="x", padx=18)
        for i, (key, label, desc) in enumerate(R.REPORTS):
            card = tk.Frame(grid, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
            r, cc = divmod(i, 2)
            card.grid(row=r, column=cc, padx=8, pady=8, sticky="nsew")
            tk.Label(card, text=label, bg=t["card"], fg=t["text"], font=("Segoe UI Semibold", 12),
                     anchor="w").pack(fill="x", padx=14, pady=(10, 2))
            tk.Label(card, text=desc, bg=t["card"], fg=t["muted"], font=("Segoe UI", 9),
                     wraplength=300, justify="left", anchor="w").pack(fill="x", padx=14)
            brow = tk.Frame(card, bg=t["card"]); brow.pack(fill="x", padx=14, pady=10)
            tk.Button(brow, text="Export", command=lambda k=key: self._export_report(k, getf()),
                      relief="solid", bd=1, bg=t["accent"], fg=t["on_accent"], width=10).pack(side="left")
            tk.Button(brow, text="Custom\u2026", command=lambda k=key: self._custom_report_dialog(k, getf()),
                      relief="solid", bd=1, bg=t["panel"], fg=t["text"], width=10).pack(side="left", padx=6)
        for cc in range(2):
            grid.columnconfigure(cc, weight=1, uniform="rep")
        # the printable financial summary
        sumcard = tk.Frame(inner, bg=t["card"], highlightbackground=t["accent"], highlightthickness=2)
        sumcard.pack(fill="x", padx=26, pady=12)
        tk.Label(sumcard, text="Financial summary (printable P&L + transaction detail)", bg=t["card"],
                 fg=t["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=14, pady=(10, 2))
        tk.Button(sumcard, text="Export financial summary",
                  command=lambda: self._export_report("summary", getf(), summary=True), relief="solid",
                  bd=1, bg=t["accent"], fg=t["on_accent"]).pack(anchor="w", padx=14, pady=10)

    def _custom_report_dialog(self, key, filt):
        t = self.t
        cols = R.report_columns(key)
        win = tk.Toplevel(self); win.title("Custom report"); win.configure(bg=t["bg"])
        win.transient(self); win.geometry("360x440")
        tk.Label(win, text="Choose columns to include", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(16, 8))
        vars = {}
        for h, _kind in cols:
            v = tk.BooleanVar(value=True); vars[h] = v
            tk.Checkbutton(win, text=h, variable=v, bg=t["bg"], fg=t["text"], selectcolor=t["panel"],
                           activebackground=t["bg"], anchor="w", font=("Segoe UI", 10), bd=0,
                           highlightthickness=0).pack(fill="x", padx=22)

        def go():
            chosen = [h for h, v in vars.items() if v.get()]
            if not chosen:
                messagebox.showinfo("Custom report", "Pick at least one column.", parent=win)
                return
            win.destroy()
            self._export_report(key, filt, custom_cols=chosen)
        _btnrow(win, t, go, "Export")
        self._modalize(win)

    # ---- sub-page mechanism ------------------------------------------------
    def _show_subpage(self, render_fn):
        for w in self.content_wrap.winfo_children():
            w.destroy()
        t = self.t
        topbar = tk.Frame(self.content_wrap, bg=t["content"])
        topbar.pack(fill="x")
        back = tk.Label(topbar, text="\u2039  Back", bg=t["content"], fg=t["accent"],
                        font=("Segoe UI Semibold", 11), cursor="hand2", padx=24, pady=8)
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: self._render_content())
        inner = self._scrollable(self.content_wrap)
        render_fn(inner)

    # ---- Home / dashboard --------------------------------------------------
    def _render_home(self, inner):
        t = self.t
        grid = tk.Frame(inner, bg=t["content"])
        grid.pack(fill="x", padx=18, pady=4)
        stats = [("Current inventory", "inventory", False),
                 ("Items shipping to shop", "to_shop", False),
                 ("Sales", "sales", False),
                 ("Items shipping to customers", "to_customer", False),
                 ("Total revenue", "revenue", True),
                 ("Total expenses", "expenses", True)]
        for i, (title, key, is_money) in enumerate(stats):
            r, c = divmod(i, 3)
            self._graph_card(grid, title, key, is_money).grid(
                row=r, column=c, padx=12, pady=12, sticky="nsew")
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="g")
        self._home_bubbles(inner)

    def _home_bubbles(self, inner):
        """A scrollable second band of at-a-glance numbers mirroring the Reports tab."""
        t = self.t
        ds = L.dashboard_summary(self.conn)
        tk.Label(inner, text="At a glance", bg=t["content"], fg=t["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=30, pady=(10, 0))
        tk.Label(inner, text="A summary of what you'd find in Reports. Open Reports for detail and exports.",
                 bg=t["content"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=30)
        bubbles = [
            ("Stock value (LYD)", D(ds["instock_value"]), "Inventory \u203A at cost"),
            ("Pending approval", str(ds["pending_units"]), "units awaiting your OK"),
            ("In shipping pipeline", str(ds["shipping_units"]), "units inbound to shop"),
            ("Cash on hand (LYD)", D(ds["cash_lyd"]), "across all accounts"),
            ("USD on hand", D(ds["cash_usd"]), "across all accounts"),
            ("This month — revenue", D(ds["month_revenue"]), "LYD, current month"),
            ("This month — expenses", D(ds["month_expense"]), "LYD, current month"),
            ("This month — net", D(ds["month_net"]), "revenue \u2212 expenses + FX"),
            ("Open listings", str(ds["open_listings"]), "across all platforms"),
            ("Catalogue items", str(ds["catalog_items"]), "item types on file"),
            ("Sold (lifetime)", str(ds["sold_units"]), "units finalized"),
            ("Closed / returned", str(L.losses_summary(self.conn)["count"]), "cancelled / written off / returned"),
            ("Top seller", ds["top_item"], "by units sold"),
        ]
        grid = tk.Frame(inner, bg=t["content"]); grid.pack(fill="x", padx=18, pady=6)
        for i, (label, value, sub) in enumerate(bubbles):
            r, c = divmod(i, 4)
            card = tk.Frame(grid, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            tk.Label(card, text=label, bg=t["card"], fg=t["muted"], font=("Segoe UI", 10),
                     anchor="w").pack(fill="x", padx=14, pady=(12, 0))
            tk.Label(card, text=value, bg=t["card"], fg=t["text"], font=("Segoe UI Semibold", 17),
                     anchor="w").pack(fill="x", padx=14)
            tk.Label(card, text=sub, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8),
                     anchor="w").pack(fill="x", padx=14, pady=(0, 10))
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="hb")

    def _graph_card(self, parent, title, key, is_money):
        t = self.t
        card = tk.Frame(parent, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
        top = tk.Frame(card, bg=t["card"])
        top.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(top, text=title, bg=t["card"], fg=t["muted"], font=("Segoe UI", 10),
                 anchor="w").pack(side="left")
        val = tk.Label(top, text="", bg=t["card"], fg=t["text"], font=("Segoe UI Semibold", 18))
        val.pack(side="right")
        cv = tk.Canvas(card, width=348, height=150, bg=t["card"], highlightthickness=0)
        cv.pack(padx=10, pady=(6, 2))
        bottom = tk.Frame(card, bg=t["card"])
        bottom.pack(fill="x", padx=14, pady=(0, 8))
        wide = tk.BooleanVar(value=False)

        def redraw():
            self._draw_graph(cv, key, 30 if wide.get() else 7, is_money, val)
        tk.Radiobutton(bottom, text="7 days", variable=wide, value=False, command=redraw, bg=t["card"],
                       fg=t["muted"], selectcolor=t["panel"], activebackground=t["card"],
                       font=("Segoe UI", 8), bd=0, highlightthickness=0).pack(side="left")
        tk.Radiobutton(bottom, text="30 days", variable=wide, value=True, command=redraw, bg=t["card"],
                       fg=t["muted"], selectcolor=t["panel"], activebackground=t["card"],
                       font=("Segoe UI", 8), bd=0, highlightthickness=0).pack(side="left")
        redraw()
        return card

    def _draw_graph(self, cv, key, days, is_money, val_lbl):
        t = self.t
        cv.delete("all")
        series = L.home_stat_series(self.conn, key, days)
        vals = [float(v) for _, v in series]
        today_val = vals[-1] if vals else 0
        val_lbl.configure(text=(D(today_val) if is_money else str(int(today_val))))
        W, H, padx, padt, padb = 348, 150, 26, 14, 24
        hi, lo = max(vals + [0]), min(vals + [0])
        if hi == lo:
            hi = lo + 1
        n = len(vals)

        def X(i):
            return padx + (W - 2 * padx) * (i / max(n - 1, 1))

        def Y(v):
            return H - padb - (v - lo) / (hi - lo) * (H - padt - padb)

        cv.create_line(padx, H - padb, W - padx, H - padb, fill=t["divider"])
        pts = [(X(i), Y(v)) for i, v in enumerate(vals)]
        if len(pts) >= 2:
            cv.create_line(*[c for p in pts for c in p], fill=t["accent"], width=2)
        coords = []
        for i, ((dt, v), (x, y)) in enumerate(zip(series, pts)):
            cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=t["accent"], outline=t["card"])
            coords.append((x, y, dt, v))
            show = (days <= 7) or (i % 5 == 0) or (i == n - 1)
            if show:
                cv.create_line(x, H - padb, x, H - padb + 4, fill=t["muted"])
                lab = dt.strftime("%a").lower() if days <= 7 else dt.strftime("%d/%m")
                cv.create_text(x, H - padb + 12, text=lab, fill=t["muted"], font=("Segoe UI", 7))
        self._bind_graph_hover(cv, coords, is_money)

    def _bind_graph_hover(self, cv, coords, is_money):
        tip = {"win": None, "lbl": None}

        def clear():
            if tip["win"]:
                tip["win"].destroy()
                tip["win"] = None

        def motion(e):
            near, best = None, 1e9
            for (x, y, dt, v) in coords:
                d = (e.x - x) ** 2 + (e.y - y) ** 2
                if d < best:
                    best, near = d, (x, y, dt, v)
            if near and best <= 120:
                x, y, dt, v = near
                txt = f"{dt.strftime('%a %d/%m')}:  {D(v) if is_money else int(v)}"
                if tip["win"] is None:
                    tip["win"] = tk.Toplevel(cv)
                    tip["win"].wm_overrideredirect(True)
                    tip["lbl"] = tk.Label(tip["win"], bg=self.t["text"], fg=self.t["bg"],
                                          font=("Segoe UI", 8), padx=5, pady=1)
                    tip["lbl"].pack()
                tip["lbl"].configure(text=txt)
                tip["win"].wm_geometry(f"+{cv.winfo_rootx() + int(x) + 8}+{cv.winfo_rooty() + int(y) - 8}")
            else:
                clear()
        cv.bind("<Motion>", motion)
        cv.bind("<Leave>", lambda e: clear())

    # ---- toggles / panels --------------------------------------------------
    def toggle_quickstart(self):
        self.qs_collapsed = not self.qs_collapsed
        self._repack_body()

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        L.set_pref(self.conn, "theme", self.theme_name)
        tab, sub, qs = self.cur_tab, self.cur_sub, self.qs_collapsed
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self.qs_collapsed = qs
        self.select_tab(tab)
        if sub:
            self.select_sub(sub)

    def _quickstart(self, label):
        if label == "Show Statistics":
            self.select_tab("Home")
        elif label == "Recharge Card":
            self.select_tab("Accounts"); self.select_sub("Cash Accounts")
            messagebox.showinfo("Recharge", "Pick the funding account, then use 'Recharge A Card'.", parent=self)
        elif label == "New Purchase":
            MakePurchaseDialog(self)
        elif label == "New Sale Order":
            self.select_tab("Inventory"); self.select_sub("Current Inventory")
            messagebox.showinfo("New sale order",
                                "Select one or more in-stock items, then use 'Sell Order'.", parent=self)
        else:
            messagebox.showinfo("Quickstart", f"'{label}' is wired in a later stage.", parent=self)

    def _export_backup(self, parent):
        """Consistent snapshot to a user-chosen location (USB stick / cloud folder) — an
        off-machine copy, so one dead disk can't take both the data and the backups."""
        from datetime import datetime as _dt
        path = filedialog.asksaveasfilename(
            parent=parent, defaultextension=".db", title="Export backup to\u2026",
            initialfile=f"lyware_backup_{_dt.now().strftime('%Y%m%d')}.db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        try:
            L.export_backup(path, DB_FILE)
            messagebox.showinfo("Backup exported", f"Consistent snapshot written to:\n{path}\n\n"
                                "Keep a copy off this machine.", parent=parent)
        except Exception as e:  # noqa
            messagebox.showerror("Could not export", str(e), parent=parent)

    def _health_check(self, parent):
        """One-click consistency audit: SQLite integrity + LYWARE's own invariants."""
        t = self.t
        results = L.health_check(self.conn)
        win = tk.Toplevel(parent); win.configure(bg=t["bg"]); win.title("Database health check")
        win.transient(parent)
        bad = [r for r in results if not r["ok"]]
        head = ("\u2705 All checks passed \u2014 the database is consistent."
                if not bad else f"\u26A0 {len(bad)} check(s) need attention.")
        tk.Label(win, text="Database health check", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(win, text=head, bg=t["bg"], fg=(t["text"] if not bad else "#c0392b"),
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 8))
        btnbar = tk.Frame(win, bg=t["bg"]); btnbar.pack(side="bottom", fill="x")
        tk.Button(btnbar, text="Close", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=20, pady=10)
        body_outer = tk.Frame(win, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
        body_outer.pack(fill="both", expand=True, padx=20, pady=4)
        body = self._scroll_host(body_outer)
        for r in results:
            row = tk.Frame(body, bg=t["card"]); row.pack(fill="x", padx=10, pady=3)
            tk.Label(row, text=("\u2705" if r["ok"] else "\u274C"), bg=t["card"],
                     font=("Segoe UI", 10)).pack(side="left")
            tk.Label(row, text=r["check"] + (f" \u2014 {r['detail']}" if r["detail"] else ""),
                     bg=t["card"], fg=(t["text"] if r["ok"] else "#c0392b"), anchor="w",
                     wraplength=380, justify="left", font=("Segoe UI", 10)).pack(side="left", padx=6)
        self._fit_window(win, 480, 460)
        _modalize(win)

    def open_settings(self):
        t = self.t
        win = tk.Toplevel(self); win.title("Settings"); win.geometry("440x440")
        win.configure(bg=t["bg"]); win.transient(self)
        tk.Label(win, text="Settings", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=18, pady=(16, 8))
        row = tk.Frame(win, bg=t["bg"]); row.pack(fill="x", padx=18, pady=6)
        tk.Label(row, text="Appearance", bg=t["bg"], fg=t["muted"]).pack(side="left")
        tk.Button(row, text=f"Switch to {'dark' if self.theme_name == 'light' else 'light'} mode",
                  command=lambda: (win.destroy(), self.toggle_theme()), relief="solid", bd=1,
                  bg=t["panel"], fg=t["text"]).pack(side="right")
        rowd = tk.Frame(win, bg=t["bg"]); rowd.pack(fill="x", padx=18, pady=6)
        tk.Label(rowd, text="Demo data", bg=t["bg"], fg=t["muted"]).pack(side="left")
        tk.Button(rowd, text="Reset DB", command=lambda: self._reset_db(win), relief="solid", bd=1,
                  bg=t["panel"], fg=t["text"]).pack(side="right", padx=(6, 0))
        tk.Button(rowd, text="Load sample data", command=lambda: self._load_sample(win),
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="right")
        tk.Frame(win, bg=t["divider"], height=1).pack(fill="x", padx=18, pady=8)
        rowb = tk.Frame(win, bg=t["bg"]); rowb.pack(fill="x", padx=18, pady=6)
        tk.Label(rowb, text="Backups", bg=t["bg"], fg=t["muted"]).pack(side="left")
        tk.Button(rowb, text="Restore from backup\u2026", command=lambda: self._restore_dialog(win),
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="right", padx=(6, 0))
        tk.Button(rowb, text="Back up now", command=lambda: self._backup_now(win), relief="solid",
                  bd=1, bg=t["panel"], fg=t["text"]).pack(side="right")
        tk.Button(rowb, text="Export to\u2026", command=lambda: self._export_backup(win),
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="right", padx=(0, 6))
        rowh = tk.Frame(win, bg=t["bg"]); rowh.pack(fill="x", padx=18, pady=6)
        tk.Label(rowh, text="Database", bg=t["bg"], fg=t["muted"]).pack(side="left")
        tk.Button(rowh, text="Health check", command=lambda: self._health_check(win), relief="solid",
                  bd=1, bg=t["panel"], fg=t["text"]).pack(side="right")
        tk.Frame(win, bg=t["divider"], height=1).pack(fill="x", padx=18, pady=8)
        tk.Label(win, text="Hidden accounts (click to unhide)", bg=t["bg"], fg=t["muted"],
                 anchor="w").pack(fill="x", padx=18)
        listf = tk.Frame(win, bg=t["bg"]); listf.pack(fill="both", expand=True, padx=18, pady=6)
        any_hidden = False
        for a in L.list_accounts(self.conn, include_hidden=True):
            if a["is_hidden"]:
                any_hidden = True
                tk.Button(listf, text=f'{a["account_name"]} ({a["account_type"]})', anchor="w",
                          relief="flat", bg=t["panel"], fg=t["text"],
                          command=lambda i=a["acctid"]: (L.unhide_account(self.conn, i), win.destroy(),
                                                         self.refresh())).pack(fill="x", pady=2)
        if not any_hidden:
            tk.Label(listf, text="none", bg=t["bg"], fg=t["muted"]).pack(anchor="w")

    def _backup_now(self, win=None):
        try:
            p = L.make_backup(DB_FILE, reason="manual")
            messagebox.showinfo("Backup", f"Saved snapshot:\n{os.path.basename(p)}" if p else
                                "Nothing to back up yet.", parent=win or self)
        except Exception as e:  # noqa
            messagebox.showerror("Backup failed", str(e), parent=win or self)

    def _restore_dialog(self, parent_win=None):
        t = self.t
        backups = L.list_backups(DB_FILE)
        win = tk.Toplevel(self); win.title("Restore from backup"); win.configure(bg=t["bg"])
        win.transient(self); win.geometry("520x420")
        tk.Label(win, text="Restore from a backup", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(win, text="This replaces the current database. The present state is itself backed up "
                 "first, so this is reversible. Newest at the top.", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI", 9), wraplength=470, justify="left").pack(anchor="w", padx=18)
        listf = tk.Frame(win, bg=t["bg"]); listf.pack(fill="both", expand=True, padx=18, pady=8)
        if not backups:
            tk.Label(listf, text="No backups yet.", bg=t["bg"], fg=t["muted"]).pack(anchor="w")
        for path, label, size in backups[:40]:
            pretty = label.replace(".db", "").replace("_", "  ·  ")
            tk.Button(listf, text=f"{pretty}    ({size // 1024} KB)", anchor="w", relief="flat",
                      bg=t["panel"], fg=t["text"], font=("Segoe UI", 9),
                      command=lambda p=path: self._do_restore(p, win, parent_win)).pack(fill="x", pady=1)
        self._modalize(win)

    def _do_restore(self, path, win, parent_win=None):
        if not messagebox.askyesno("Restore", "Replace the current database with this backup?\n\n"
                                   "The app will reload from the restored data.", parent=win):
            return
        try:
            self.conn.close()
            L.restore_backup(path, DB_FILE)
            self.conn = L.open_or_create_db(DB_FILE)
            win.destroy()
            if parent_win:
                parent_win.destroy()
            self.cur_tab, self.cur_sub = "Home", None
            self.refresh()
            messagebox.showinfo("Restored", "Database restored from backup.", parent=self)
        except Exception as e:  # noqa
            try:
                self.conn = L.open_or_create_db(DB_FILE)
            except Exception:
                pass
            messagebox.showerror("Restore failed", str(e), parent=self)

    def _load_sample(self, win=None):
        try:
            if L.list_accounts(self.conn, include_hidden=True):
                if not messagebox.askyesno("Load sample", "Add sample data on top of what's here?",
                                           parent=win or self):
                    return
            c = self.conn
            # --- accounts & funding --------------------------------------------
            cash = L.add_account(c, "Cash drawer", "Cash")
            L.add_account(c, "Bank (digital)", "Digital Funds")
            card = L.add_account(c, "Online Card", "Card")
            main = L.add_account(c, "Main holding", "Cash")
            L.deposit_lyd(c, cash, 80000)
            L.deposit_lyd(c, main, 40000)
            L.recharge_card(c, cash, card, "USD", 1600, 11)
            # --- catalogue (every purchased/listed item is a real catalogue type) ---
            cb4 = L.add_catalog_item(c, "Laptop", "HP Chromebook x360 11 G3 EE", "HP", "x360 11 G3 EE",
                                     [("RAM", "4GB"), ("Storage", "32GB eMMC"), ("Touch", "Yes")])
            cb8 = L.add_catalog_item(c, "Laptop", "HP Chromebook x360 11 G3 EE", "HP", "x360 11 G3 EE",
                                     [("RAM", "8GB"), ("Storage", "64GB eMMC"), ("Touch", "Yes")])
            acer = L.add_catalog_item(c, "Laptop", "Acer Spin 311", "Acer", "Spin 311",
                                      [("RAM", "4GB"), ("Storage", "32GB eMMC")])
            ssd = L.add_catalog_item(c, "Storage", "Kingston A400 1TB SSD", "Kingston", "A400",
                                     [("Capacity", "1TB"), ("Form", "2.5in SATA")])
            mon = L.add_catalog_item(c, "Monitor", "Dell 27in QHD", "Dell", "S2721DS",
                                     [("Size", "27in"), ("Resolution", "QHD")])
            # --- listings (priced) ---------------------------------------------
            l1 = L.add_listing(c, "eBay", currency="USD", seller_name="techsurplus_us",
                               phone_number="+1-503-555-0110", date_of_listing="2026-06-05",
                               reference="3855512340")
            L.add_listing_items(c, l1, [(cb4, 4, 100), (cb8, 2, 130)])
            l2 = L.add_listing(c, "Amazon", currency="USD", seller_name="warehouse_deals",
                               date_of_listing="2026-06-08", reference="B0ACER311X")
            L.add_listing_items(c, l2, [(acer, 3, 95), (ssd, 5, 42)])
            l3 = L.add_listing(c, "In-Person", currency="LYD", seller_name="Tripoli market stall",
                               phone_number="0925550000", date_of_listing="2026-06-12")
            L.add_listing_items(c, l3, [(mon, 2, 1500)])

            # --- purchase 1: international (from l1), 6 items, paid shipping -----
            p1 = L.record_purchase(c, card, "techsurplus_us", "USD",
                                   [{"catid": cb4, "unit_price": 100}] * 4 + [{"catid": cb8, "unit_price": 130}] * 2,
                                   lsid=l1, delivery_method="International", purchaser_name="hafiz",
                                   shipping_cost=48, shipping_acct=card, shipping_currency="USD")
            u1 = [it["lywrid"] for it in p1["items"]]
            # split the two 8GB units into their own box (still pre-transit)
            ns1 = L.split_shipment(c, p1["shipid"], u1[4:])
            # the 8GB box: left mid-pipeline (shows in Shipping To Shop, in transit)
            L.start_international_shipment(c, ns1, tracking_number="1Z9991US")
            L.mark_arrived_us_warehouse(c, ns1, "2026-06-16")
            # drive the main 4-unit box all the way to inventory
            L.start_international_shipment(c, p1["shipid"], tracking_number="1Z9990US",
                                          freight_forwarder_name="Oregon Reship")
            L.mark_arrived_us_warehouse(c, p1["shipid"], "2026-06-14")
            L.mark_arrived_libya_warehouse(c, p1["shipid"], "2026-06-22")
            L.start_local_shipment(c, [u1[0]], shipping_office_name="Al Bayda Express",
                                   date_shipped="2026-06-23", cost=60, paying_acctid=cash, currency="LYD")
            loc = L._shipment_peers(c, u1[0], "Local", "Local Transit")[1]
            L.mark_arrived_local_office(c, loc, "2026-06-24")
            L.receive_at_shop(c, u1[0], "2026-06-25")
            for x in u1[:4]:
                L.accept_into_inventory(c, x, "2026-06-25",
                                        cost_adjustment=(25 if x == u1[0] else 0),
                                        cost_adjustment_note=("cleaning + new keys" if x == u1[0] else None))

            # --- purchase 2: international (from l2), left Awaiting + Transit ----
            p2 = L.record_purchase(c, card, "warehouse_deals", "USD",
                                   [{"catid": acer, "unit_price": 95}] * 3 + [{"catid": ssd, "unit_price": 42}] * 5,
                                   lsid=l2, delivery_method="International", purchaser_name="hafiz",
                                   shipping_cost=40, shipping_acct=card, shipping_currency="USD")
            u2 = [it["lywrid"] for it in p2["items"]]
            L.start_international_shipment(c, p2["shipid"], tracking_number="1Z7777US")  # in transit

            # --- purchase 3: in-person monitors (from l3), straight to approval -
            p3 = L.record_purchase(c, cash, "Tripoli market stall", "LYD",
                                   [{"catid": mon, "unit_price": 1500}] * 2,
                                   lsid=l3, delivery_method="In-Person", purchaser_name="hafiz")
            u3 = [it["lywrid"] for it in p3["items"]]
            L.accept_into_inventory(c, u3[0], "2026-06-20")     # one monitor into stock

            # --- sales: one finalized, one shipping to customer ----------------
            o1 = L.commit_sale_order(c, [{"lywrid": u1[1], "price": 2400}, {"lywrid": u1[2], "price": 2400}],
                                     buyer_name="Walk-in (Salah)", buyer_phone="0913334444",
                                     requires_shipping=False)
            L.finalize_sale_order(c, o1, main, "2026-06-25")
            o2 = L.commit_sale_order(c, [{"lywrid": u3[0], "price": 2300}],
                                     buyer_name="Online (Mariam)", buyer_phone="0926667777",
                                     requires_shipping=True)
            L.ship_order_to_customer(c, o2, "Libya Post", shipping_cost=40, currency="LYD",
                                     date_shipped="2026-06-25", paying_acctid=cash)
            # u1[3] stays In Stock so Current Inventory isn't empty
            if win:
                win.destroy()
            self.refresh()
            messagebox.showinfo("Sample data", "Loaded a full sample: catalogue, listings, purchases, "
                                "a split shipment mid-pipeline, items pending approval, stock, and "
                                "both a finalized and an in-transit customer sale.", parent=self)
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=win or self)

    def _reset_db(self, win=None):
        if not messagebox.askyesno("Reset database", "Wipe ALL data and rebuild empty tables?",
                                   parent=win or self):
            return
        self.conn.close()
        L.init_db(DB_FILE)
        self.conn = L.open_or_create_db(DB_FILE)
        if win:
            win.destroy()
        self.refresh()

    def open_log(self):
        t = self.t
        win = tk.Toplevel(self); win.title("Change log"); win.geometry("700x470")
        win.configure(bg=t["bg"]); win.transient(self)
        tk.Label(win, text="Change log", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=16, pady=(14, 6))
        wrap = tk.Frame(win, bg=t["bg"]); wrap.pack(fill="both", expand=True, padx=16, pady=8)
        tree = ttk.Treeview(wrap, columns=("ts", "action", "entity", "detail"), show="headings")
        for c, w in [("ts", 150), ("action", 80), ("entity", 110), ("detail", 330)]:
            tree.heading(c, text=c); tree.column(c, width=w)
        tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")
        for r in self.conn.execute("SELECT ts, action, entity, detail FROM change_log "
                                   "ORDER BY logid DESC LIMIT 500"):
            tree.insert("", "end", values=(r["ts"], r["action"], r["entity"], r["detail"]))

    # ---- helpers -----------------------------------------------------------
    def _hoverable(self, widget, base, hover):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover), add="+")
        widget.bind("<Leave>", lambda e: widget.configure(bg=base), add="+")

    @staticmethod
    def _lerp(c1, c2, f):
        a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02X%02X%02X" % tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))

    def _hover_fade(self, widget, base, hover, steps=5, ms=14):
        """Cheap, safe hover animation: short color fade between base and hover (VIS4)."""
        state = {"job": None}

        def animate(target_from, target_to, i=0):
            widget.configure(bg=self._lerp(target_from, target_to, i / steps))
            if i < steps:
                state["job"] = widget.after(ms, lambda: animate(target_from, target_to, i + 1))
        widget.bind("<Enter>", lambda e: animate(base, hover), add="+")
        widget.bind("<Leave>", lambda e: animate(hover, base), add="+")

    def _flash_row(self, tree, iid, ms=90):
        """Brief highlight-flash on a freshly added/updated row (VIS4)."""
        try:
            tree.see(iid)
            tree.selection_set(iid)
            tree.tag_configure("flash", background=self.t["accent"], foreground=self.t["on_accent"])
            tree.item(iid, tags=("flash",))
            tree.after(2 * ms, lambda: tree.item(iid, tags=()) if tree.exists(iid) else None)
        except Exception:
            pass


# ---- Convert dialog: direction toggles which balance caps the amount -------
class ConvertDialog(tk.Toplevel):
    def __init__(self, app, acctid):
        super().__init__(app)
        self.app, self.t, self.acctid = app, app.t, acctid
        t = self.t
        self.title("Convert")
        self.configure(bg=t["bg"])
        self.resizable(False, False)
        self.transient(app)
        self.lyd = L.lyd_balance(app.conn, acctid)
        self.usd = L.fx_balance(app.conn, acctid, "USD")

        tk.Label(self, text="Convert", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 4))
        self.info = tk.Label(self, bg=t["bg"], fg=t["muted"], font=("Segoe UI", 10),
                             anchor="w", justify="left")
        self.info.pack(fill="x", padx=20)

        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20, pady=8)
        self.dir = tk.StringVar(value="LYD \u2192 USD")
        r1 = tk.Frame(body, bg=t["bg"]); r1.pack(fill="x", pady=5)
        tk.Label(r1, text="Direction", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        ttk.OptionMenu(r1, self.dir, self.dir.get(), "LYD \u2192 USD", "USD \u2192 LYD",
                       command=lambda *_: self._update_cap()).pack(side="left", fill="x", expand=True)

        r2 = tk.Frame(body, bg=t["bg"]); r2.pack(fill="x", pady=5)
        self.amt_label = tk.Label(r2, text="LYD to convert", bg=t["bg"], fg=t["muted"], width=18, anchor="w")
        self.amt_label.pack(side="left")
        self.amt = tk.StringVar()
        tk.Entry(r2, textvariable=self.amt, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"], font=("Segoe UI", 10)).pack(side="left", fill="x",
                                                                          expand=True, ipady=2)
        self.amt.trace_add("write", self._clamp)

        r3 = tk.Frame(body, bg=t["bg"]); r3.pack(fill="x", pady=5)
        tk.Label(r3, text="Rate (LYD per USD)", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        self.rate = tk.StringVar()
        tk.Entry(r3, textvariable=self.rate, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"], font=("Segoe UI", 10)).pack(side="left", fill="x",
                                                                         expand=True, ipady=2)

        btns = tk.Frame(self, bg=t["bg"]); btns.pack(fill="x", padx=20, pady=16)
        tk.Button(btns, text="Cancel", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Done", command=self._submit, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=12).pack(side="right")
        self._last = ""
        self._update_cap()
        _modalize(self)

    def _cap(self):
        return self.lyd if self.dir.get().startswith("LYD") else self.usd

    def _update_cap(self):
        lyd_to_usd = self.dir.get().startswith("LYD")
        self.amt_label.configure(text="LYD to convert" if lyd_to_usd else "USD to convert")
        self.info.configure(text=f"Account: {self.app._acct_label(self.acctid)}    "
                                 f"LYD {D(self.lyd)}  |  USD {D(self.usd)}\n"
                                 f"Capped at {D(self._cap())} "
                                 f"{'LYD' if lyd_to_usd else 'USD'}.")
        self._clamp()

    def _clamp(self, *_):
        val = self.amt.get()
        if val in ("", ".", "-"):
            self._last = val
            return
        try:
            d = Decimal(val.replace(",", ""))
        except InvalidOperation:
            self.amt.set(self._last)
            return
        if d > self._cap():
            d = self._cap()
            self.amt.set(f"{d:.4f}".rstrip("0").rstrip("."))
        self._last = self.amt.get()

    def _submit(self):
        try:
            amount = _num(self.amt.get(), "Amount")
            rate = _num(self.rate.get(), "Rate")
            if amount <= 0 or rate <= 0:
                raise ValueError("Amount and rate must be greater than zero.")
            if not messagebox.askyesno("Confirm", "Are you sure?", parent=self):
                return
            if self.dir.get().startswith("LYD"):          # LYD -> USD: buy fx
                usd = L.money(amount / rate)
                L.convert_buy(self.app.conn, self.acctid, "USD", usd, rate)
            else:                                         # USD -> LYD: sell fx
                L.convert_sell(self.app.conn, self.acctid, "USD", amount, rate)
            self.destroy()
            self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not convert", str(e), parent=self)


def _acct_dropdown(parent, theme, accounts, label, var):
    row = tk.Frame(parent, bg=theme["bg"])
    row.pack(fill="x", pady=5)
    tk.Label(row, text=label, bg=theme["bg"], fg=theme["muted"], width=18, anchor="w").pack(side="left")
    names = [f'{a["account_name"]} ({a["account_type"]})' for a in accounts]
    var.set(names[0] if names else "")
    ttk.OptionMenu(row, var, var.get(), *names).pack(side="left", fill="x", expand=True)
    return {f'{a["account_name"]} ({a["account_type"]})': a["acctid"] for a in accounts}


def _field(parent, theme, label, var, width=18):
    row = tk.Frame(parent, bg=theme["bg"])
    row.pack(fill="x", pady=5)
    tk.Label(row, text=label, bg=theme["bg"], fg=theme["muted"], width=width, anchor="w").pack(side="left")
    e = tk.Entry(row, textvariable=var, bg=theme["panel"], fg=theme["text"], relief="solid", bd=1,
                 insertbackground=theme["text"], font=("Segoe UI", 10))
    e.pack(side="left", fill="x", expand=True, ipady=2)
    return e


def _btnrow(parent, theme, done_cmd, done_text="Done"):
    btns = tk.Frame(parent, bg=theme["bg"])
    btns.pack(fill="x", padx=20, pady=16)
    tk.Button(btns, text="Cancel", command=parent.destroy, relief="solid", bd=1, bg=theme["panel"],
              fg=theme["text"], width=10).pack(side="right", padx=(8, 0))
    tk.Button(btns, text=done_text, command=done_cmd, relief="solid", bd=1, bg=theme["accent"],
              fg=theme["on_accent"], width=14).pack(side="right")
    return btns


class AcceptInventoryDialog(tk.Toplevel):
    """Accept items into stock with an optional per-item cost adjustment. A non-zero
    adjustment can now move real money: pick an account and currency, and a positive value
    is spent (expense) while a negative value is refunded back (an FX account gets a fresh
    batch at the rate you choose — or pick an existing batch's rate)."""
    def __init__(self, app, lywrids):
        super().__init__(app)
        self.app, self.t, self.conn, self.ids = app, app.t, app.conn, lywrids
        t = self.t
        self.configure(bg=t["bg"]); self.title("Accept Into Inventory"); self.transient(app)
        self.geometry("560x600")
        tk.Label(self, text="Accept into inventory", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="Optional cost adjustment per item. + spends from an account (expense), "
                 "\u2212 refunds back. Leave the account on \u201cnone\u201d for a cost-only tweak.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9), wraplength=520,
                 justify="left").pack(anchor="w", padx=20)
        drow = tk.Frame(self, bg=t["bg"]); drow.pack(fill="x", padx=20, pady=(8, 2))
        tk.Label(drow, text="Date entered", bg=t["bg"], fg=t["muted"], width=14, anchor="w").pack(side="left")
        self.date = tk.StringVar(value=_today())
        tk.Entry(drow, textvariable=self.date, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", fill="x", expand=True)

        self.acct_map = {"\u2014 none (cost only) \u2014": None}
        for a in L.list_accounts(self.conn):
            self.acct_map[f'{a["account_name"]} ({a["account_type"]})'] = a["acctid"]
        none_label = next(iter(self.acct_map))

        host = tk.Frame(self, bg=t["bg"]); host.pack(fill="both", expand=True, padx=20, pady=8)
        canvas = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar", command=canvas.yview)
        box = tk.Frame(canvas, bg=t["bg"])
        box.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=box, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        self.rows = {}
        for lid in lywrids:
            r = self.conn.execute(
                "SELECT i.catid, pl.item_name, i.lyd_cost_basis FROM inventory_items i "
                "JOIN purchase_lines pl ON i.polnid=pl.polnid WHERE i.lywrid=?", (lid,)).fetchone()
            name = L.catalog_label(self.conn, r["catid"]) if r["catid"] else r["item_name"]
            card = tk.Frame(box, bg=t["card"], highlightbackground=t["border"], highlightthickness=1)
            card.pack(fill="x", pady=4, padx=1)
            tk.Label(card, text=f"#{lid}  {name}"[:46], bg=t["card"], fg=t["text"],
                     anchor="w", font=("Segoe UI Semibold", 10)).pack(fill="x", padx=10, pady=(7, 0))
            r1 = tk.Frame(card, bg=t["card"]); r1.pack(fill="x", padx=10, pady=3)
            adj = tk.StringVar(value="0"); cur = tk.StringVar(value="LYD"); rate = tk.StringVar()
            acct = tk.StringVar(value=none_label)
            tk.Label(r1, text="adjust", bg=t["card"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left")
            tk.Entry(r1, textvariable=adj, width=8, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                     insertbackground=t["text"]).pack(side="left", padx=(3, 6))
            ttk.OptionMenu(r1, cur, "LYD", "LYD", "USD").pack(side="left")
            ttk.OptionMenu(r1, acct, none_label, *self.acct_map.keys()).pack(side="left", padx=6)
            r2 = tk.Frame(card, bg=t["card"]); r2.pack(fill="x", padx=10, pady=(0, 7))
            note = tk.StringVar()
            tk.Entry(r2, textvariable=note, width=20, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                     insertbackground=t["text"]).pack(side="left")
            tk.Label(r2, text="rate", bg=t["card"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left", padx=(8, 2))
            tk.Entry(r2, textvariable=rate, width=8, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                     insertbackground=t["text"]).pack(side="left")
            tk.Button(r2, text="\u29C9 batch", relief="solid", bd=1, bg=t["panel"], fg=t["text"],
                      font=("Segoe UI", 8), command=lambda a=acct, rv=rate: self._pick_batch_rate(a, rv)
                      ).pack(side="left", padx=4)
            self.rows[lid] = {"adj": adj, "note": note, "acct": acct, "cur": cur, "rate": rate}
        _btnrow(self, t, self._submit, "Accept")
        _modalize(self)

    def _pick_batch_rate(self, acct_var, rate_var):
        acctid = self.acct_map.get(acct_var.get())
        if not acctid:
            messagebox.showinfo("Pick a rate", "Choose the refund account first.", parent=self); return
        batches = L.account_batches(self.conn, acctid, "USD")
        if not batches:
            messagebox.showinfo("No batches", "That account has no USD batches to borrow a rate from.",
                                parent=self); return
        t = self.t
        win = tk.Toplevel(self); win.configure(bg=t["bg"]); win.title("Pick a batch rate"); win.transient(self)
        tk.Label(win, text="Refund at the rate of\u2026", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 6))
        btnbar = tk.Frame(win, bg=t["bg"]); btnbar.pack(side="bottom", fill="x")
        tk.Button(btnbar, text="Cancel", command=win.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=16, pady=10)
        body = self.app._scroll_host(win) if hasattr(self, "app") else win
        for b in batches:
            txt = f'Batch #{b["bachid"]} \u00B7 rate {D(b["rate"])} \u00B7 {D(b["fx_remaining"])} USD left ({b["source"]})'
            tk.Button(body, text=txt, anchor="w", relief="solid", bd=1, bg=t["panel"], fg=t["text"],
                      font=("Segoe UI", 9),
                      command=lambda rt=b["rate"]: (rate_var.set(str(rt)), win.destroy())
                      ).pack(fill="x", padx=16, pady=2)
        self.app._fit_window(win, 380, 320)
        _modalize(win)

    def _submit(self):
        try:
            for lid in self.ids:
                d = self.rows[lid]
                _num(d["adj"].get() or "0", "Adjustment", signed=True)
            if not messagebox.askyesno("Confirm", f"Accept {len(self.ids)} item(s) into stock?", parent=self):
                return
            for lid in self.ids:
                d = self.rows[lid]
                acctid = self.acct_map.get(d["acct"].get())
                amt = _num(d["adj"].get() or "0", "Adjustment", signed=True)
                if acctid and amt != 0:
                    L.accept_into_inventory(
                        self.conn, lid, self.date.get().strip() or _today(),
                        cost_adjustment=amt, cost_adjustment_note=d["note"].get().strip() or None,
                        adjustment_acctid=acctid, adjustment_currency=d["cur"].get(),
                        adjustment_rate=d["rate"].get().strip() or None)
                else:
                    L.accept_into_inventory(
                        self.conn, lid, self.date.get().strip() or _today(),
                        cost_adjustment=amt, cost_adjustment_note=d["note"].get().strip() or None)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not accept", str(e), parent=self)


class SplitShipmentDialog(tk.Toplevel):
    """M5: split a pre-transit shipment into subgroups (e.g. two boxes)."""
    def __init__(self, app, shipid):
        super().__init__(app)
        self.app, self.t, self.conn, self.shipid = app, app.t, app.conn, shipid
        t = self.t
        self.configure(bg=t["bg"]); self.title("Split Shipment"); self.transient(app)
        self.geometry("460x420")
        tk.Label(self, text=f"Split shipment #{shipid}", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="Tick the items to move into a NEW shipment (must leave at least one).",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        box = tk.Frame(self, bg=t["bg"]); box.pack(fill="both", expand=True, padx=20, pady=8)
        self.picks = {}
        for r in L.shipment_member_items(self.conn, shipid):
            name = L.catalog_label(self.conn, r["catid"]) if r["catid"] else r["item_name"]
            v = tk.BooleanVar(); self.picks[r["lywrid"]] = v
            tk.Checkbutton(box, text=f"#{r['lywrid']}  {name}", variable=v, bg=t["bg"], fg=t["text"],
                           selectcolor=t["panel"], activebackground=t["bg"], anchor="w",
                           font=("Segoe UI", 10), bd=0, highlightthickness=0).pack(fill="x")
        _btnrow(self, t, self._submit, "Split")
        _modalize(self)

    def _submit(self):
        chosen = [lid for lid, v in self.picks.items() if v.get()]
        if not chosen:
            messagebox.showinfo("Pick items", "Select at least one item to split off.", parent=self)
            return
        try:
            L.split_shipment(self.conn, self.shipid, chosen)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not split", str(e), parent=self)


class QuickstartEditor(tk.Toplevel):
    """M14: add / remove / reorder quickstart shortcuts (tabs, subtabs, tools)."""
    def __init__(self, app):
        super().__init__(app)
        self.app, self.t, self.conn = app, app.t, app.conn
        t = self.t
        self.configure(bg=t["bg"]); self.title("Customize Quickstart"); self.transient(app)
        self.geometry("820x600")
        self.reg = build_action_registry()
        self.labels = {a: lbl for a, _, lbl, _ in self.reg}
        cur = L.get_pref(self.conn, "quickstart", None)
        self.current = [x for x in cur.split("\u241F") if x] if cur else list(QS_DEFAULT)
        self.current = [a for a in self.current if a in self.labels]
        tk.Label(self, text="Customize Quickstart", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 8))
        cols = tk.Frame(self, bg=t["bg"]); cols.pack(fill="both", expand=True, padx=16)
        # left: all available actions grouped
        left = tk.Frame(cols, bg=t["bg"]); left.pack(side="left", fill="both", expand=True, padx=6)
        tk.Label(left, text="All operations", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        lf = tk.Frame(left, bg=t["bg"]); lf.pack(fill="both", expand=True)
        self.avail = ttk.Treeview(lf, show="tree", height=16)
        self.avail.column("#0", width=240, stretch=True)
        asb = ttk.Scrollbar(lf, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=self.avail.yview)
        self.avail.configure(yscrollcommand=asb.set)
        self.avail.pack(side="left", fill="both", expand=True); asb.pack(side="right", fill="y")
        groups = {}
        for a, e, lbl, grp in self.reg:
            groups.setdefault(grp, []).append((a, e, lbl))
        self.row_action = {}
        for grp, items in groups.items():
            gid = self.avail.insert("", "end", text=grp, open=(grp == "Shortcuts"))
            for a, e, lbl in items:
                iid = self.avail.insert(gid, "end", text=f"{e}  {lbl}")
                self.row_action[iid] = a
        tk.Button(left, text="Add \u2192", command=self._add, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"]).pack(anchor="e", pady=4)
        # right: current quickstart, reorder
        right = tk.Frame(cols, bg=t["bg"]); right.pack(side="left", fill="both", expand=True, padx=6)
        tk.Label(right, text="Your quickstart (top → bottom)", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.lb = tk.Listbox(right, bg=t["panel"], fg=t["text"], relief="solid", bd=1, height=14,
                             selectbackground=t["accent"], selectforeground=t["on_accent"],
                             highlightthickness=0, font=("Segoe UI", 10))
        self.lb.pack(fill="both", expand=True, pady=4)
        ctl = tk.Frame(right, bg=t["bg"]); ctl.pack(fill="x")
        for txt, cmd in [("\u25B2 Up", lambda: self._move(-1)), ("\u25BC Down", lambda: self._move(1)),
                         ("Remove", self._remove)]:
            tk.Button(ctl, text=txt, command=cmd, relief="solid", bd=1, bg=t["panel"],
                      fg=t["text"], width=8).pack(side="left", padx=2)
        self._reload()
        btns = tk.Frame(self, bg=t["bg"]); btns.pack(fill="x", padx=20, pady=12)
        tk.Button(btns, text="Cancel", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Save", command=self._save, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=10).pack(side="right")
        _modalize(self)

    def _reload(self):
        self.lb.delete(0, "end")
        for a in self.current:
            self.lb.insert("end", self.labels.get(a, a))

    def _add(self):
        sel = self.avail.selection()
        if not sel:
            return
        a = self.row_action.get(sel[0])
        if a and a not in self.current:
            self.current.append(a); self._reload()

    def _remove(self):
        if self.lb.curselection():
            del self.current[self.lb.curselection()[0]]; self._reload()

    def _move(self, d):
        if not self.lb.curselection():
            return
        i = self.lb.curselection()[0]; j = i + d
        if 0 <= j < len(self.current):
            self.current[i], self.current[j] = self.current[j], self.current[i]
            self._reload(); self.lb.selection_set(j)

    def _save(self):
        L.set_pref(self.conn, "quickstart", "\u241F".join(self.current))
        self.destroy()
        self.app._build_quickstart()


class MakePurchaseDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.t = app, app.t
        self.conn = app.conn
        t = self.t
        self.title("Make Purchase")
        self.configure(bg=t["bg"])
        self.transient(app)
        self.geometry("600x680")
        self.accts = L.list_accounts(app.conn)
        self.src_lsid = None
        tk.Label(self, text="Make Purchase", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="Pick items from the catalogue (or import a listing); set quantity and unit price.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20, pady=(6, 0))
        self.acct = tk.StringVar()
        self.amap = _acct_dropdown(body, t, self.accts, "Pay from", self.acct)
        last = L.get_pref(self.conn, "last.purchase_acct", None)   # QOL6: remember last account
        if last:
            for disp, aid in self.amap.items():
                if str(aid) == last:
                    self.acct.set(disp)
        self.cur = tk.StringVar(value="USD")
        r = tk.Frame(body, bg=t["bg"]); r.pack(fill="x", pady=5)
        tk.Label(r, text="Currency", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        ttk.OptionMenu(r, self.cur, "USD", "USD", "LYD").pack(side="left")
        self.deliv = tk.StringVar(value="International")
        r2 = tk.Frame(body, bg=t["bg"]); r2.pack(fill="x", pady=5)
        tk.Label(r2, text="Delivery", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        ttk.OptionMenu(r2, self.deliv, "International", "International", "Local", "In-Person",
                       command=lambda *_: self._sync_shipping()).pack(side="left")
        self.vendor = tk.StringVar(); _field(body, t, "Vendor", self.vendor)
        self.purchaser = tk.StringVar(); _field(body, t, "Purchaser name", self.purchaser)
        # M9: international shipping cost (paid immediately from the funding account)
        self.ship_cost = tk.StringVar()
        self.ship_row = tk.Frame(body, bg=t["bg"])
        tk.Label(self.ship_row, text="Shipping cost", bg=t["bg"], fg=t["muted"], width=18,
                 anchor="w").pack(side="left")
        tk.Entry(self.ship_row, textvariable=self.ship_cost, width=10, bg=t["panel"], fg=t["text"],
                 relief="solid", bd=1, insertbackground=t["text"]).pack(side="left")
        tk.Label(self.ship_row, text="(international, paid now)", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=6)
        self._sync_shipping()
        # M2/M4: import a listing
        lr = tk.Frame(self, bg=t["bg"]); lr.pack(fill="x", padx=20, pady=(8, 0))
        self.src_label = tk.Label(lr, text="No listing linked", bg=t["bg"], fg=t["muted"],
                                  font=("Segoe UI", 9))
        self.src_label.pack(side="left")
        tk.Button(lr, text="Import from listing\u2026", command=self._import_listing, relief="solid",
                  bd=1, bg=t["panel"], fg=t["text"], font=("Segoe UI", 9)).pack(side="right")

        tk.Label(self, text="Items (from catalogue)", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=20, pady=(10, 2))
        host = tk.Frame(self, bg=t["bg"], height=150); host.pack(fill="both", expand=True, padx=20)
        host.pack_propagate(False)
        canvas = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        isb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=canvas.yview)
        self.items_box = tk.Frame(canvas, bg=t["bg"])
        self.items_box.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        iwin = canvas.create_window((0, 0), window=self.items_box, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(iwin, width=e.width))
        canvas.configure(yscrollcommand=isb.set)
        canvas.pack(side="left", fill="both", expand=True); isb.pack(side="right", fill="y")
        self.lines = []
        addrow = tk.Frame(self, bg=t["bg"]); addrow.pack(fill="x", padx=20, pady=4)
        tk.Button(addrow, text="+ add item from catalogue", command=self._pick_item, relief="solid",
                  bd=1, bg=t["panel"], fg=t["text"]).pack(side="left")
        self.total_lbl = tk.Label(addrow, text="Items total: 0.00", bg=t["bg"], fg=t["text"],
                                  font=("Segoe UI Semibold", 10))   # QOL1
        self.total_lbl.pack(side="right")
        _btnrow(self, t, self._submit, "Record purchase")
        _modalize(self)

    def _sync_shipping(self):
        if self.deliv.get() == "International":
            self.ship_row.pack(fill="x", pady=5)
        else:
            self.ship_row.pack_forget()

    def _import_listing(self):
        ListingPickerDialog(self.app, on_pick=self._load_listing)

    def _load_listing(self, lsid):
        self.src_lsid = lsid
        self.src_label.configure(text=f"Linked to listing #{lsid}", fg=self.t["accent"])
        lr = self.conn.execute("SELECT currency, seller_name FROM all_listings WHERE lsid=?",
                               (lsid,)).fetchone()
        if lr and lr["currency"]:
            self.cur.set(lr["currency"])
        if lr and lr["seller_name"] and not self.vendor.get():
            self.vendor.set(lr["seller_name"])
        for r in L.get_listing_items(self.conn, lsid):
            self._add_line(r["catid"], qty=r["quantity"],
                           price=str(r["unit_price"]) if r["unit_price"] is not None else "")

    def _pick_item(self):
        CatalogPickerDialog(self.app, on_pick=self._add_line)

    def _recalc(self):
        total = 0.0
        for catid, qty, price, cond, note, _ in self.lines:
            try:
                total += float(qty.get()) * float(price.get() or 0)
            except ValueError:
                pass
        self.total_lbl.configure(text=f"Items total: {D(total)}")

    def _add_line(self, catid, qty="1", price=""):
        t = self.t
        row = tk.Frame(self.items_box, bg=t["bg"]); row.pack(fill="x", pady=2)
        tk.Label(row, text=L.catalog_label(self.conn, catid)[:24], bg=t["bg"], fg=t["text"],
                 anchor="w", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
        qv = tk.StringVar(value=str(qty)); pv = tk.StringVar(value=str(price))
        cond = tk.StringVar(value="Used"); note = tk.StringVar()
        qv.trace_add("write", lambda *_: self._recalc()); pv.trace_add("write", lambda *_: self._recalc())
        tk.Label(row, text="qty", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=qv, width=3, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", padx=2)
        tk.Label(row, text="unit", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=pv, width=7, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", padx=2)
        ttk.OptionMenu(row, cond, "Used", "Used", "Unused").pack(side="left", padx=2)
        tk.Entry(row, textvariable=note, width=9, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", padx=2)

        def remove():
            row.destroy()
            self.lines[:] = [ln for ln in self.lines if ln[-1] is not row]
            self._recalc()
        tk.Button(row, text="\u2715", command=remove, relief="flat", bg=t["bg"], fg=t["muted"],
                  width=2, cursor="hand2").pack(side="left")
        self.lines.append((catid, qv, pv, cond, note, row))
        self._recalc()

    def _submit(self):
        try:
            if not self.lines:
                raise ValueError("Add at least one item from the catalogue.")
            items = []
            for catid, qty, price, cond, note, _ in self.lines:
                q = int(qty.get())
                up = _num(price.get(), "Unit price")
                if q < 1:
                    raise ValueError("Quantity must be at least 1.")
                for _ in range(q):
                    items.append({"catid": catid, "unit_price": up,
                                  "condition": cond.get(),
                                  "condition_note": note.get().strip() or None})
            acctid = self.amap[self.acct.get()]
            ship_cost = None
            if self.deliv.get() == "International" and self.ship_cost.get().strip():
                ship_cost = _num(self.ship_cost.get(), "Shipping cost")
            if not messagebox.askyesno("Confirm", "Record this purchase?", parent=self):
                return
            L.record_purchase(self.conn, acctid, self.vendor.get() or "unknown",
                              self.cur.get(), items, lsid=self.src_lsid,
                              delivery_method=self.deliv.get(),
                              purchaser_name=self.purchaser.get() or None,
                              shipping_cost=ship_cost, shipping_acct=acctid if ship_cost else None,
                              shipping_currency=self.cur.get())
            L.set_pref(self.conn, "last.purchase_acct", str(acctid))   # QOL6
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not record purchase", str(e), parent=self)


class ListingPickerDialog(tk.Toplevel):
    """M4: searchable listing picker for importing a listing into a purchase."""
    def __init__(self, app, on_pick):
        super().__init__(app)
        self.app, self.t, self.conn, self.on_pick = app, app.t, app.conn, on_pick
        t = self.t
        self.configure(bg=t["bg"]); self.title("Pick a listing"); self.transient(app)
        self.geometry("620x460")
        tk.Label(self, text="Import from a listing", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 6))
        bar = tk.Frame(self, bg=t["bg"]); bar.pack(fill="x", padx=20)
        tk.Label(bar, text="Search:", bg=t["bg"], fg=t["muted"]).pack(side="left")
        self.q = tk.StringVar()
        tk.Entry(bar, textvariable=self.q, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", fill="x", expand=True, padx=6, ipady=2)
        self.q.trace_add("write", lambda *_: self._search())
        wrap = tk.Frame(self, bg=t["bg"]); wrap.pack(fill="both", expand=True, padx=20, pady=8)
        self.tree = ttk.Treeview(wrap, columns=("plat", "items", "seller", "val"), show="headings", height=12)
        for c, txt, w in [("plat", "Platform", 90), ("items", "Items", 250), ("seller", "Seller", 110),
                          ("val", "Value", 90)]:
            self.tree.heading(c, text=txt); self.tree.column(c, width=w)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", style="Lyware.Vertical.TScrollbar",
                           command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._use())
        btns = tk.Frame(self, bg=t["bg"]); btns.pack(fill="x", padx=20, pady=(0, 14))
        tk.Button(btns, text="Cancel", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Use listing", command=self._use, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=12).pack(side="right")
        self._search()
        _modalize(self)

    def _summary(self, lsid):
        lines = L.get_listing_items(self.conn, lsid)
        return ", ".join(f'{r["quantity"]}\u00D7 {r["display_name"]}' for r in lines) or "\u2014"

    def _search(self):
        self.tree.delete(*self.tree.get_children())
        q = self.q.get().strip().lower()
        for r in self.conn.execute("SELECT lsid, platform, seller_name FROM all_listings ORDER BY lsid DESC"):
            summary = self._summary(r["lsid"])
            blob = f'{r["platform"]} {r["seller_name"] or ""} {summary}'.lower()
            if q and q not in blob:
                continue
            val = L.listing_total(self.conn, r["lsid"])
            self.tree.insert("", "end", iid=str(r["lsid"]),
                             values=(r["platform"], summary, r["seller_name"] or "\u2014",
                                     D(val) if val else "\u2014"))

    def _use(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Pick one", "Select a listing first.", parent=self)
            return
        lsid = int(sel[0]); self.destroy(); self.on_pick(lsid)


class SellOrderDialog(tk.Toplevel):
    def __init__(self, app, lywrids):
        super().__init__(app)
        self.app, self.t, self.lywrids = app, app.t, lywrids
        t = self.t
        self.title("Sell Order")
        self.configure(bg=t["bg"])
        self.transient(app)
        tk.Label(self, text="Sell Order", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(self, text="Set a sale price for each item. Shipping applies to the whole order.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=20)
        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20, pady=8)
        hdr = tk.Frame(body, bg=t["bg"]); hdr.pack(fill="x")
        for txt, w in [("Item", 24), ("Cost", 10), ("Market", 10), ("Sale price", 12), ("Margin", 12)]:
            tk.Label(hdr, text=txt, bg=t["bg"], fg=t["muted"], width=w, anchor="w",
                     font=("Segoe UI Semibold", 9)).pack(side="left")
        self.price_vars = {}
        mvm = {}
        for lid in lywrids:                        # market medians for the pricing column
            row = app.conn.execute("SELECT catid FROM inventory_items WHERE lywrid=?", (lid,)).fetchone()
            cid = row["catid"] if row else None
            if cid is not None and cid not in mvm:
                mvm[cid] = L.market_value(app.conn, cid)["median"]
        for lid in lywrids:
            r = app.conn.execute(
                "SELECT i.catid, pl.item_name, i.total_cost FROM inventory_items i "
                "JOIN purchase_lines pl ON i.polnid=pl.polnid WHERE i.lywrid=?", (lid,)).fetchone()
            name = L.catalog_label(app.conn, r["catid"]) if r["catid"] else r["item_name"]
            med = mvm.get(r["catid"])
            cost = r["total_cost"]
            row = tk.Frame(body, bg=t["bg"]); row.pack(fill="x", pady=2)
            tk.Label(row, text=name[:32], bg=t["bg"], fg=t["text"], width=24,
                     anchor="w").pack(side="left")
            tk.Label(row, text=D(cost) if cost is not None else "\u2014",
                     bg=t["bg"], fg=t["muted"], width=10, anchor="w").pack(side="left")
            tk.Label(row, text=D(med) if med is not None else "\u2014", bg=t["bg"],
                     fg=t["accent"], width=10, anchor="w").pack(side="left")
            pv = tk.StringVar()
            tk.Entry(row, textvariable=pv, width=12, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                     insertbackground=t["text"]).pack(side="left")
            marg = tk.Label(row, text="\u2014", bg=t["bg"], fg=t["muted"], width=12, anchor="w",
                            font=("Segoe UI", 9))
            marg.pack(side="left", padx=(6, 0))

            def _upd(*_, pv=pv, marg=marg, cost=cost):     # live margin as the price is typed
                s = pv.get().strip().replace(",", "")
                try:
                    price = float(s)
                except ValueError:
                    marg.configure(text="\u2014", fg=t["muted"]); return
                if cost is None:
                    marg.configure(text="cost unknown", fg=t["muted"]); return
                m = price - float(cost)
                pct = f" ({m / float(cost) * 100:.0f}%)" if float(cost) else ""
                marg.configure(text=f"{'+' if m >= 0 else ''}{D(m)}{pct}",
                               fg=(t["text"] if m >= 0 else "#c0392b"))
            pv.trace_add("write", _upd)
            self.price_vars[lid] = pv
        self.buyer = tk.StringVar(); _field(body, t, "Buyer name", self.buyer)
        self.buyer_phone = tk.StringVar(); _field(body, t, "Buyer phone", self.buyer_phone)
        self.ship = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="Requires shipping to customer", variable=self.ship, bg=t["bg"],
                       fg=t["text"], selectcolor=t["panel"], activebackground=t["bg"],
                       font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))
        _btnrow(self, t, self._submit, "Commit order")
        _modalize(self)

    def _submit(self):
        try:
            items = []
            for lid, pv in self.price_vars.items():
                items.append({"lywrid": lid, "price": _num(pv.get(), "Sale price")})
            if not messagebox.askyesno("Confirm", "Commit this sale order?", parent=self):
                return
            L.commit_sale_order(self.app.conn, items, buyer_name=self.buyer.get() or None,
                                requires_shipping=self.ship.get(),
                                buyer_phone=self.buyer_phone.get().strip() or None)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not commit order", str(e), parent=self)


class UpdateShippingDialog(tk.Toplevel):
    """Stateful: shows only the next valid action for the item's current shipping stage."""
    def __init__(self, app, lywrid):
        super().__init__(app)
        self.app, self.t, self.lywrid = app, app.t, lywrid
        self.configure(bg=self.t["bg"])
        self.title("Update Shipping Status")
        self.transient(app)
        self.geometry("460x420")
        self.body = tk.Frame(self, bg=self.t["bg"]); self.body.pack(fill="both", expand=True)
        self._render()
        _modalize(self)

    def _intl(self):
        return self.app.conn.execute(
            "SELECT s.shipid, s.lyd_shipping_cost, ish.date_arrived_us_warehouse, ish.date_arrived_libya_warehouse "
            "FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "JOIN international_shipping ish ON ish.shipid=s.shipid "
            "WHERE si.lywrid=? AND s.shipment_type='International' ORDER BY s.shipid DESC LIMIT 1",
            (self.lywrid,)).fetchone()

    def _local_ship(self):
        return self.app.conn.execute(
            "SELECT s.shipid, s.lyd_shipping_cost, ls.date_arrived_local_office "
            "FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "JOIN local_shipping ls ON ls.shipid=s.shipid "
            "WHERE si.lywrid=? AND s.shipment_type='Local' ORDER BY s.shipid DESC LIMIT 1",
            (self.lywrid,)).fetchone()

    def _delivery(self):
        r = self.app.conn.execute(
            "SELECT po.delivery_method FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
            "JOIN purchase_orders po ON pl.poid=po.poid WHERE i.lywrid=?", (self.lywrid,)).fetchone()
        return r["delivery_method"]

    def _do(self, fn):
        try:
            fn()
            self.app.refresh()
            self._render()
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=self)

    def _local_cost_fields(self, box):
        """Cost + currency + paying-account inputs for a local leg (paid immediately)."""
        t = self.t
        cost = tk.StringVar()
        _field(box, t, "Local shipping cost", cost)
        cur = tk.StringVar(value="LYD")
        crow = tk.Frame(box, bg=t["bg"]); crow.pack(fill="x", pady=5)
        tk.Label(crow, text="Currency", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        ttk.OptionMenu(crow, cur, "LYD", "LYD", "USD").pack(side="left")
        payv = tk.StringVar()
        pmap = _acct_dropdown(box, t, L.list_accounts(self.app.conn, "Cash") +
                              L.list_accounts(self.app.conn, "Digital Funds") +
                              L.list_accounts(self.app.conn, "Card"), "Pay shipping from", payv)
        return cost, cur, payv, pmap

    def _start_local(self, office, cost, cur, payv, pmap):
        amount = _num(cost.get(), "Local shipping cost") if cost.get().strip() else None
        acct = pmap.get(payv.get()) if amount else None
        L.start_local_shipment(self.app.conn, [self.lywrid],
                               shipping_office_name=office.get() or None, date_shipped=_today(),
                               cost=amount, paying_acctid=acct, currency=cur.get())

    def _render(self):
        t = self.t
        for w in self.body.winfo_children():
            w.destroy()
        status = L.get_item_status(self.app.conn, self.lywrid)
        method = self._delivery()
        tk.Label(self.body, text="Update Shipping Status", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self.body, text=f"Item #{self.lywrid}   Method: {method}   Status: {status}",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 10))
        box = tk.Frame(self.body, bg=t["bg"]); box.pack(fill="x", padx=20)

        def entry(label, default=""):
            v = tk.StringVar(value=default)
            _field(box, t, label, v)
            return v

        def action(text, fn):
            tk.Button(self.body, text=text, command=lambda: self._do(fn), relief="solid", bd=1,
                      bg=t["accent"], fg=t["on_accent"], font=("Segoe UI Semibold", 10)).pack(
                anchor="w", padx=20, pady=10)

        if status == "Awaiting Shipment" and method == "International":
            track = entry("Tracking number"); fwd = entry("Forwarder"); wt = entry("Weight kg")
            action("Start international shipment",
                   lambda: L.start_international_shipment(
                       self.app.conn, [self.lywrid], tracking_number=track.get() or None,
                       freight_forwarder_name=fwd.get() or None, weight_kg=wt.get() or None))
        elif status == "Awaiting Shipment" and method == "Local":
            tk.Label(self.body, text="Acts on the whole shipment group. Cost is charged now.",
                     bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
            office = entry("Shipping office")
            cost, cur, payv, pmap = self._local_cost_fields(box)
            action("Start local shipment",
                   lambda: self._start_local(office, cost, cur, payv, pmap))
        elif status == "International Transit":
            intl = self._intl()
            if intl and not intl["date_arrived_us_warehouse"]:
                d = entry("US warehouse date", _today())
                action("Mark arrived at US warehouse",
                       lambda: L.mark_arrived_us_warehouse(self.app.conn, intl["shipid"], d.get()))
            else:
                flight = entry("Flight number (optional)")
                d = entry("Libya warehouse date", _today())

                def go():
                    if flight.get().strip():
                        L.update_international_shipment(self.app.conn, intl["shipid"],
                                                        flight_number=flight.get().strip())
                    L.mark_arrived_libya_warehouse(self.app.conn, intl["shipid"], d.get())
                action("Mark arrived at Libya warehouse", go)
        elif status == "At Libya Warehouse":
            tk.Label(self.body, text="Choose how the whole group reaches the shop:", bg=t["bg"],
                     fg=t["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=20)
            office = entry("Local office (for local ship)")
            cost, cur, payv, pmap = self._local_cost_fields(box)
            action("Start local shipment (whole group)",
                   lambda: self._start_local(office, cost, cur, payv, pmap))
            tk.Button(self.body, text="Personal pickup \u2192 approval queue (whole group)",
                      command=lambda: self._do(lambda: L.pickup_to_shop(self.app.conn, self.lywrid, _today())),
                      relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(anchor="w", padx=20, pady=4)
            tk.Button(self.body, text="Keep at warehouse (close)", command=self.destroy, relief="solid",
                      bd=1, bg=t["panel"], fg=t["text"]).pack(anchor="w", padx=20, pady=2)
        elif status == "Local Transit":
            d = entry("Local office arrival date", _today())
            action("Mark arrived at local office",
                   lambda: L.mark_arrived_local_office(self.app.conn, self._local_ship()["shipid"], d.get()))
        elif status == "At Local Office":
            d = entry("Received at shop date", _today())
            action("Receive at shop \u2192 approval queue (whole group)",
                   lambda: L.receive_at_shop(self.app.conn, self.lywrid, d.get()))
        else:
            tk.Label(self.body, text="No further shipping actions for this status.",
                     bg=t["bg"], fg=t["muted"], font=("Segoe UI", 11)).pack(anchor="w", padx=20, pady=10)

        active = self._intl() if status in ("International Transit", "At Libya Warehouse") else self._local_ship()
        if active and active["shipid"]:
            paid = active["lyd_shipping_cost"] is not None
            tk.Frame(self.body, bg=t["divider"], height=1).pack(fill="x", padx=20, pady=8)
            if paid:
                tk.Label(self.body, text=f"This leg already has {D(active['lyd_shipping_cost'])} LYD "
                                         f"recorded; paying again adds to it.", bg=t["bg"], fg=t["muted"],
                         font=("Segoe UI", 9)).pack(anchor="w", padx=20)
            tk.Button(self.body, text=("Add shipping cost to this leg" if paid else "Pay shipping for this leg"),
                      command=lambda sid=active["shipid"]: self._pay(sid), relief="solid", bd=1,
                      bg=t["panel"], fg=t["text"]).pack(anchor="w", padx=20, pady=4)
            if paid:
                tk.Button(self.body, text="Adjust (correct) this leg's cost",
                          command=lambda sid=active["shipid"]: self._adjust(sid), relief="solid", bd=1,
                          bg=t["panel"], fg=t["text"]).pack(anchor="w", padx=20, pady=2)

        # Undo the last shipping/inventory step (mistake correction)
        ok, why = L.can_reverse_last_status(self.app.conn, self.lywrid)
        tk.Frame(self.body, bg=t["divider"], height=1).pack(fill="x", padx=20, pady=8)
        if ok:
            tk.Button(self.body, text="\u21A9 Undo last step (whole group)", command=self._undo_last,
                      relief="solid", bd=1, bg=t["panel"], fg=t["accent"]).pack(anchor="w", padx=20, pady=2)
            tk.Label(self.body, text="Reverses only the most recent step; refunds any shipping it paid.",
                     bg=t["bg"], fg=t["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=20)
        else:
            tk.Label(self.body, text="Undo unavailable: " + why, bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI", 8), wraplength=360, justify="left").pack(anchor="w", padx=20)

    def _undo_last(self):
        if not messagebox.askyesno("Undo last step", "Reverse the most recent shipping/inventory step "
                                   "for this item's group?", parent=self):
            return
        self.app._snapshot("undo-shipping-step")
        self._do(lambda: L.reverse_last_status(self.app.conn, self.lywrid, _today()))

    def _adjust(self, shipid):
        cur = self.app.conn.execute("SELECT lyd_shipping_cost FROM shipments WHERE shipid=?",
                                    (shipid,)).fetchone()["lyd_shipping_cost"]
        accts = L.list_accounts(self.app.conn)
        amap = {f'{a["account_name"]} ({a["account_type"]})': a["acctid"] for a in accts}
        FormDialog(self.app, "Adjust shipping cost",
                   [{"key": "new", "label": f"Corrected LYD cost (now {D(cur)})", "type": "number",
                     "required": True},
                    {"key": "acct", "label": "Settle difference with", "type": "option",
                     "values": list(amap)}],
                   lambda v: (self.app._snapshot("adjust-shipping"),
                              L.adjust_shipping_cost(self.app.conn, shipid, _num(v["new"], "Cost"),
                                                     amap[v["acct"]]),
                              self.app.refresh(), self._render()))

    def _pay(self, shipid):
        accts = L.list_accounts(self.app.conn)
        amap = {f'{a["account_name"]} ({a["account_type"]})': a["acctid"] for a in accts}
        FormDialog(self.app, "Pay shipping",
                   [{"key": "acct", "label": "Pay from", "type": "option", "values": list(amap)},
                    {"key": "cost", "label": "Cost", "type": "number", "required": True},
                    {"key": "cur", "label": "Currency", "type": "option", "values": ["LYD", "USD"]}],
                   lambda v: (L.pay_shipping(self.app.conn, shipid, amap[v["acct"]],
                                             _num(v["cost"], "Cost"), v["cur"]),
                              self.app.refresh(), self._render()))


class UpdateSaleStatusDialog(tk.Toplevel):
    def __init__(self, app, order_id):
        super().__init__(app)
        self.app, self.t, self.oid = app, app.t, order_id
        t = self.t
        self.configure(bg=t["bg"])
        self.title("Update Sale Status")
        self.transient(app)
        o = app.conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (order_id,)).fetchone()
        tk.Label(self, text=f"Sale order #{order_id}", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        items = app.conn.execute(
            "SELECT pl.item_name, s.sale_price FROM sales s JOIN inventory_items i ON s.lywrid=i.lywrid "
            "JOIN purchase_lines pl ON i.polnid=pl.polnid WHERE s.sale_order_id=?", (order_id,)).fetchall()
        summary = ", ".join(f'{r["item_name"]} ({D(r["sale_price"])})' for r in items)
        tk.Label(self, text=f"Buyer: {o['buyer_name'] or '\u2014'}   Shipping: "
                            f"{'yes' if o['requires_shipping'] else 'no'}", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20)
        tk.Label(self, text=summary, bg=t["bg"], fg=t["muted"], font=("Segoe UI", 10),
                 wraplength=420, justify="left").pack(anchor="w", padx=20, pady=(2, 8))
        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20)

        if o["requires_shipping"]:
            self.office = tk.StringVar(); _field(body, t, "Postal office", self.office)
            self.cost = tk.StringVar(value="0"); _field(body, t, "Shop shipping cost", self.cost)
            self.payv = tk.StringVar()
            self.pmap = _acct_dropdown(body, t, L.list_accounts(app.conn, "Cash") +
                                       L.list_accounts(app.conn, "Digital Funds"), "Pay shipping from", self.payv)
            _btnrow(self, t, self._move_to_shipping, "Move to shipping")
        else:
            self.recv = tk.StringVar()
            self.rmap = _acct_dropdown(body, t, L.list_accounts(app.conn, "Cash") +
                                       L.list_accounts(app.conn, "Digital Funds"), "Money lands in", self.recv)
            _btnrow(self, t, self._approve, "Approve & record payment")
        _modalize(self)

    def _move_to_shipping(self):
        try:
            cost = _num(self.cost.get(), "Cost")
            if not messagebox.askyesno("Confirm", "Move this order to shipping?", parent=self):
                return
            L.ship_order_to_customer(self.app.conn, self.oid, self.office.get() or "\u2014",
                                     shipping_cost=cost, currency="LYD", date_shipped=_today(),
                                     paying_acctid=self.pmap[self.payv.get()] if cost > 0 else None)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=self)

    def _approve(self):
        try:
            if not messagebox.askyesno("Confirm", "Approve and record payment?", parent=self):
                return
            L.finalize_sale_order(self.app.conn, self.oid, self.rmap[self.recv.get()], _today())
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=self)


class ShipCustomerDialog(tk.Toplevel):
    def __init__(self, app, order_id):
        super().__init__(app)
        self.app, self.t, self.oid = app, app.t, order_id
        self.configure(bg=self.t["bg"])
        self.title("Update Status")
        self.transient(app)
        self.body = tk.Frame(self, bg=self.t["bg"]); self.body.pack(fill="both", expand=True)
        self._render()
        _modalize(self)

    def _render(self):
        t = self.t
        for w in self.body.winfo_children():
            w.destroy()
        o = self.app.conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (self.oid,)).fetchone()
        tk.Label(self.body, text=f"Order #{self.oid} to customer", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self.body, text=f"Buyer: {o['buyer_name'] or '\u2014'}   "
                                 f"Arrived: {o['date_arrived_customer'] or 'not yet'}",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 10))
        body = tk.Frame(self.body, bg=t["bg"]); body.pack(fill="x", padx=20)
        if not o["date_arrived_customer"]:
            self.d = tk.StringVar(value=_today()); _field(body, t, "Arrival date", self.d)
            tk.Button(self.body, text="Mark arrived to customer", command=self._mark, relief="solid",
                      bd=1, bg=t["accent"], fg=t["on_accent"],
                      font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=20, pady=10)
        else:
            self.recv = tk.StringVar()
            self.rmap = _acct_dropdown(body, t, L.list_accounts(self.app.conn, "Cash") +
                                       L.list_accounts(self.app.conn, "Digital Funds"), "Money lands in", self.recv)
            tk.Button(self.body, text="Approve & record payment", command=self._approve, relief="solid",
                      bd=1, bg=t["accent"], fg=t["on_accent"],
                      font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=20, pady=10)

    def _mark(self):
        try:
            L.mark_order_arrived_customer(self.app.conn, self.oid, self.d.get())
            self.app.refresh(); self._render()
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=self)

    def _approve(self):
        try:
            if not messagebox.askyesno("Confirm", "Approve and record payment?", parent=self):
                return
            L.finalize_sale_order(self.app.conn, self.oid, self.rmap[self.recv.get()], _today())
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Error", str(e), parent=self)


class AutocompleteCombobox(ttk.Combobox):
    """Combobox whose dropdown list filters to substring matches as you type."""
    def set_completion_list(self, items):
        self._all = sorted(set(x for x in items if x), key=str.lower)
        self["values"] = self._all
        self.bind("<KeyRelease>", self._on_key, add="+")

    def _on_key(self, event):
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Up", "Down", "Return",
                            "Tab", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        typed = self.get().lower()
        if not typed:
            self["values"] = self._all
        else:
            matches = [x for x in self._all if typed in x.lower()]
            self["values"] = matches or self._all


def _combo(parent, theme, label, values, default="", width=18, editable=True):
    row = tk.Frame(parent, bg=theme["bg"]); row.pack(fill="x", pady=5)
    tk.Label(row, text=label, bg=theme["bg"], fg=theme["muted"], width=18, anchor="w").pack(side="left")
    cb = ttk.Combobox(row, values=list(values), font=("Segoe UI", 10),
                      state="normal" if editable else "readonly")
    cb.set(default)
    cb.pack(side="left", fill="x", expand=True)
    return cb


class EditAccountDialog(tk.Toplevel):
    """Rename an account; the type may only change while it has no transactions."""
    def __init__(self, app, acctid):
        super().__init__(app)
        self.app, self.t, self.conn, self.acctid = app, app.t, app.conn, acctid
        t = self.t
        a = self.conn.execute("SELECT * FROM accounts WHERE acctid=?", (acctid,)).fetchone()
        self.configure(bg=t["bg"]); self.title("Edit Account"); self.transient(app)
        self.geometry("420x250")
        tk.Label(self, text=f"Edit account #{acctid}", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 8))
        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20)
        self.name = tk.StringVar(value=a["account_name"])
        _field(body, t, "Account name", self.name)
        self.has_txns = bool(L.account_usage(self.conn, acctid)["transactions"])
        self.atype = tk.StringVar(value=a["account_type"])
        trow = tk.Frame(body, bg=t["bg"]); trow.pack(fill="x", pady=5)
        tk.Label(trow, text="Type", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        if self.has_txns:
            tk.Label(trow, text=f"{a['account_type']} (locked — has transactions)", bg=t["bg"],
                     fg=t["muted"], font=("Segoe UI", 10)).pack(side="left")
        else:
            ttk.OptionMenu(trow, self.atype, a["account_type"], "Cash", "Digital Funds", "Card").pack(side="left")
        _btnrow(self, t, self._save, "Save")
        _modalize(self)

    def _save(self):
        try:
            self.app._snapshot("edit-account")
            L.edit_account(self.conn, self.acctid, account_name=self.name.get(),
                           account_type=None if self.has_txns else self.atype.get())
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not save", str(e), parent=self)


class EditBuyerDialog(tk.Toplevel):
    """Correct the buyer name / phone on a sale order."""
    def __init__(self, app, sale_order_id, name, phone):
        super().__init__(app)
        self.app, self.t, self.conn, self.soid = app, app.t, app.conn, sale_order_id
        t = self.t
        self.configure(bg=t["bg"]); self.title("Edit Buyer"); self.transient(app)
        self.geometry("420x220")
        tk.Label(self, text=f"Edit buyer — order #{sale_order_id}", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 8))
        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20)
        self.name = tk.StringVar(value=name); self.phone = tk.StringVar(value=phone)
        _field(body, t, "Buyer name", self.name)
        _field(body, t, "Buyer phone", self.phone)
        _btnrow(self, t, self._save, "Save")
        _modalize(self)

    def _save(self):
        try:
            L.edit_sale_order_meta(self.conn, self.soid, buyer_name=self.name.get().strip() or None,
                                   buyer_phone=self.phone.get().strip() or None)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not save", str(e), parent=self)


class CatalogItemDialog(tk.Toplevel):
    """Create or edit a catalog item: core fields + an arbitrary list of named
    attributes. Display name and Category are required; the rest optional."""
    def __init__(self, app, catid=None, on_saved=None, clone_from=None):
        super().__init__(app)
        self.app, self.t, self.catid, self.on_saved = app, app.t, catid, on_saved
        self.conn = app.conn
        t = self.t
        self.configure(bg=t["bg"])
        self.title("Edit Catalogue Item" if catid else
                   ("Make Similar Item" if clone_from else "Add Catalogue Item"))
        self.transient(app)
        self.geometry("520x600")
        tk.Label(self, text="Edit catalogue item" if catid else
                 ("Make a similar item (creates a NEW item)" if clone_from else
                  "Add an item to the catalogue"),
                 bg=t["bg"], fg=t["text"], font=("Segoe UI Semibold", 14)).pack(
            anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="Tweak whatever differs (e.g. one attribute) and save." if clone_from else
                 "Display name and category are required; everything else is optional.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)

        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20, pady=(8, 0))
        self.display = self._autocomplete_field(body, "Display name",
                                                L.autocomplete_display_names(self.conn))
        self.category = _combo(body, t, "Category", L.list_categories(self.conn))
        self.manufacturer = _combo(body, t, "Manufacturer", L.list_manufacturers(self.conn))
        self.model = self._autocomplete_field(body, "Model name",
                                              L.autocomplete_model_names(self.conn))
        self.variant_var = tk.StringVar(value="A")
        self._auto_variant = True
        vrow = tk.Frame(body, bg=t["bg"]); vrow.pack(fill="x", pady=5)
        tk.Label(vrow, text="Variant", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        ve = tk.Entry(vrow, textvariable=self.variant_var, bg=t["panel"], fg=t["text"], relief="solid",
                      bd=1, insertbackground=t["text"])
        ve.pack(side="left", fill="x", expand=True)
        ve.bind("<KeyRelease>", lambda e: setattr(self, "_auto_variant", False), add="+")

        # auto-detect: surfaces existing variants that share this display name
        self.fam_frame = tk.Frame(self, bg=t["bg"])
        self.fam_frame.pack(fill="x", padx=20, pady=(0, 0))
        self.display.bind("<KeyRelease>", lambda e: self._check_variants(), add="+")
        self.display.bind("<<ComboboxSelected>>", lambda e: self._check_variants(), add="+")
        self.display.bind("<FocusOut>", lambda e: self._check_variants(), add="+")

        tk.Label(self, text="Attributes", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=20, pady=(10, 0))
        tk.Label(self, text="Name each attribute (e.g. RAM, Capacity) and give it a value.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        # BUG2: scrollable attribute area so many attributes don't make the dialog too tall
        host = tk.Frame(self, bg=t["bg"], height=210); host.pack(fill="both", expand=True, padx=20, pady=4)
        host.pack_propagate(False)
        acanvas = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        asb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=acanvas.yview)
        self.attr_box = tk.Frame(acanvas, bg=t["bg"])
        self.attr_box.bind("<Configure>", lambda e: acanvas.configure(scrollregion=acanvas.bbox("all")))
        awin = acanvas.create_window((0, 0), window=self.attr_box, anchor="nw")
        acanvas.bind("<Configure>", lambda e: acanvas.itemconfig(awin, width=e.width))
        acanvas.configure(yscrollcommand=asb.set)
        acanvas.pack(side="left", fill="both", expand=True); asb.pack(side="right", fill="y")
        self.attr_rows = []
        btnrow = tk.Frame(self, bg=t["bg"]); btnrow.pack(fill="x", padx=20, pady=2)
        tk.Button(btnrow, text="+ add attribute", command=lambda: self._add_attr_row(),
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="left")
        tk.Button(btnrow, text="\u2913 Use template", command=self._use_template,
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="left", padx=(8, 0))
        tk.Button(btnrow, text="\u270E New template", command=self._new_template,
                  relief="solid", bd=1, bg=t["panel"], fg=t["text"]).pack(side="left", padx=(4, 0))

        prefill_src = catid or clone_from
        if prefill_src:
            d = L.get_catalog_item(self.conn, prefill_src)
            self.display.set(d["item"]["display_name"])
            self.category.set(d["item"]["category"])
            self.manufacturer.set(d["item"]["manufacturer"] or "")
            self.model.set(d["item"]["model_name"] or "")
            if catid:
                self.variant_var.set(d["item"]["variant"] if "variant" in d["item"].keys() else "A")
            for n, v in d["attributes"]:
                self._add_attr_row(n, v)
            self._check_variants()
        else:
            self._add_attr_row()
        _btnrow(self, t, self._submit, "Save item")
        _modalize(self)

    def _check_variants(self):
        """When the typed name matches existing items, show them and (in add mode) nudge
        the variant field to the next free label so a new entry doesn't collide."""
        t = self.t
        for w in self.fam_frame.winfo_children():
            w.destroy()
        name = self.display.get().strip()
        fams = L.catalog_variants(self.conn, name, exclude_catid=self.catid) if name else []
        if not fams:
            self._known_family = False
            if not self.catid and getattr(self, "_auto_variant", False):
                self.variant_var.set("A")     # back to a clean lone-item default
            return
        if not getattr(self, "_known_family", False) and not self.catid:
            # first time we notice a family: advance the variant to the next free label
            self.variant_var.set(L.next_variant_label(self.conn, name, self.catid))
            self._auto_variant = True
        self._known_family = True
        tk.Label(self.fam_frame,
                 text=f"\u26A0 {len(fams)} variant(s) named \u201c{name}\u201d already exist \u2014 "
                      "pick one to view its specs:", bg=t["bg"], fg=t["accent"],
                 font=("Segoe UI", 9), wraplength=480, justify="left").pack(anchor="w")
        cb = ttk.Combobox(self.fam_frame, state="readonly", font=("Segoe UI", 9),
                          values=[f'{v["variant"]} \u2014 {v["spec_summary"]}' for v in fams])
        cb.pack(fill="x", pady=(2, 4))
        cb.bind("<<ComboboxSelected>>", lambda e: self._load_variant_preview(fams[cb.current()]))

    def _load_variant_preview(self, v):
        """Fill the form with an existing variant's specs so the user can compare; the
        variant label is moved to the next free one so saving makes a NEW variant."""
        self.category.set(v["category"] or "")
        self.manufacturer.set(v["manufacturer"] or "")
        self.model.set(v["model_name"] or "")
        for _, _, row in list(self.attr_rows):
            row.destroy()
        self.attr_rows.clear()
        for n, val in v["attributes"]:
            self._add_attr_row(n, val)
        if not self.attr_rows:
            self._add_attr_row()
        if not self.catid:
            self.variant_var.set(L.next_variant_label(self.conn, self.display.get(), self.catid))
            self._auto_variant = True

    def _autocomplete_field(self, parent, label, values, default=""):
        t = self.t
        row = tk.Frame(parent, bg=t["bg"]); row.pack(fill="x", pady=5)
        tk.Label(row, text=label, bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        cb = AutocompleteCombobox(row, font=("Segoe UI", 10))
        cb.set_completion_list(values)
        if default:
            cb.set(default)
        cb.pack(side="left", fill="x", expand=True)
        return cb

    def _add_attr_row(self, name="", value=""):
        t = self.t
        row = tk.Frame(self.attr_box, bg=t["bg"]); row.pack(fill="x", pady=2)
        name_cb = ttk.Combobox(row, values=L.list_attribute_names(self.conn), width=16,
                               font=("Segoe UI", 10))
        name_cb.set(name)
        name_cb.pack(side="left", padx=(0, 6))
        val_cb = AutocompleteCombobox(row, width=24, font=("Segoe UI", 10))
        val_cb.set_completion_list(L.attribute_value_suggestions(self.conn, name) if name else [])
        val_cb.set(value)
        val_cb.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def refresh_vals(*_):
            val_cb.set_completion_list(L.attribute_value_suggestions(self.conn, name_cb.get()))
        name_cb.bind("<<ComboboxSelected>>", refresh_vals)
        name_cb.bind("<FocusOut>", refresh_vals)

        def remove():
            row.destroy()
            self.attr_rows.remove((name_cb, val_cb, row))
        tk.Button(row, text="\u2715", command=remove, relief="flat", bg=t["bg"], fg=t["muted"],
                  font=("Segoe UI", 10), width=2, cursor="hand2").pack(side="left")
        self.attr_rows.append((name_cb, val_cb, row))

    def _load_template(self, attrs):
        """Replace the attribute rows with the template's attribute names (values left blank)."""
        for _, _, row in list(self.attr_rows):
            row.destroy()
        self.attr_rows.clear()
        for name in attrs:
            self._add_attr_row(name, "")
        if not self.attr_rows:
            self._add_attr_row()

    def _use_template(self):
        SelectTemplateDialog(self, self._load_template)

    def _new_template(self):
        # seed the designer with whatever attribute names are already typed in
        seed = [n.get().strip() for (n, _, _) in self.attr_rows if n.get().strip()]
        TemplateDesignerDialog(self, prefill=seed)

    def _submit(self):
        try:
            attrs = [(n.get(), v.get()) for (n, v, _) in self.attr_rows]
            if not messagebox.askyesno("Confirm", "Save this item?", parent=self):
                return
            if self.catid:
                L.update_catalog_item(self.conn, self.catid, self.category.get(), self.display.get(),
                                      self.manufacturer.get() or None, self.model.get() or None, attrs,
                                      variant=self.variant_var.get().strip() or None)
                new_id = self.catid
            else:
                new_id = L.add_catalog_item(self.conn, self.category.get(), self.display.get(),
                                            self.manufacturer.get() or None, self.model.get() or None, attrs,
                                            variant=self.variant_var.get().strip() or None)
            self.destroy()
            self.app.refresh()
            if self.on_saved:
                self.on_saved(new_id)
        except L.DuplicateCatalogItem as e:
            messagebox.showerror("Already in catalogue", str(e), parent=self)
        except Exception as e:  # noqa
            messagebox.showerror("Could not save item", str(e), parent=self)


class SelectTemplateDialog(tk.Toplevel):
    """Pick a saved attribute template to load into the catalogue dialog. Searchable,
    scrollable; supports adding a new template and removing existing ones."""
    def __init__(self, parent, on_pick):
        super().__init__(parent)
        self.parent, self.t, self.conn, self.on_pick = parent, parent.t, parent.conn, on_pick
        t = self.t
        self.configure(bg=t["bg"]); self.title("Use a template"); self.transient(parent)
        self.geometry("440x460")
        tk.Label(self, text="Load a template", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(self, text="Loads the attribute list (names only) so you just fill in values.",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=18)
        top = tk.Frame(self, bg=t["bg"]); top.pack(fill="x", padx=18, pady=(8, 4))
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._render())
        self.search = tk.Entry(top, textvariable=self.query, bg=t["panel"], fg=t["text"],
                               relief="solid", bd=1, insertbackground=t["text"], font=("Segoe UI", 10))
        self.search.pack(side="left", fill="x", expand=True)
        tk.Button(top, text="+ New", command=self._new, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"]).pack(side="left", padx=(6, 0))

        host = tk.Frame(self, bg=t["bg"]); host.pack(fill="both", expand=True, padx=18, pady=4)
        cv = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar", command=cv.yview)
        self.listf = tk.Frame(cv, bg=t["bg"])
        self.listf.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=self.listf, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self._cv = cv
        tk.Button(self, text="Close", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=18, pady=12)
        self._render()
        _modalize(self)
        self.after(80, lambda: (self.search.focus_force(), self.search.icursor("end")))   # cursor in search bar

    def _render(self):
        t = self.t
        for w in self.listf.winfo_children():
            w.destroy()
        q = self.query.get().strip().lower()
        items = sorted(L.list_catalog_templates(self.conn).items())
        shown = [(n, a) for n, a in items if not q or q in n.lower()
                 or any(q in x.lower() for x in a)]
        if not shown:
            tk.Label(self.listf, text="No templates yet — click + New to make one." if not items
                     else "No templates match your search.", bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI", 10), wraplength=360, justify="left").pack(anchor="w", pady=8)
            return
        for name, attrs in shown:
            card = tk.Frame(self.listf, bg=t["card"], highlightbackground=t["border"],
                            highlightthickness=1)
            card.pack(fill="x", pady=3, padx=1)
            head = tk.Frame(card, bg=t["card"]); head.pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(head, text=name, bg=t["card"], fg=t["text"],
                     font=("Segoe UI Semibold", 11)).pack(side="left")
            tk.Button(head, text="\u2715", command=lambda n=name: self._remove(n), relief="flat",
                      bg=t["card"], fg=t["muted"], font=("Segoe UI", 10), width=2,
                      cursor="hand2").pack(side="right")
            tk.Button(head, text="Use", command=lambda a=attrs: self._pick(a), relief="solid", bd=1,
                      bg=t["accent"], fg=t["on_accent"], font=("Segoe UI", 9)).pack(side="right", padx=4)
            tk.Label(card, text="  \u2022  ".join(attrs), bg=t["card"], fg=t["muted"],
                     font=("Segoe UI", 9), wraplength=380, justify="left", anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))

    def _pick(self, attrs):
        self.on_pick(list(attrs))
        self.destroy()

    def _remove(self, name):
        if messagebox.askyesno("Remove template", f"Delete the template '{name}'?", parent=self):
            L.delete_catalog_template(self.conn, name)
            self._render()

    def _new(self):
        TemplateDesignerDialog(self.parent, on_saved=self._render)


class TemplateDesignerDialog(tk.Toplevel):
    """Design a custom attribute template: a name plus an ordered list of attribute
    names chosen from the stored vocabulary (or typed in). Reorder and remove freely."""
    def __init__(self, parent, prefill=None, on_saved=None):
        super().__init__(parent)
        self.parent, self.t, self.conn, self.on_saved = parent, parent.t, parent.conn, on_saved
        t = self.t
        self.items = list(prefill or [])
        self.configure(bg=t["bg"]); self.title("New template"); self.transient(parent)
        self.geometry("440x520")
        tk.Label(self, text="Design a template", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(self, text="Pick the attributes to pre-fill and set their order. Values aren't "
                 "stored — only the list.", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9),
                 wraplength=400, justify="left").pack(anchor="w", padx=18)

        nrow = tk.Frame(self, bg=t["bg"]); nrow.pack(fill="x", padx=18, pady=(10, 4))
        tk.Label(nrow, text="Template name", bg=t["bg"], fg=t["muted"], width=14,
                 anchor="w").pack(side="left")
        self.name = tk.StringVar()
        tk.Entry(nrow, textvariable=self.name, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"], font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)

        arow = tk.Frame(self, bg=t["bg"]); arow.pack(fill="x", padx=18, pady=(4, 4))
        tk.Label(arow, text="Add attribute", bg=t["bg"], fg=t["muted"], width=14,
                 anchor="w").pack(side="left")
        self.picker = ttk.Combobox(arow, values=L.list_attribute_names(self.conn), font=("Segoe UI", 10))
        self.picker.pack(side="left", fill="x", expand=True)
        self.picker.bind("<Return>", lambda e: self._add())
        tk.Button(arow, text="Add", command=self._add, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"]).pack(side="left", padx=(6, 0))

        host = tk.Frame(self, bg=t["bg"]); host.pack(fill="both", expand=True, padx=18, pady=4)
        cv = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar", command=cv.yview)
        self.listf = tk.Frame(cv, bg=t["bg"])
        self.listf.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=self.listf, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        _btnrow(self, t, self._save, "Save template")
        self._render()
        _modalize(self)
        self.after(80, self.picker.focus_force)

    def _add(self):
        v = self.picker.get().strip()
        if v and v.lower() not in [x.lower() for x in self.items]:
            self.items.append(v)
        self.picker.set("")
        self._render()

    def _move(self, i, delta):
        j = i + delta
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self._render()

    def _remove(self, i):
        del self.items[i]
        self._render()

    def _render(self):
        t = self.t
        for w in self.listf.winfo_children():
            w.destroy()
        if not self.items:
            tk.Label(self.listf, text="No attributes added yet.", bg=t["bg"], fg=t["muted"],
                     font=("Segoe UI", 10)).pack(anchor="w", pady=6)
            return
        for i, name in enumerate(self.items):
            row = tk.Frame(self.listf, bg=t["card"], highlightbackground=t["border"],
                           highlightthickness=1)
            row.pack(fill="x", pady=2, padx=1)
            tk.Label(row, text=f"{i + 1}.", bg=t["card"], fg=t["muted"], width=3,
                     font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))
            tk.Label(row, text=name, bg=t["card"], fg=t["text"], font=("Segoe UI", 10),
                     anchor="w").pack(side="left", fill="x", expand=True, pady=6)
            tk.Button(row, text="\u2715", command=lambda i=i: self._remove(i), relief="flat",
                      bg=t["card"], fg=t["muted"], width=2, cursor="hand2").pack(side="right", padx=(0, 6))
            tk.Button(row, text="\u2193", command=lambda i=i: self._move(i, 1), relief="flat",
                      bg=t["card"], fg=t["text"], width=2, cursor="hand2").pack(side="right")
            tk.Button(row, text="\u2191", command=lambda i=i: self._move(i, -1), relief="flat",
                      bg=t["card"], fg=t["text"], width=2, cursor="hand2").pack(side="right")

    def _save(self):
        try:
            L.save_catalog_template(self.conn, self.name.get(), self.items)
            self.destroy()
            if self.on_saved:
                self.on_saved()
        except Exception as e:  # noqa
            messagebox.showerror("Could not save template", str(e), parent=self)


class VocabularyDialog(tk.Toplevel):
    """Manage the three editable vocabularies: categories, manufacturers, attribute names."""
    def __init__(self, app):
        super().__init__(app)
        self.app, self.t, self.conn = app, app.t, app.conn
        t = self.t
        self.configure(bg=t["bg"])
        self.title("Manage Vocabulary")
        self.transient(app)
        self.geometry("640x420")
        tk.Label(self, text="Manage Vocabulary", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 8))
        cols = tk.Frame(self, bg=t["bg"]); cols.pack(fill="both", expand=True, padx=14, pady=6)
        self._column(cols, "Categories", "category", L.list_categories, L.add_category)
        self._column(cols, "Manufacturers", "manufacturer", L.list_manufacturers, L.add_manufacturer)
        self._column(cols, "Attribute names", "attribute", L.list_attribute_names, L.add_attribute_name)
        tk.Button(self, text="Close", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=20, pady=10)
        _modalize(self)

    def _column(self, parent, title, kind, lister, adder):
        t = self.t
        frame = tk.Frame(parent, bg=t["bg"]); frame.pack(side="left", fill="both", expand=True, padx=8)
        tk.Label(frame, text=title, bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        lb = tk.Listbox(frame, bg=t["panel"], fg=t["text"], relief="solid", bd=1, height=10,
                        selectbackground=t["accent"], selectforeground=t["on_accent"],
                        highlightthickness=0, font=("Segoe UI", 10))
        lb.pack(fill="both", expand=True, pady=4)

        def reload():
            lb.delete(0, "end")
            for v in lister(self.conn):
                lb.insert("end", v)
        reload()
        entry = tk.Entry(frame, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                         insertbackground=t["text"], font=("Segoe UI", 10))
        entry.pack(fill="x", pady=2)
        btns = tk.Frame(frame, bg=t["bg"]); btns.pack(fill="x")

        def add():
            if entry.get().strip():
                adder(self.conn, entry.get().strip())
                entry.delete(0, "end")
                reload()
                self.app.refresh()

        def remove():
            if not lb.curselection():
                return
            name = lb.get(lb.curselection()[0])
            try:
                L.delete_vocab(self.conn, kind, name)
                reload()
                self.app.refresh()
            except Exception as e:  # noqa
                messagebox.showerror("Can't remove", str(e), parent=self)
        tk.Button(btns, text="Add", command=add, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=6).pack(side="left", padx=(0, 4), pady=2)
        tk.Button(btns, text="Remove", command=remove, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=8).pack(side="left", pady=2)


class CatalogPickerDialog(tk.Toplevel):
    """Search the catalogue and pick item(s), or create a new one. Calls on_pick(catid)
    for each chosen item. Multiple rows can be selected at once (M5)."""
    def __init__(self, app, on_pick):
        super().__init__(app)
        self.app, self.t, self.conn, self.on_pick = app, app.t, app.conn, on_pick
        t = self.t
        self.configure(bg=t["bg"])
        self.title("Pick from catalogue")
        self.transient(app)
        self.geometry("660x520")
        tk.Label(self, text="Pick item(s) from the catalogue", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="Tip: Ctrl/Shift-click to select several at once.", bg=t["bg"],
                 fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        bar = tk.Frame(self, bg=t["bg"]); bar.pack(fill="x", padx=20, pady=(6, 0))
        tk.Label(bar, text="Search:", bg=t["bg"], fg=t["muted"]).pack(side="left")
        self.q = tk.StringVar()
        ent = tk.Entry(bar, textvariable=self.q, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                       insertbackground=t["text"], font=("Segoe UI", 10))
        ent.pack(side="left", fill="x", expand=True, padx=6, ipady=2)
        self.q.trace_add("write", lambda *_: self._search())
        wrap = tk.Frame(self, bg=t["bg"]); wrap.pack(fill="both", expand=True, padx=20, pady=8)
        self.tree = ttk.Treeview(wrap, columns=("name", "cat", "attrs"), show="headings", height=12,
                                 selectmode="extended")
        for c, txt, w in [("name", "Display name", 200), ("cat", "Category", 90), ("attrs", "Attributes", 260)]:
            self.tree.heading(c, text=txt); self.tree.column(c, width=w)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", style="Lyware.Vertical.TScrollbar",
                           command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._use())
        btns = tk.Frame(self, bg=t["bg"]); btns.pack(fill="x", padx=20, pady=(0, 14))
        tk.Button(btns, text="Cancel", command=self.destroy, relief="solid", bd=1, bg=t["panel"],
                  fg=t["text"], width=10).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Add selected", command=self._use, relief="solid", bd=1, bg=t["accent"],
                  fg=t["on_accent"], width=12).pack(side="right")
        tk.Button(btns, text="Create new item\u2026", command=self._create, relief="solid", bd=1,
                  bg=t["panel"], fg=t["text"]).pack(side="left")
        self._search()
        _modalize(self)

    def _search(self):
        self.tree.delete(*self.tree.get_children())
        for r in L.search_catalog(self.conn, self.q.get() or None):
            attrs = self.conn.execute("SELECT attr_name, attr_value FROM catalog_attributes "
                                      "WHERE catid=? ORDER BY sort_order", (r["catid"],)).fetchall()
            summary = ", ".join(f'{a["attr_name"]}: {a["attr_value"]}' for a in attrs)
            self.tree.insert("", "end", iid=str(r["catid"]),
                             values=(r["display_name"], r["category"], summary))

    def _use(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Pick one", "Select at least one catalogue item first.", parent=self)
            return
        ids = [int(s) for s in sel]
        self.destroy()
        for catid in ids:                                # M5: add every selected item
            self.on_pick(catid)

    def _create(self):
        def after(new_id):
            self.destroy()
            self.on_pick(new_id)
        CatalogItemDialog(self.app, on_saved=after)


class ListingDialog(tk.Toplevel):
    """Create a listing composed of catalogue items (search/pick/create) with per-product
    quantity and a per-item listing price (M1). Phone on every platform; link only for
    online platforms (BUG4). The item list scrolls so long listings stay visible (BUG1)."""
    def __init__(self, app, platform=None, edit_lsid=None):
        super().__init__(app)
        self.edit_lsid = edit_lsid
        if edit_lsid:
            _al = app.conn.execute("SELECT * FROM all_listings WHERE lsid=?", (edit_lsid,)).fetchone()
            platform = _al["platform"]
        self.app, self.t, self.fixed = app, app.t, platform
        self.conn = app.conn
        t = self.t
        self.configure(bg=t["bg"])
        self.title("Edit Listing" if edit_lsid else "Add Listing")
        self.transient(app)
        self.geometry("580x640")
        tk.Label(self, text="Edit Listing" if edit_lsid else "Add Listing", bg=t["bg"], fg=t["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=20, pady=(16, 4))

        self.platform = tk.StringVar(value=platform or "eBay")
        prow = tk.Frame(self, bg=t["bg"]); prow.pack(fill="x", padx=20, pady=4)
        tk.Label(prow, text="Platform", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        if platform:
            tk.Label(prow, text=platform, bg=t["bg"], fg=t["text"],
                     font=("Segoe UI Semibold", 10)).pack(side="left")
        else:
            ttk.OptionMenu(prow, self.platform, self.platform.get(), "eBay", "Amazon", "Facebook",
                           "In-Person", command=lambda *_: self._rebuild_ref()).pack(side="left")

        body = tk.Frame(self, bg=t["bg"]); body.pack(fill="x", padx=20)
        self.ref_holder = tk.Frame(body, bg=t["bg"]); self.ref_holder.pack(fill="x")
        self.ref = tk.StringVar()
        self.seller = tk.StringVar(); self.price = tk.StringVar()
        self.currency = tk.StringVar(value="USD")
        self.link = tk.StringVar(); self.phone = tk.StringVar(); self.date = tk.StringVar(value=_today())
        self.listing_name = tk.StringVar(); self.seller_link = tk.StringVar()
        self._rebuild_ref()
        _field(body, t, "Listing name", self.listing_name)
        _field(body, t, "Seller", self.seller)
        _field(body, t, "Seller link", self.seller_link)
        prow2 = tk.Frame(body, bg=t["bg"]); prow2.pack(fill="x", pady=5)
        tk.Label(prow2, text="Total value", bg=t["bg"], fg=t["muted"], width=18, anchor="w").pack(side="left")
        self.total_lbl = tk.Label(prow2, text="0.00", bg=t["bg"], fg=t["text"],
                                  font=("Segoe UI Semibold", 11))     # M4: computed, not typed
        self.total_lbl.pack(side="left")
        ttk.OptionMenu(prow2, self.currency, self.currency.get(), "USD", "LYD").pack(side="left", padx=10)
        tk.Label(prow2, text="(sum of item prices \u00D7 qty)", bg=t["bg"], fg=t["muted"],
                 font=("Segoe UI", 8)).pack(side="left")
        self.link_holder = tk.Frame(body, bg=t["bg"]); self.link_holder.pack(fill="x")
        _field(body, t, "Phone number", self.phone)
        _field(body, t, "Date", self.date)
        self._rebuild_link()

        tk.Label(self, text="Items in this listing — set each item's listing price (M1)",
                 bg=t["bg"], fg=t["muted"], font=("Segoe UI Semibold", 10)).pack(
            anchor="w", padx=20, pady=(10, 0))
        # BUG1: scrollable item area so many items remain visible
        host = tk.Frame(self, bg=t["bg"], height=170); host.pack(fill="both", expand=True, padx=20)
        host.pack_propagate(False)
        canvas = tk.Canvas(host, bg=t["bg"], highlightthickness=0)
        isb = ttk.Scrollbar(host, orient="vertical", style="Lyware.Vertical.TScrollbar",
                            command=canvas.yview)
        self.items_box = tk.Frame(canvas, bg=t["bg"])
        self.items_box.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        iwin = canvas.create_window((0, 0), window=self.items_box, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(iwin, width=e.width))
        canvas.configure(yscrollcommand=isb.set)
        canvas.pack(side="left", fill="both", expand=True); isb.pack(side="right", fill="y")
        self.lines = []
        tk.Button(self, text="+ add item from catalogue", command=self._pick_item, relief="solid",
                  bd=1, bg=t["panel"], fg=t["text"]).pack(anchor="w", padx=20, pady=2)
        _btnrow(self, t, self._submit, "Save listing" if edit_lsid else "Create listing")
        if edit_lsid:
            self._prefill(edit_lsid)
        _modalize(self)

    def _prefill(self, lsid):
        al = self.conn.execute("SELECT * FROM all_listings WHERE lsid=?", (lsid,)).fetchone()
        self.seller.set(al["seller_name"] or "")
        self.currency.set(al["currency"] or "USD")
        self.link.set(al["link"] or "")
        self.phone.set(al["phone_number"] or "")
        self.date.set(al["date_of_listing"] or "")
        self.listing_name.set(al["listing_name"] or "")
        self.seller_link.set(al["seller_link"] or "")
        ref = self.conn.execute(
            "SELECT ebay_item_number AS r FROM ebay_listings WHERE lsid=? UNION ALL "
            "SELECT asin AS r FROM amazon_listings WHERE lsid=?", (lsid, lsid)).fetchone()
        if ref:
            self.ref.set(ref["r"] or "")
        for r in self.conn.execute("SELECT catid, quantity, unit_price FROM listing_items WHERE lsid=?",
                                   (lsid,)):
            self._add_line(r["catid"])
            catid, qty, price, _ = self.lines[-1]
            qty.set(str(r["quantity"]))
            price.set("" if r["unit_price"] is None else str(D(r["unit_price"])))
        self._recalc()

    def _rebuild_ref(self):
        for w in self.ref_holder.winfo_children():
            w.destroy()
        p = self.fixed or self.platform.get()
        label = {"eBay": "eBay item number", "Amazon": "ASIN"}.get(p)
        if label:
            _field(self.ref_holder, self.t, label, self.ref)
        if hasattr(self, "link_holder"):
            self._rebuild_link()

    def _rebuild_link(self):
        for w in self.link_holder.winfo_children():
            w.destroy()
        p = self.fixed or self.platform.get()
        if p != "In-Person":                       # BUG4: no link field for in-person listings
            _field(self.link_holder, self.t, "Link", self.link)

    def _pick_item(self):
        CatalogPickerDialog(self.app, on_pick=self._add_line)

    def _recalc(self):
        total = 0.0
        for catid, qty, price, _ in self.lines:
            try:
                total += float(qty.get()) * float(price.get() or 0)
            except ValueError:
                pass
        self._total = total
        self.total_lbl.configure(text=D(total))

    def _add_line(self, catid):
        if any(c == catid for c, _, _, _ in self.lines):
            messagebox.showinfo("Already added", "That item is already in the listing; adjust its "
                                "quantity instead.", parent=self)
            return
        t = self.t
        row = tk.Frame(self.items_box, bg=t["bg"]); row.pack(fill="x", pady=2)
        tk.Label(row, text=L.catalog_label(self.conn, catid)[:34], bg=t["bg"], fg=t["text"],
                 anchor="w", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
        qty = tk.StringVar(value="1"); price = tk.StringVar()
        qty.trace_add("write", lambda *_: self._recalc()); price.trace_add("write", lambda *_: self._recalc())
        tk.Label(row, text="qty", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=qty, width=4, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", padx=3)
        tk.Label(row, text="price", bg=t["bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=price, width=8, bg=t["panel"], fg=t["text"], relief="solid", bd=1,
                 insertbackground=t["text"]).pack(side="left", padx=3)

        def remove():
            row.destroy()
            self.lines[:] = [ln for ln in self.lines if ln[3] is not row]
            self._recalc()
        tk.Button(row, text="\u2715", command=remove, relief="flat", bg=t["bg"], fg=t["muted"],
                  width=2, cursor="hand2").pack(side="left")
        self.lines.append((catid, qty, price, row))
        self._recalc()

    def _submit(self):
        try:
            if not self.lines:
                raise ValueError("Add at least one item from the catalogue.")
            items = []
            for catid, qty, price, _ in self.lines:
                q = int(qty.get())
                if q < 1:
                    raise ValueError("Quantities must be at least 1.")
                up = _num(price.get(), "Item price") if price.get().strip() else None
                items.append((catid, q, up))
            if not messagebox.askyesno("Confirm", "Save this listing?", parent=self):
                return
            p = self.fixed or self.platform.get()
            total_qty = sum(it[1] for it in items)
            total_val = getattr(self, "_total", 0) or None       # M4: computed total
            if self.edit_lsid:
                self.app._snapshot("edit-listing")
                L.edit_listing(self.conn, self.edit_lsid,
                               link=(self.link.get().strip() or None) if p != "In-Person" else None,
                               price=total_val, currency=self.currency.get(),
                               seller_name=self.seller.get().strip() or None,
                               date_of_listing=self.date.get().strip() or None,
                               reference=self.ref.get().strip() or None,
                               phone_number=self.phone.get().strip() or None, qty_items=total_qty,
                               listing_name=self.listing_name.get().strip() or None,
                               seller_link=self.seller_link.get().strip() or None)
                L.set_listing_items(self.conn, self.edit_lsid, items)
                self.destroy(); self.app.refresh()
                return
            lsid = L.add_listing(self.conn, p,
                                 link=(self.link.get().strip() or None) if p != "In-Person" else None,
                                 price=total_val, currency=self.currency.get(),
                                 qty_items=total_qty, seller_name=self.seller.get().strip() or None,
                                 date_of_listing=self.date.get().strip() or None,
                                 reference=self.ref.get().strip() or None,
                                 phone_number=self.phone.get().strip() or None,
                                 listing_name=self.listing_name.get().strip() or None,
                                 seller_link=self.seller_link.get().strip() or None)
            L.add_listing_items(self.conn, lsid, items)
            self.destroy(); self.app.refresh()
        except Exception as e:  # noqa
            messagebox.showerror("Could not add listing", str(e), parent=self)


if __name__ == "__main__":
    App().mainloop()
