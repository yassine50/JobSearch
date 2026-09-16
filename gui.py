#!/usr/bin/env python3
"""
Job Search — A modern, professional desktop application for finding jobs.
"""
import csv
import os
import re
import threading
import tkinter as tk
import webbrowser
import urllib.parse
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime
import pandas as pd


# ─── Color Palette ─────────────────────────────────────────────────────────────
C = {
    "bg":           "#DBEAFE",   # Page background (light blue)
    "card":         "#FFFFFF",   # Card / panel background
    "card_hdr":     "#EFF6FF",   # Card title bar background (very light blue)
    "primary":      "#1A56DB",   # Blue accent
    "primary_dark": "#1740B0",
    "primary_light":"#BFDBFE",
    "success":      "#0B7A4E",
    "warning":      "#92400E",
    "error":        "#B91C1C",
    "text":         "#000000",   # Pure black for maximum contrast
    "text_sub":     "#111827",   # Near black for labels
    "text_muted":   "#374151",   # Dark gray for hints (not too light)
    "border":       "#93C5FD",   # Blue-tinted border
    "entry_bg":     "#FFFFFF",   # Pure white for inputs
    "row_odd":      "#F3F8FF",   # Very subtle blue for alternating rows
    "row_even":     "#FFFFFF",
    "hover":        "#BFDBFE",
}

FONT_BODY   = ("Helvetica", 12)
FONT_LABEL  = ("Helvetica", 11, "bold")
FONT_HINT   = ("Helvetica", 10)
FONT_TITLE  = ("Helvetica", 13, "bold")
FONT_HEADER = ("Helvetica", 23, "bold")
FONT_BTN    = ("Helvetica", 14, "bold")
FONT_BTN2   = ("Helvetica", 13, "bold")
FONT_BTN_SM = ("Helvetica", 11, "bold")


class JobSearchApp:
    SITES = [
        ("LinkedIn", "linkedin"),
        ("Indeed",   "indeed"),
    ]
    HOURS_OLD_OPTIONS = {
        "Any time":      None,
        "Last 24 hours": 24,
        "Last 3 days":   72,
        "Last week":     168,
        "Last month":    720,
    }
    JOB_TYPE_OPTIONS = {
        "Any":        None,
        "Full-time":  "fulltime",
        "Part-time":  "parttime",
        "Contract":   "contract",
        "Internship": "internship",
    }
    COUNTRIES = [
        "USA", "UK", "Canada", "Australia", "Germany", "France", "India",
        "Singapore", "United Arab Emirates", "Saudi Arabia", "Netherlands",
        "Spain", "Italy", "Brazil", "Mexico", "Japan", "South Korea",
        "South Africa", "Qatar", "Kuwait", "Egypt", "Pakistan", "Nigeria",
        "Philippines", "Malaysia", "Indonesia", "Ireland", "Sweden",
        "Switzerland", "Belgium", "Poland", "Turkey", "Israel", "New Zealand",
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Job Searcher — Developed by Yassine Youssef")
        self.root.geometry("1280x860")
        self.root.minsize(1000, 700)
        self.root.configure(bg=C["bg"])

        self.site_vars: dict = {}
        self.is_searching = False
        self.current_jobs_df = None
        self.custom_sites: list = []
        self._cv_text: str = ""
        self._match_breakdowns: dict = {}   # item_id -> breakdown dict

        self._setup_styles()
        self._build_header()
        self._build_body()

        self.root.after(200, self._toggle_country_cb)
        if "indeed" in self.site_vars:
            self.site_vars["indeed"].trace_add("write", self._toggle_country_cb)

    # ── Styles ──────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self.root)
        for t in ("clam", "default"):
            if t in s.theme_names():
                s.theme_use(t)
                break

        s.configure(".", font=FONT_BODY, background=C["bg"])
        s.configure("TFrame", background=C["bg"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])

        # Checkbutton — bigger, clearer
        s.configure("TCheckbutton",
                    background=C["card"],
                    foreground=C["text"],
                    font=FONT_BODY)

        # Spinbox / Combobox
        s.configure("TSpinbox",
                    fieldbackground=C["entry_bg"],
                    foreground=C["text"],
                    font=FONT_BODY,
                    borderwidth=1,
                    relief="solid")
        s.configure("TCombobox",
                    fieldbackground=C["entry_bg"],
                    foreground=C["text"],
                    font=FONT_BODY,
                    borderwidth=1,
                    relief="solid",
                    padding=4)
        s.map("TCombobox",
              fieldbackground=[("readonly", C["entry_bg"])],
              foreground=[("disabled", C["text_muted"])])

        # Treeview — clear, readable
        s.configure("Treeview",
                    font=FONT_BODY,
                    rowheight=34,
                    fieldbackground="white",
                    background="white",
                    foreground=C["text"],
                    borderwidth=0,
                    relief="flat")
        s.configure("Treeview.Heading",
                    font=FONT_LABEL,
                    background=C["primary_light"],
                    foreground=C["primary"],
                    borderwidth=0,
                    relief="flat",
                    padding=(10, 8))
        s.map("Treeview",
              background=[("selected", C["hover"])],
              foreground=[("selected", C["text"])])

        # Progressbar
        s.configure("TProgressbar",
                    troughcolor=C["border"],
                    background=C["primary"])

        # Buttons (macOS tk.Button ignores bg, so we use ttk.Button + clam theme)
        s.configure("Search.TButton", font=FONT_BTN, background=C["primary"], foreground="white", padding=(10, 8))
        s.map("Search.TButton", background=[("active", C["primary_dark"]), ("disabled", C["primary_light"])])

        s.configure("Export.TButton", font=FONT_BTN2, background="#DC2626", foreground="white", padding=(10, 8))
        s.map("Export.TButton", background=[("active", "#B91C1C"), ("disabled", "#FECACA")])

        s.configure("Add.TButton", font=FONT_BTN_SM, background=C["primary"], foreground="white", padding=(8, 6))
        s.map("Add.TButton", background=[("active", C["primary_dark"])])

        s.configure("Remove.TButton", font=FONT_BTN_SM, background="#DC2626", foreground="white", padding=(8, 6))
        s.map("Remove.TButton", background=[("active", "#B91C1C")])

    # ── Header ──────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=C["primary"])
        hdr.pack(fill=tk.X)
        inner = tk.Frame(hdr, bg=C["primary"])
        inner.pack(fill=tk.X, padx=24, pady=16)

        tk.Label(inner, text="🔍  Job Search",
                 font=FONT_HEADER, bg=C["primary"], fg="white").pack(side=tk.LEFT)
        tk.Label(inner, text="   Find your next opportunity across LinkedIn & Indeed",
                 font=("Helvetica", 12), bg=C["primary"], fg="#BFDBFE").pack(side=tk.LEFT, pady=6)

    # ── Body ────────────────────────────────────────────────────────────────────

    def _build_body(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(16, 0))

        # ── 1. Job Seeker Tab ──
        self.seeker_tab = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(self.seeker_tab, text=" 👤 Job Seeker Mode ")
        self._build_seeker_tab(self.seeker_tab)

        # ── 2. Recruiter Tab ──
        self.recruiter_tab = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(self.recruiter_tab, text=" 👔 Recruiter Mode ")
        self._build_recruiter_tab(self.recruiter_tab)

        # Build watermark at the absolute bottom
        self._build_watermark(self.root)

    def _build_seeker_tab(self, parent):
        body = tk.Frame(parent, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Top row: three cards side by side
        top = tk.Frame(body, bg=C["bg"])
        top.pack(fill=tk.X, pady=(0, 12))

        self._build_search_card(top)
        self._build_sites_card(top)
        self._build_custom_card(top)

        self._build_action_bar(body)
        self._build_status_strip(body)
        
        self._build_results_panel(body)

    def _build_recruiter_tab(self, parent):
        body = tk.Frame(parent, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        top = tk.Frame(body, bg=C["bg"])
        top.pack(fill=tk.X, pady=(0, 12))

        jd_card = self._card(top, "📝 Target Job Profile", side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Row 1: title, location, results count
        row1 = tk.Frame(jd_card, bg=C["card"])
        row1.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row1, text="Job Title:", font=FONT_LABEL, bg=C["card"]).pack(side=tk.LEFT)
        self.rec_title_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.rec_title_var, font=FONT_BODY,
                 bg=C["entry_bg"], width=24).pack(side=tk.LEFT, padx=(5, 18))

        tk.Label(row1, text="Location:", font=FONT_LABEL, bg=C["card"]).pack(side=tk.LEFT)
        self.rec_loc_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.rec_loc_var, font=FONT_BODY,
                 bg=C["entry_bg"], width=22).pack(side=tk.LEFT, padx=(5, 18))

        tk.Label(row1, text="Results:", font=FONT_LABEL, bg=C["card"]).pack(side=tk.LEFT)
        self.rec_results_var = tk.IntVar(value=30)
        ttk.Spinbox(row1, from_=5, to=100, increment=5,
                    textvariable=self.rec_results_var, width=5).pack(side=tk.LEFT, padx=(5, 0))

        # Row 2: optional keywords to inject into query
        row2 = tk.Frame(jd_card, bg=C["card"])
        row2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(row2, text="Required Skills (comma-sep, injected into search):",
                 font=FONT_LABEL, bg=C["card"]).pack(side=tk.LEFT)
        self.rec_skills_var = tk.StringVar()
        tk.Entry(row2, textvariable=self.rec_skills_var, font=FONT_BODY,
                 bg=C["entry_bg"], width=50).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(jd_card, text="Job Description (paste full text — used for AI matching):",
                 font=FONT_LABEL, bg=C["card"]).pack(anchor=tk.W, pady=(4, 4))
        self.rec_jd_text = tk.Text(jd_card, height=6, font=("Helvetica", 11), bg=C["entry_bg"])
        self.rec_jd_text.pack(fill=tk.BOTH, expand=True)

        # Action bar
        act_bar = tk.Frame(body, bg=C["bg"])
        act_bar.pack(fill=tk.X, pady=(0, 8))

        self.rec_search_btn = ttk.Button(act_bar, text="🔍   Search Candidates",
                                     style="Search.TButton",
                                     cursor="hand2",
                                     command=self._on_recruiter_search)
        self.rec_search_btn.pack(side=tk.LEFT, padx=(0, 14))

        self.rec_status_label = tk.Label(act_bar, text="Ready — enter a job title & description, then search.",
                                         font=("Helvetica", 11), bg=C["bg"], fg=C["text_muted"])
        self.rec_status_label.pack(side=tk.LEFT, padx=10)

        self.rec_progress = ttk.Progressbar(act_bar, mode="indeterminate", length=200)
        self.rec_progress.pack(side=tk.LEFT, padx=10)

        # Results panel
        res_card = self._card(body, "📋 Top Candidate Matches", side=tk.TOP, fill=tk.BOTH, expand=True)
        
        tbl = tk.Frame(res_card, bg=C["card"])
        tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        columns = ("match_score", "name", "headline", "body", "url")
        self.rec_tree = ttk.Treeview(tbl, columns=columns, show="headings", selectmode="browse")

        col_cfg = {
            "match_score": ("🎯 Match %", 90),
            "name": ("Candidate Name", 160),
            "headline": ("Headline", 220),
            "body": ("Profile Snippet", 450),
            "url": ("LinkedIn URL", 200),
        }
        for col, (heading, width) in col_cfg.items():
            self.rec_tree.heading(col, text=heading)
            self.rec_tree.column(col, width=width, minwidth=60)

        vsb = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.rec_tree.yview)
        hsb = ttk.Scrollbar(tbl, orient=tk.HORIZONTAL, command=self.rec_tree.xview)
        self.rec_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.rec_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tbl.grid_rowconfigure(0, weight=1)
        tbl.grid_columnconfigure(0, weight=1)

        self.rec_tree.tag_configure("odd",        background=C["row_odd"])
        self.rec_tree.tag_configure("even",       background=C["row_even"])
        self.rec_tree.tag_configure("match_high", background="#D1FAE5", foreground="#065F46")
        self.rec_tree.tag_configure("match_mid",  background="#FEF3C7", foreground="#92400E")
        self.rec_tree.tag_configure("match_low",  background="#FEE2E2", foreground="#991B1B")

        self.rec_tree.bind("<ButtonRelease-1>", self._on_rec_tree_click)
        self.rec_tree.bind("<Motion>", self._on_rec_tree_motion)

    # ── Card factory ────────────────────────────────────────────────────────────

    def _card(self, parent, title: str, **pack_kw) -> tk.Frame:
        """White rounded card with a colored title bar."""
        outer = tk.Frame(parent, bg=C["card"],
                         highlightbackground=C["border"],
                         highlightthickness=1)
        outer.pack(**pack_kw)

        if title:
            title_bar = tk.Frame(outer, bg=C["card_hdr"])
            title_bar.pack(fill=tk.X)
            tk.Label(title_bar, text=title, font=FONT_TITLE,
                     bg=C["card_hdr"], fg=C["primary"],
                     padx=16, pady=10).pack(anchor=tk.W)
            tk.Frame(outer, bg=C["border"], height=1).pack(fill=tk.X)

        body = tk.Frame(outer, bg=C["card"], padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)
        return body

    # ── Field label helpers ─────────────────────────────────────────────────────

    def _field_label(self, parent, text: str, pady=(0, 4)):
        """Bold dark label above an input field."""
        tk.Label(parent, text=text, font=FONT_LABEL,
                 bg=C["card"], fg=C["text_sub"]).pack(anchor=tk.W, pady=pady)

    def _inline_label(self, parent, text: str):
        """Label rendered inline (for same-row field groups)."""
        tk.Label(parent, text=text, font=FONT_LABEL,
                 bg=C["card"], fg=C["text_sub"]).pack(side=tk.LEFT, padx=(0, 5))

    def _entry(self, parent, var, **kw) -> tk.Entry:
        e = tk.Entry(parent, textvariable=var, font=FONT_BODY,
                     bg=C["entry_bg"], fg=C["text"],
                     relief="solid", bd=1,
                     highlightthickness=2,
                     highlightcolor=C["primary"],
                     highlightbackground=C["border"],
                     insertbackground=C["primary"],
                     **kw)
        e.pack(fill=tk.X, pady=(0, 12))
        return e

    # ── Search Parameters Card ──────────────────────────────────────────────────

    def _build_search_card(self, parent):
        body = self._card(parent, "🔎  Search Parameters",
                          side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # ── Keywords & Location side by side ──
        kw_loc = tk.Frame(body, bg=C["card"])
        kw_loc.pack(fill=tk.X)
        kw_loc.columnconfigure(0, weight=1)
        kw_loc.columnconfigure(1, weight=1)

        kw_frame = tk.Frame(kw_loc, bg=C["card"])
        kw_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._field_label(kw_frame, "Keywords")
        self.search_term_var = tk.StringVar(value="software engineer")
        self._entry(kw_frame, self.search_term_var)

        loc_frame = tk.Frame(kw_loc, bg=C["card"])
        loc_frame.grid(row=0, column=1, sticky="ew")
        self._field_label(loc_frame, "Location")
        self.location_var = tk.StringVar(value="San Francisco, CA")
        self._entry(loc_frame, self.location_var)

        # ── Row 2: Results · Posted Within · Job Type ──
        sep1 = tk.Frame(body, bg=C["card"])
        sep1.pack(fill=tk.X, pady=(0, 10))

        def inline_group(frm, label, widget_fn):
            grp = tk.Frame(frm, bg=C["card"])
            grp.pack(side=tk.LEFT, padx=(0, 24))
            tk.Label(grp, text=label, font=FONT_LABEL,
                     bg=C["card"], fg=C["text_sub"]).pack(anchor=tk.W, pady=(0, 3))
            widget_fn(grp)

        self.results_var = tk.IntVar(value=10)
        inline_group(sep1, "Results",
                     lambda p: ttk.Spinbox(p, from_=1, to=200, textvariable=self.results_var,
                                           width=6).pack(anchor=tk.W))

        self.hours_old_var = tk.StringVar(value="Any time")
        inline_group(sep1, "Posted Within",
                     lambda p: ttk.Combobox(p, textvariable=self.hours_old_var,
                                            values=list(self.HOURS_OLD_OPTIONS.keys()),
                                            state="readonly", width=14).pack(anchor=tk.W))

        self.job_type_var = tk.StringVar(value="Any")
        inline_group(sep1, "Job Type",
                     lambda p: ttk.Combobox(p, textvariable=self.job_type_var,
                                            values=list(self.JOB_TYPE_OPTIONS.keys()),
                                            state="readonly", width=12).pack(anchor=tk.W))

        # ── Row 3: Country · Checkboxes ──
        sep2 = tk.Frame(body, bg=C["card"])
        sep2.pack(fill=tk.X)

        country_grp = tk.Frame(sep2, bg=C["card"])
        country_grp.pack(side=tk.LEFT, padx=(0, 24))
        tk.Label(country_grp, text="Country (Indeed)", font=FONT_LABEL,
                 bg=C["card"], fg=C["text_sub"]).pack(anchor=tk.W, pady=(0, 3))
        self.country_var = tk.StringVar(value="USA")
        self.country_cb = ttk.Combobox(country_grp, textvariable=self.country_var,
                                       values=self.COUNTRIES, state="readonly", width=22)
        self.country_cb.pack(anchor=tk.W)

        chk_grp = tk.Frame(sep2, bg=C["card"])
        chk_grp.pack(side=tk.LEFT, pady=(16, 0))

        self.remote_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk_grp, text="Remote only", variable=self.remote_var).pack(anchor=tk.W, pady=2)

        self.fetch_desc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(chk_grp, text="Fetch details & links", variable=self.fetch_desc_var).pack(anchor=tk.W, pady=2)

        self.fetch_emails_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk_grp, text="Deep scan emails  🔍", variable=self.fetch_emails_var).pack(anchor=tk.W, pady=2)

        # ── Row 4: CV / Resume Matcher ──
        tk.Frame(body, bg=C["border"], height=1).pack(fill=tk.X, pady=(12, 8))

        cv_row = tk.Frame(body, bg=C["card"])
        cv_row.pack(fill=tk.X)

        cv_left = tk.Frame(cv_row, bg=C["card"])
        cv_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(cv_left, text="📄  CV / Resume Matcher",
                 font=FONT_LABEL, bg=C["card"], fg=C["primary"]).pack(anchor=tk.W, pady=(0, 4))

        cv_file_row = tk.Frame(cv_left, bg=C["card"])
        cv_file_row.pack(fill=tk.X)

        self.cv_path_var = tk.StringVar(value="No CV selected")
        cv_path_lbl = tk.Label(cv_file_row, textvariable=self.cv_path_var,
                               font=FONT_HINT, bg=C["entry_bg"], fg=C["text_muted"],
                               relief="solid", bd=1, anchor=tk.W, width=50, padx=6, pady=4)
        cv_path_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(cv_file_row, text="📂  Browse",
                   style="Add.TButton",
                   command=self._browse_cv).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(cv_left,
                 text="Supports PDF, DOCX, TXT — After searching, a Match % column will appear for each job.",
                 font=("Helvetica", 9), bg=C["card"], fg=C["text_muted"]).pack(anchor=tk.W, pady=(4, 0))

    # ── Job Sites Card ──────────────────────────────────────────────────────────

    def _build_sites_card(self, parent):
        body = self._card(parent, "🌐  Job Sites",
                          side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        site_icons = {"linkedin": "🔷", "indeed": "🔵"}
        for label, value in self.SITES:
            var = tk.BooleanVar(value=True)
            self.site_vars[value] = var

            row = tk.Frame(body, bg=C["card"],
                           highlightbackground=C["border"],
                           highlightthickness=1)
            row.pack(fill=tk.X, pady=4, ipady=4)
            tk.Label(row, text=site_icons.get(value, "●"),
                     font=("Helvetica", 14), bg=C["card"]).pack(side=tk.LEFT, padx=(8, 4))
            ttk.Checkbutton(row, text=f"  {label}", variable=var).pack(side=tk.LEFT, padx=(0, 12))

        # Divider
        tk.Frame(body, bg=C["border"], height=1).pack(fill=tk.X, pady=12)

        # Proxies
        tk.Label(body, text="Proxies (optional)", font=FONT_LABEL,
                 bg=C["card"], fg=C["text_sub"]).pack(anchor=tk.W)
        tk.Label(body, text="Format: user:pass@host:port",
                 font=FONT_HINT, bg=C["card"], fg=C["text_muted"]).pack(anchor=tk.W, pady=(2, 5))
        self.proxy_text = tk.Text(body, width=26, height=4, font=("Courier", 10),
                                  bg=C["entry_bg"], fg=C["text"],
                                  relief="solid", bd=1, highlightthickness=0,
                                  insertbackground=C["primary"])
        self.proxy_text.pack(fill=tk.X)

    # ── Custom Sites Card ───────────────────────────────────────────────────────

    def _build_custom_card(self, parent):
        body = self._card(parent, "➕  Custom Job Sites",
                          side=tk.LEFT, fill=tk.Y)

        tk.Label(body,
                 text="Add career pages or job\nboards to scan for emails\nwhen Deep Scan is on.",
                 font=("Helvetica", 10), bg=C["card"],
                 fg=C["text_muted"], justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        lb_frame = tk.Frame(body, bg=C["card"],
                            highlightbackground=C["border"],
                            highlightthickness=1)
        lb_frame.pack(fill=tk.BOTH, expand=True)

        self.custom_lb = tk.Listbox(lb_frame,
                                    font=("Helvetica", 10),
                                    relief="flat", bd=0, width=30, height=5,
                                    bg=C["entry_bg"],
                                    fg=C["text"],
                                    selectbackground=C["hover"],
                                    selectforeground=C["text"],
                                    activestyle="none")
        self.custom_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL, command=self.custom_lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.custom_lb.configure(yscrollcommand=sb.set)

        btn_row = tk.Frame(body, bg=C["card"])
        btn_row.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_row, text="＋  Add Site",
                   style="Add.TButton",
                   cursor="hand2",
                   command=self._add_site).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(btn_row, text="✕  Remove",
                   style="Remove.TButton",
                   cursor="hand2",
                   command=self._remove_site).pack(side=tk.LEFT)

    # ── Action Bar ──────────────────────────────────────────────────────────────

    def _build_action_bar(self, parent):
        bar = tk.Frame(parent, bg=C["bg"])
        bar.pack(fill=tk.X, pady=(0, 10))

        self.search_btn = ttk.Button(bar, text="🔍   Search Jobs",
                                     style="Search.TButton",
                                     cursor="hand2",
                                     command=self._on_search)
        self.search_btn.pack(side=tk.LEFT, padx=(0, 14))

        self.export_btn = ttk.Button(bar, text="💾   Export CSV",
                                     style="Export.TButton",
                                     cursor="hand2",
                                     state=tk.DISABLED,
                                     command=self._on_export)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.sort_btn = ttk.Button(bar, text="🎯  Sort by Match",
                                   style="Add.TButton",
                                   cursor="hand2",
                                   state=tk.DISABLED,
                                   command=self._sort_by_match)
        self.sort_btn.pack(side=tk.LEFT, padx=(0, 22))

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=220)
        self.progress.pack(side=tk.LEFT, padx=(0, 16))

        self.status_label = tk.Label(bar, text="Ready to search",
                                     font=("Helvetica", 11),
                                     bg=C["bg"], fg=C["text_muted"])
        self.status_label.pack(side=tk.LEFT)

    # ── Status Strip ────────────────────────────────────────────────────────────

    def _build_status_strip(self, parent):
        strip = tk.Frame(parent, bg=C["card"],
                         highlightbackground=C["border"], highlightthickness=1)
        strip.pack(fill=tk.X, pady=(0, 10))
        inner = tk.Frame(strip, bg=C["card"])
        inner.pack(fill=tk.X, padx=16, pady=8)
        tk.Label(inner, text="Status:", font=FONT_LABEL,
                 bg=C["card"], fg=C["text_sub"]).pack(side=tk.LEFT, padx=(0, 16))
        self.status_labels: dict = {}
        for display_name, site_key in self.SITES:
            lbl = tk.Label(inner,
                           text=f"  {display_name}: —  ",
                           font=("Helvetica", 11),
                           bg=C["card"], fg=C["text_muted"],
                           relief="solid", bd=1,
                           padx=8, pady=4)
            lbl.pack(side=tk.LEFT, padx=(0, 8))
            self.status_labels[site_key] = lbl

    # ── Results Panel ────────────────────────────────────────────────────────────

    def _build_results_panel(self, parent):
        card_outer = tk.Frame(parent, bg=C["card"],
                              highlightbackground=C["border"], highlightthickness=1)
        card_outer.pack(fill=tk.BOTH, expand=True)

        # Card title bar
        hdr_bar = tk.Frame(card_outer, bg=C["card_hdr"])
        hdr_bar.pack(fill=tk.X)
        hdr_inner = tk.Frame(hdr_bar, bg=C["card_hdr"])
        hdr_inner.pack(fill=tk.X, padx=16, pady=10)

        tk.Label(hdr_inner, text="📋  Search Results",
                 font=FONT_TITLE, bg=C["card_hdr"], fg=C["primary"]).pack(side=tk.LEFT)
        self.count_label = tk.Label(hdr_inner, text="",
                                    font=("Helvetica", 11),
                                    bg=C["card_hdr"], fg=C["text_muted"])
        self.count_label.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(hdr_inner,
                 text="💡 Click 🎯 Match % for skill breakdown  ·  Click Website/Job Link to open  ·  Click 📧 to compose email",
                 font=FONT_HINT, bg=C["card_hdr"], fg=C["text_muted"]).pack(side=tk.RIGHT)

        tk.Frame(card_outer, bg=C["border"], height=1).pack(fill=tk.X)

        # Table area
        tbl = tk.Frame(card_outer, bg=C["card"])
        tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        columns = ("match_score", "site", "title", "company", "company_url_direct",
                   "location", "date_posted", "job_type", "emails", "job_url")
        self.tree = ttk.Treeview(tbl, columns=columns, show="headings", selectmode="browse")

        col_cfg = {
            "match_score":        ("🎯 Match %",       90),
            "site":               ("Platform",          90),
            "title":              ("Job Title",         220),
            "company":            ("Company",           150),
            "company_url_direct": ("Website",           190),
            "location":           ("Location",          145),
            "date_posted":        ("Date",               90),
            "job_type":           ("Type",               85),
            "emails":             ("📧 Email",           185),
            "job_url":            ("Job Link",           210),
        }
        for col, (heading, width) in col_cfg.items():
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=55)

        vsb = ttk.Scrollbar(tbl, orient=tk.VERTICAL,   command=self.tree.yview)
        hsb = ttk.Scrollbar(tbl, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tbl.grid_rowconfigure(0, weight=1)
        tbl.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure("odd",        background=C["row_odd"])
        self.tree.tag_configure("even",       background=C["row_even"])
        self.tree.tag_configure("match_high", background="#D1FAE5", foreground="#065F46")  # green
        self.tree.tag_configure("match_mid",  background="#FEF3C7", foreground="#92400E")  # amber
        self.tree.tag_configure("match_low",  background="#FEE2E2", foreground="#991B1B")  # red
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Motion>",          self._on_tree_motion)

    # ── Watermark Footer ────────────────────────────────────────────────────────

    def _build_watermark(self, parent):
        wm_frame = tk.Frame(parent, bg=C["bg"])
        wm_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        tk.Label(wm_frame, text="Developed by Yassine Youssef   |   ",
                 font=("Helvetica", 10, "bold"), bg=C["bg"], fg=C["text_muted"]).pack(side=tk.LEFT)

        li_link = tk.Label(wm_frame, text="https://www.linkedin.com/in/yassine-youssef/",
                           font=("Helvetica", 10, "bold", "underline"),
                           bg=C["bg"], fg=C["primary"], cursor="hand2")
        li_link.pack(side=tk.LEFT)
        li_link.bind("<Button-1>", lambda e: webbrowser.open("https://www.linkedin.com/in/yassine-youssef/"))

        tk.Label(wm_frame, text="   |   ",
                 font=("Helvetica", 10, "bold"), bg=C["bg"], fg=C["text_muted"]).pack(side=tk.LEFT)

        gh_link = tk.Label(wm_frame, text="https://github.com/yassine50",
                           font=("Helvetica", 10, "bold", "underline"),
                           bg=C["bg"], fg=C["text"], cursor="hand2")
        gh_link.pack(side=tk.LEFT)
        gh_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/yassine50"))

    # ── Custom Site Management ──────────────────────────────────────────────────

    def _add_site(self):
        url = simpledialog.askstring(
            "Add Custom Job Site",
            "Paste the URL of a career page or job board:\n(e.g. https://company.com/careers)",
            parent=self.root)
        if url:
            url = url.strip()
            if not url.startswith("http"):
                url = "https://" + url
            if url not in self.custom_sites:
                self.custom_sites.append(url)
                self.custom_lb.insert(tk.END, url)

    def _remove_site(self):
        sel = self.custom_lb.curselection()
        if sel:
            idx = sel[0]
            self.custom_lb.delete(idx)
            del self.custom_sites[idx]

    # ── Dynamic UI ──────────────────────────────────────────────────────────────

    def _toggle_country_cb(self, *_):
        if hasattr(self, "country_cb"):
            state = "readonly" if self.site_vars.get("indeed", tk.BooleanVar()).get() else "disabled"
            self.country_cb.configure(state=state)

    # ── Tree Interaction ────────────────────────────────────────────────────────

    def _on_tree_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col_idx = int(self.tree.identify_column(event.x).replace("#", "")) - 1
            if self.tree["columns"][col_idx] in ("job_url", "company_url_direct", "emails", "match_score"):
                self.tree.config(cursor="hand2")
                return
        self.tree.config(cursor="")

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        col_idx  = int(self.tree.identify_column(event.x).replace("#", "")) - 1
        col_name = self.tree["columns"][col_idx]
        item_id  = self.tree.identify_row(event.y)
        if not item_id:
            return
        values   = self.tree.item(item_id, "values")
        cell_val = values[col_idx] if col_idx < len(values) else ""

        if col_name == "match_score":
            breakdown = self._match_breakdowns.get(item_id)
            if breakdown:
                job_title = values[2] if len(values) > 2 else ""
                company   = values[3] if len(values) > 3 else ""
                self._show_match_popup(breakdown, job_title, company)
            else:
                messagebox.showinfo("No breakdown",
                    "Load a CV first, then run a search to see the match breakdown.")

        elif col_name in ("job_url", "company_url_direct"):
            if cell_val and cell_val.startswith("http"):
                webbrowser.open(cell_val)

        elif col_name == "emails" and cell_val:
            # cols: match=0, site=1, title=2, company=3, website=4, location=5, date=6, type=7, email=8, url=9
            job_title = values[2] if len(values) > 2 else "the position"
            company   = values[3] if len(values) > 3 else "your company"
            location  = values[5] if len(values) > 5 else ""
            job_type  = values[7] if len(values) > 7 else ""
            job_url   = values[9] if len(values) > 9 else ""

            raw   = cell_val.strip().lstrip("[").rstrip("]").replace("'", "").replace('"', "")
            email = raw.split(",")[0].strip()

            subject   = f"Application for {job_title} at {company}"
            loc_part  = f" in {location}" if location else ""
            type_part = f" ({job_type})"  if job_type else ""

            body_lines = [
                f"Dear Hiring Team at {company},",
                "",
                f"I am writing to express my strong interest in the {job_title}{type_part} "
                f"position{loc_part} at {company}.",
                "",
                "After reviewing the job posting, I am confident that my skills and experience "
                "align well with your requirements. I would be thrilled to contribute to your "
                "team and discuss how I can add value.",
                "",
                "Please find my resume attached. I am available at your earliest "
                "convenience for an interview.",
            ]
            if job_url and job_url.startswith("http"):
                body_lines += ["", f"Job Reference: {job_url}"]
            body_lines += [
                "", "Thank you for your time and consideration.",
                "", "Best regards,",
                "[Your Name]", "[Your Phone Number]", "[Your LinkedIn Profile]",
            ]

            mailto = (
                f"mailto:{urllib.parse.quote(email)}"
                f"?subject={urllib.parse.quote(subject)}"
                f"&body={urllib.parse.quote(chr(10).join(body_lines))}"
            )
            webbrowser.open(mailto)

    # ── Search Logic ────────────────────────────────────────────────────────────

    def _on_search(self):
        if self.is_searching:
            return
        selected_sites = [k for k, v in self.site_vars.items() if v.get()]
        if not selected_sites and not self.custom_sites:
            messagebox.showwarning("No sites selected",
                                   "Please select LinkedIn, Indeed, or add a custom site.")
            return
        search_term = self.search_term_var.get().strip()
        if not search_term:
            messagebox.showwarning("No keywords", "Please enter search keywords.")
            return

        proxy_raw = self.proxy_text.get("1.0", tk.END).strip()
        proxies   = [p.strip() for p in proxy_raw.splitlines() if p.strip()] or None

        params = {
            "site_name":                  selected_sites,
            "search_term":                search_term,
            "location":                   self.location_var.get().strip() or None,
            "results_wanted":             self.results_var.get(),
            "hours_old":                  self.HOURS_OLD_OPTIONS[self.hours_old_var.get()],
            "job_type":                   self.JOB_TYPE_OPTIONS[self.job_type_var.get()],
            "is_remote":                  self.remote_var.get(),
            "fetch_emails":               self.fetch_emails_var.get(),
            "linkedin_fetch_description": self.fetch_desc_var.get(),
            "proxies":                    proxies,
            "country_indeed":             self.country_var.get(),
            "verbose":                    2,
        }
        self._start_search(params)

    def _start_search(self, params):
        self.is_searching = True
        self.search_btn.configure(state=tk.DISABLED)
        self.export_btn.configure(state=tk.DISABLED)
        self.progress.start(10)
        self.status_label.configure(text="Searching…", fg=C["primary"])

        for k, lbl in self.status_labels.items():
            if self.site_vars.get(k, tk.BooleanVar()).get():
                lbl.configure(text=f"  {self._display_name(k)}: ⏳  ", fg=C["primary"],
                              bg="#EFF6FF", relief="solid")
            else:
                lbl.configure(text=f"  {self._display_name(k)}: —  ", fg=C["text_muted"],
                              bg=C["card"])

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.count_label.configure(text="")
        threading.Thread(target=self._search_worker, args=(params,), daemon=True).start()

    def _search_worker(self, params):
        try:
            from jobspy import scrape_jobs_with_status, fetch_company_emails
            df, statuses = scrape_jobs_with_status(**params)

            if self.custom_sites and params.get("fetch_emails"):
                custom_rows = []
                for site_url in self.custom_sites:
                    emails = fetch_company_emails(site_url, follow_links=True)
                    domain = site_url.split("/")[2] if "/" in site_url else site_url
                    custom_rows.append({
                        "site": "Custom", "title": "—", "company": domain,
                        "company_url_direct": site_url, "location": "—",
                        "date_posted": "—", "job_type": "—",
                        "emails": str(sorted(emails)) if emails else "",
                        "job_url": site_url,
                    })
                if custom_rows:
                    extra = pd.DataFrame(custom_rows)
                    df = pd.concat([df, extra], ignore_index=True) if df is not None else extra

            self.root.after(0, self._on_search_done, df, statuses, None)
        except Exception as e:
            self.root.after(0, self._on_search_done, None, {}, str(e))

    def _on_search_done(self, df, statuses, error):
        self.is_searching = False
        self.search_btn.configure(state=tk.NORMAL)
        self.progress.stop()

        if error:
            self.status_label.configure(text=f"Error: {error}", fg=C["error"])
            messagebox.showerror("Search Error", error)
            return

        for site_key, info in statuses.items():
            lbl = self.status_labels.get(site_key)
            if not lbl:
                continue
            name   = self._display_name(site_key)
            status = info["status"]
            count  = info["count"]
            msg    = info["message"]
            if status == "success":
                lbl.configure(text=f"  {name}: ✅  {count} jobs  ",
                              fg=C["success"], bg="#F0FFF4", relief="solid")
            elif status == "warning":
                lbl.configure(text=f"  {name}: ⚠️  No results  ",
                              fg=C["warning"], bg="#FFFBEB", relief="solid")
            else:
                lbl.configure(text=f"  {name}: ❌  Error  ",
                              fg=C["error"], bg="#FFF5F5", relief="solid")
                lbl.bind("<Enter>", lambda e, m=msg: self.status_label.configure(
                    text=m, fg=C["error"]))
                lbl.bind("<Leave>", lambda e: self.status_label.configure(
                    text="Hover over ❌ for error details", fg=C["text_muted"]))

        self.current_jobs_df = df
        if df is not None and not df.empty:
            data_cols = ["site", "title", "company", "company_url_direct",
                         "location", "date_posted", "job_type", "emails", "job_url"]

            # Build job rows for the matcher
            self._match_breakdowns = {}
            cv_text = self._cv_text
            if cv_text:
                try:
                    from cv_matcher import batch_match
                    job_rows = []
                    for _, row in df.iterrows():
                        parts = []
                        for col in ("description", "job_description", "company",
                                    "location", "job_type"):
                            v = row.get(col, "")
                            if v and not pd.isna(v):
                                parts.append(str(v))
                        job_rows.append({
                            "text":  " ".join(parts),
                            "title": str(row.get("title", "") or ""),
                        })
                    match_results = batch_match(cv_text, job_rows)
                except Exception as ex:
                    match_results = [(None, {}) for _ in range(len(df))]
                    self.status_label.configure(
                        text=f"Match error: {ex}", fg=C["warning"])
            else:
                match_results = [(None, {}) for _ in range(len(df))]

            for i, ((_, row), (score, breakdown)) in enumerate(
                    zip(df.iterrows(), match_results)):
                if score is not None:
                    score_str = f"{score}%"
                    tag = ("match_high" if score >= 70 else
                           "match_mid"  if score >= 40 else "match_low")
                else:
                    score_str = "— (no CV)"
                    tag = "odd" if i % 2 == 0 else "even"

                vals = [score_str]
                for col in data_cols:
                    v = row.get(col, "")
                    if pd.isna(v) or v is None:
                        v = ""
                    vals.append(str(v)[:130])

                item_id = self.tree.insert("", tk.END, values=vals, tags=(tag,))
                if breakdown:
                    self._match_breakdowns[item_id] = breakdown

            total = len(df)
            matched = sum(1 for s, _ in match_results if s is not None)
            self.count_label.configure(text=f"  —  {total} jobs found", fg=C["success"])
            self.status_label.configure(text=f"✅  Done — {total} jobs found", fg=C["success"])
            self.export_btn.configure(state=tk.NORMAL)
            if matched > 0:
                self.sort_btn.configure(state=tk.NORMAL)
        else:
            self.count_label.configure(text="  —  0 jobs found", fg=C["warning"])
            self.status_label.configure(
                text="No results — try different keywords, location or country",
                fg=C["warning"])

    # ── Export ──────────────────────────────────────────────────────────────────

    def _on_export(self):
        if self.current_jobs_df is None or self.current_jobs_df.empty:
            messagebox.showinfo("Nothing to export", "No job data to export.")
            return
        default_name = f"jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if filepath:
            try:
                self.current_jobs_df.to_csv(filepath, quoting=csv.QUOTE_NONNUMERIC,
                                            escapechar="\\", index=False)
                self.status_label.configure(
                    text=f"✅  Exported {len(self.current_jobs_df)} jobs to {filepath}",
                    fg=C["success"])
                messagebox.showinfo("Export Successful",
                                    f"Saved {len(self.current_jobs_df)} jobs to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _display_name(self, site_key: str) -> str:
        for display, key in self.SITES:
            if key == site_key:
                return display
        return site_key.capitalize()

    # ── CV Parsing & Matching ────────────────────────────────────────────────────

    def _browse_cv(self):
        path = filedialog.askopenfilename(
            title="Select your CV / Resume",
            filetypes=[
                ("All supported", "*.pdf *.docx *.txt"),
                ("PDF files", "*.pdf"),
                ("Word documents", "*.docx"),
                ("Text files", "*.txt"),
            ]
        )
        if not path:
            return
        try:
            text = self._parse_cv(path)
            if not text.strip():
                messagebox.showwarning("Empty CV", "Could not extract any text from the selected file.")
                return
            self._cv_text = text
            filename = os.path.basename(path)
            self.cv_path_var.set(f"✅  {filename}  ({len(text.split())} words extracted)")
            self.status_label.configure(
                text=f"CV loaded: {filename} — run a search to see match scores",
                fg=C["success"])
        except Exception as e:
            messagebox.showerror("CV Parse Error", f"Could not read the CV:\n{e}")

    def _parse_cv(self, path: str) -> str:
        """Extract plain text from a PDF, DOCX, or TXT file."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".pdf":
            try:
                import PyPDF2
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
            except ImportError:
                raise RuntimeError("PyPDF2 not installed. Run: pip install PyPDF2")
        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(path)
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                raise RuntimeError("python-docx not installed. Run: pip install python-docx")
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    # ── Recruiter Search Logic ──────────────────────────────────────────────────

    def _on_recruiter_search(self):
        title  = self.rec_title_var.get().strip()
        loc    = self.rec_loc_var.get().strip()
        jd     = self.rec_jd_text.get("1.0", tk.END).strip()
        skills_raw = self.rec_skills_var.get().strip()

        if not title:
            messagebox.showwarning("Missing Info", "Please enter a Job Title.")
            return
        if not jd:
            messagebox.showwarning("Missing Info", "Please paste a Job Description.")
            return

        self.rec_search_btn.configure(state=tk.DISABLED)
        self.rec_status_label.configure(
            text="🔍  Building smart X-Ray query & searching LinkedIn…", fg=C["text"])
        self.rec_progress.start()

        for item in self.rec_tree.get_children():
            self.rec_tree.delete(item)
        self.rec_breakdowns = {}

        max_res = self.rec_results_var.get()
        threading.Thread(
            target=self._recruiter_search_worker,
            args=(title, loc, jd, skills_raw, max_res),
            daemon=True
        ).start()

    def _recruiter_search_worker(self, title, loc, jd, skills_raw, max_res):
        try:
            import time
            from ddgs import DDGS
            from cv_matcher import _extract_skills, _skill_freq_in_text, TECH_SKILLS

            # ── Build smart X-Ray query variants ─────────────────────────────
            
            # Extract skills and sort them DETERMINISTICALLY by frequency in the JD, then alphabetically
            jd_skills_set = _extract_skills(jd, TECH_SKILLS)
            scored_skills = [(s, _skill_freq_in_text(jd, s)) for s in jd_skills_set]
            scored_skills.sort(key=lambda x: (-x[1], x[0]))  # -freq descending, then alphabetical
            auto_skills = [s for s, freq in scored_skills][:6]

            manual = [s.strip() for s in skills_raw.split(",") if s.strip()]
            
            # Combine manually entered and auto skills deterministically (deduplicate keeping order)
            all_skills = []
            for s in (manual + auto_skills):
                if s not in all_skills:
                    all_skills.append(s)

            # Remove strict quotes to broaden the search and get more people
            t_clean = title.replace('"', '').strip()
            l_clean = loc.replace('"', '').strip()
            
            base_q = f'site:linkedin.com/in/ {t_clean}'
            if l_clean:
                base_q += f' {l_clean}'

            queries = [
                base_q,  # Broadest search
            ]
            
            # Create overlapping skill variants to pull in different groups of people
            if all_skills:
                queries.append(base_q + " " + " ".join(f'"{s}"' for s in all_skills[:2]))
            if len(all_skills) >= 2:
                queries.append(base_q + " " + " ".join(f'"{s}"' for s in all_skills[1:3]))
            if len(all_skills) >= 4:
                queries.append(base_q + " " + " ".join(f'"{s}"' for s in all_skills[2:4]))
            
            # Fallback: Relaxed title (e.g. if title is "Senior Python Engineer", fallback to "Python Engineer")
            words = t_clean.split()
            if len(words) > 1:
                relaxed_title = " ".join(words[1:])
                rel_q = f'site:linkedin.com/in/ {relaxed_title}'
                if l_clean: rel_q += f' {l_clean}'
                queries.append(rel_q)
                if all_skills:
                    queries.append(rel_q + " " + " ".join(f'"{s}"' for s in all_skills[:2]))

            # ── Fetch results from all query variants ─────────────────────
            seen_urls = set()
            results   = []
            # We want to fetch max_res results TOTAL.
            # Give each query a chance to fetch up to max_res so we can fill the quota if one fails.
            for idx, q in enumerate(queries):
                if idx > 0:
                    time.sleep(1.5)  # Backoff to avoid DDG rate limiting
                try:
                    for r in DDGS().text(q, max_results=max_res):
                        url = r.get("href", "")
                        if "linkedin.com/in/" in url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append(r)
                        if len(results) >= max_res:
                            break
                except Exception:
                    pass
                if len(results) >= max_res:
                    break

            self.root.after(0, self._on_rec_search_done, results, jd, title,
                            all_skills, l_clean, None)
        except Exception as e:
            self.root.after(0, self._on_rec_search_done, None, None, None, [], "", str(e))

    def _on_rec_search_done(self, results, jd, job_title, matched_skills, req_loc, error):
        self.rec_progress.stop()
        self.rec_search_btn.configure(state=tk.NORMAL)

        if error:
            self.rec_status_label.configure(text=f"Error: {error}", fg=C["error"])
            messagebox.showerror("Search Error", error)
            return

        if not results:
            self.rec_status_label.configure(
                text="No candidates found — try broader title or fewer skill filters.",
                fg=C["warning"])
            return

        self.rec_status_label.configure(
            text=f"⚙️  Analysing {len(results)} profiles with snippet-optimised matcher…",
            fg=C["text"])
        self.root.update_idletasks()

        # ── Parse DDG results into candidate dicts ───────────────────────────
        candidates = []
        raw_rows   = []
        for res in results:
            ddg_title = res.get("title", "")
            url       = res.get("href", "")
            snippet   = res.get("body", "")

            parts    = ddg_title.split(" - ")
            name     = parts[0].replace(" | LinkedIn", "").strip() if parts else "Unknown"
            headline = " - ".join(parts[1:]).strip() if len(parts) > 1 else ""

            candidates.append({"snippet": snippet, "headline": headline})
            raw_rows.append((name, headline, snippet, url))

        # ── Run parallel snippet-optimised matching ───────────────────────────
        try:
            from cv_matcher import batch_candidate_match
            match_results = batch_candidate_match(
                candidates, jd, job_title, req_loc, max_workers=8)
        except Exception as e:
            match_results = [(0, {}) for _ in candidates]

        # ── Assemble final rows ───────────────────────────────────────────────
        rows = []
        for (score, bd), (name, headline, snippet, url) in zip(match_results, raw_rows):
            # "Open to work" badge in name column
            available = bd.get("available", False)
            disp_name = f"🟢 {name}" if available else name
            rows.append((score, disp_name, headline, snippet, url, bd))

        # Sort best-first, then alphabetically by name for tie-breaking
        rows.sort(key=lambda x: (-x[0], x[1]))

        for score, name, headline, snippet, url, bd in rows:
            score_str = f"{score}%"
            tag = ("match_high" if score >= 70 else
                   "match_mid"  if score >= 40 else "match_low")
            item_id = self.rec_tree.insert(
                "", tk.END,
                values=(score_str, name, headline, snippet[:250], url),
                tags=(tag,))
            self.rec_breakdowns[item_id] = bd

        skills_used = ", ".join(matched_skills[:4]) if matched_skills else "—"
        self.rec_status_label.configure(
            text=f"✅  {len(rows)} candidates ranked  ·  Skills queried: {skills_used}",
            fg=C["success"])

    def _on_rec_tree_motion(self, event):
        region = self.rec_tree.identify_region(event.x, event.y)
        if region == "cell":
            col_idx = int(self.rec_tree.identify_column(event.x).replace("#", "")) - 1
            if self.rec_tree["columns"][col_idx] in ("url", "match_score"):
                self.rec_tree.config(cursor="hand2")
                return
        self.rec_tree.config(cursor="")

    def _on_rec_tree_click(self, event):
        if self.rec_tree.identify_region(event.x, event.y) != "cell":
            return
        col_idx  = int(self.rec_tree.identify_column(event.x).replace("#", "")) - 1
        col_name = self.rec_tree["columns"][col_idx]
        item_id  = self.rec_tree.identify_row(event.y)
        if not item_id:
            return
        values = self.rec_tree.item(item_id, "values")
        if col_name == "url":
            url = values[4] if len(values) > 4 else ""
            if url:
                webbrowser.open(url)
        elif col_name == "match_score":
            bd = getattr(self, "rec_breakdowns", {}).get(item_id)
            if bd:
                cand_name = values[1] if len(values) > 1 else "Candidate"
                self._show_match_popup(bd, "Candidate Profile", cand_name)



    def _show_match_popup(self, bd: dict, job_title: str, company: str):
        """Show a detailed match breakdown + improvement tips in a scrollable popup."""
        score = bd.get("overall", 0)

        win = tk.Toplevel(self.root)
        win.title(f"Match Breakdown — {job_title or 'Job'}")
        win.geometry("600x680")
        win.minsize(500, 500)
        win.configure(bg=C["card"])
        win.grab_set()

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=C["primary"])
        hdr.pack(fill=tk.X)
        hdr_lbl = tk.Label(hdr, text=f"🎯  {score}%  Match",
                           font=("Helvetica", 18, "bold"),
                           bg=C["primary"], fg="white", padx=20, pady=12)
        hdr_lbl.pack(side=tk.LEFT)
        if job_title:
            tk.Label(hdr, text=f"{job_title[:40]}  @  {company[:30]}",
                     font=("Helvetica", 11),
                     bg=C["primary"], fg="#BFDBFE", padx=10).pack(side=tk.LEFT)
        tk.Button(hdr, text="✕", font=("Helvetica", 12, "bold"),
                  bg=C["primary"], fg="white",
                  activebackground=C["primary_dark"],
                  relief="flat", cursor="hand2", padx=14,
                  command=win.destroy).pack(side=tk.RIGHT, padx=8)

        # ── Scrollable body ──────────────────────────────────────────────────
        canvas = tk.Canvas(win, bg=C["card"], highlightthickness=0)
        vsb    = ttk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        body = tk.Frame(canvas, bg=C["card"])
        canvas_win = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(canvas_win, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Mouse-wheel scroll — bind only while popup is open, unbind on close
        def _mw_scroll(e):
            try:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass

        _mw_id = win.bind_all("<MouseWheel>", _mw_scroll)

        def _on_popup_close():
            try:
                win.unbind_all("<MouseWheel>")
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_popup_close)
        # Update close button to also clean up binding
        for widget in hdr.winfo_children():
            if isinstance(widget, tk.Button) and "✕" in str(widget.cget("text")):
                widget.configure(command=_on_popup_close)

        pad = {"padx": 20}

        # ── Score bars ───────────────────────────────────────────────────────
        tk.Label(body, text="Score Breakdown",
                 font=FONT_TITLE, bg=C["card"], fg=C["primary"],
                 **pad).pack(anchor=tk.W, pady=(16, 6))

        def bar_row(label, value, fg_col, bg_bar="#E5E7EB"):
            row = tk.Frame(body, bg=C["card"])
            row.pack(fill=tk.X, **pad, pady=3)
            tk.Label(row, text=label, font=("Helvetica", 10, "bold"),
                     bg=C["card"], fg=C["text_sub"],
                     width=24, anchor=tk.W).pack(side=tk.LEFT)
            bar_bg = tk.Frame(row, bg=bg_bar, width=180, height=16)
            bar_bg.pack(side=tk.LEFT, padx=(0, 8))
            bar_bg.pack_propagate(False)
            fill_w = max(4, int(value / 100 * 180))
            tk.Frame(bar_bg, bg=fg_col, width=fill_w, height=16).pack(side=tk.LEFT)
            tk.Label(row, text=f"{value}%", font=("Helvetica", 10, "bold"),
                     bg=C["card"], fg=fg_col).pack(side=tk.LEFT)

        bar_row("⚙️  Technical skills",    bd.get("tech_score", 0),     "#1A56DB", "#DBEAFE")
        bar_row("📖  Semantic similarity",  bd.get("semantic_score", 0), "#5B21B6", "#EDE9FE")
        bar_row("🏷️  Role / title fit",     bd.get("title_score", 0),    "#0B7A4E", "#D1FAE5")
        bar_row("🤝  Soft skills",          bd.get("soft_score", 0),     "#B45309", "#FEF3C7")
        bar_row("🏢  Domain / industry",    bd.get("domain_score", 0),   "#0E7490", "#CFFAFE")
        bar_row("🎓  Education",            bd.get("edu_score", 0),      "#6D28D9", "#EDE9FE")

        # Domain info row
        jd_dom = bd.get("job_domain", "")
        cv_dom = bd.get("cv_domain", "")
        if jd_dom:
            dom_text = (f"🏢  Job domain: {jd_dom}"
                        + (f"  ·  Your domain: {cv_dom}" if cv_dom else "  ·  No domain detected in your CV"))
            tk.Label(body, text=dom_text, font=("Helvetica", 9, "italic"),
                     bg=C["card"], fg=C["text_muted"], **pad).pack(anchor=tk.W, pady=(0, 4))

        if bd.get("seniority_gap"):
            sn = {-1:"?", 0:"Intern", 1:"Junior", 2:"Mid", 3:"Senior", 4:"Lead/Principal", 5:"Director"}
            cv_s  = sn.get(bd.get("cv_seniority", -1), "?")
            job_s = sn.get(bd.get("job_seniority", -1), "?")
            warn_s = tk.Frame(body, bg="#FFF7ED",
                              highlightbackground="#F59E0B", highlightthickness=1)
            warn_s.pack(fill=tk.X, **pad, pady=(4, 2))
            tk.Label(warn_s,
                     text=f"⚠️  Seniority gap: your CV shows {cv_s} level, job targets {job_s}.",
                     font=("Helvetica", 10), bg="#FFF7ED", fg="#92400E",
                     padx=8, pady=5).pack(anchor=tk.W)

        if bd.get("exp_penalty", 0) > 0:
            cv_yr  = bd.get("cv_exp_years", 0)
            job_yr = bd.get("job_exp_years", 0)
            warn = tk.Frame(body, bg="#FFF7ED",
                            highlightbackground="#F59E0B", highlightthickness=1)
            warn.pack(fill=tk.X, **pad, pady=(2, 2))
            tk.Label(warn,
                     text=f"⚠️  Experience gap: {cv_yr} yrs in CV vs {job_yr} yrs required  "
                          f"(−{bd['exp_penalty']} pts)",
                     font=("Helvetica", 10), bg="#FFF7ED", fg="#92400E",
                     padx=8, pady=5).pack(anchor=tk.W)

        if bd.get("education_gap"):
            warn2 = tk.Frame(body, bg="#FFF7ED",
                             highlightbackground="#F59E0B", highlightthickness=1)
            warn2.pack(fill=tk.X, **pad, pady=2)
            tk.Label(warn2,
                     text="🎓  Education gap detected — check the degree requirement.",
                     font=("Helvetica", 10), bg="#FFF7ED", fg="#92400E",
                     padx=8, pady=5).pack(anchor=tk.W)


        tk.Frame(body, bg=C["border"], height=1).pack(fill=tk.X, **pad, pady=(10, 4))

        # ── Skills tags helper ───────────────────────────────────────────────
        def skills_section(title, skills, fg, bg_tag, required_set=None):
            if not skills and not title.startswith("❌"):
                return
            tk.Label(body, text=title, font=("Helvetica", 10, "bold"),
                     bg=C["card"], fg=fg, **pad).pack(anchor=tk.W, pady=(6, 2))
            if skills:
                # Wrap tags in a flow frame
                wrap = tk.Frame(body, bg=C["card"])
                wrap.pack(fill=tk.X, **pad, pady=(0, 4))
                for s in skills:
                    is_req = required_set and s in required_set
                    tag_bg = "#FECACA" if is_req else bg_tag
                    tag_fg = "#991B1B" if is_req else fg
                    badge  = "★ " if is_req else ""
                    lbl = tk.Label(wrap, text=f" {badge}{s} ",
                                   font=("Helvetica", 9, "bold" if is_req else "normal"),
                                   bg=tag_bg, fg=tag_fg,
                                   relief="flat", padx=6, pady=3)
                    lbl.pack(side=tk.LEFT, padx=2, pady=2)
                    if is_req:
                        lbl.config(highlightbackground="#DC2626", highlightthickness=1)
            else:
                tk.Label(body, text="  —  none detected",
                         font=("Helvetica", 9), bg=C["card"],
                         fg=C["text_muted"], **pad).pack(anchor=tk.W)

        req = set(bd.get("required_skills", []))
        matched_t = bd.get("matched_tech", [])
        missing_t = bd.get("missing_tech", [])
        matched_s = bd.get("matched_soft", [])
        missing_s = bd.get("missing_soft", [])

        skills_section(f"✅  Matched tech skills ({len(matched_t)})",
                       matched_t, "#065F46", "#D1FAE5")
        skills_section(f"❌  Missing tech skills ({len(missing_t)})",
                       missing_t, "#991B1B", "#FEE2E2", required_set=req)

        if matched_s or missing_s:
            skills_section(f"✅  Matched soft skills ({len(matched_s)})",
                           matched_s, "#065F46", "#D1FAE5")
            skills_section(f"❌  Missing soft skills ({len(missing_s)})",
                           missing_s, "#7C3AED", "#EDE9FE")

        if req:
            tk.Label(body,
                     text="  ★ = Required by employer (starred skills are highest priority)",
                     font=("Helvetica", 9, "italic"),
                     bg=C["card"], fg="#DC2626", **pad).pack(anchor=tk.W, pady=(2, 4))

        tk.Frame(body, bg=C["border"], height=1).pack(fill=tk.X, **pad, pady=(8, 4))

        # ── Tips section ─────────────────────────────────────────────────────
        tips = bd.get("tips", [])
        if tips:
            tk.Label(body, text="💡  How to Improve Your Match",
                     font=FONT_TITLE, bg=C["card"], fg=C["primary"],
                     **pad).pack(anchor=tk.W, pady=(8, 6))

            for tip in tips:
                tip_frame = tk.Frame(body, bg="#F0F9FF",
                                     highlightbackground=C["border"],
                                     highlightthickness=1)
                tip_frame.pack(fill=tk.X, **pad, pady=3)
                tk.Label(tip_frame, text=tip,
                         font=("Helvetica", 10),
                         bg="#F0F9FF", fg=C["text_sub"],
                         wraplength=500, justify=tk.LEFT,
                         padx=10, pady=7).pack(anchor=tk.W)

        tk.Frame(body, bg=C["card"], height=16).pack()  # bottom padding



    def _sort_by_match(self):
        """Re-sort the tree rows by match score descending."""
        rows = []
        for item_id in self.tree.get_children():
            vals = self.tree.item(item_id, "values")
            tags = self.tree.item(item_id, "tags")
            bd   = self._match_breakdowns.get(item_id)
            score_str = vals[0] if vals else "0"
            try:
                score = int(score_str.replace("%", "").strip())
            except Exception:
                score = -1
            rows.append((score, vals, tags, bd, item_id))

        rows.sort(key=lambda r: r[0], reverse=True)
        for i, (score, vals, tags, bd, old_id) in enumerate(rows):
            self.tree.delete(old_id)

        self._match_breakdowns = {}
        for i, (score, vals, tags, bd, _) in enumerate(rows):
            new_id = self.tree.insert("", tk.END, values=vals, tags=tags)
            if bd:
                self._match_breakdowns[new_id] = bd

        self.status_label.configure(
            text="✅  Sorted by match % (highest first)", fg=C["success"])


def main():
    root = tk.Tk()
    JobSearchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
