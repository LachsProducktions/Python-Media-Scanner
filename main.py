"""
main.py - GUI entrypoint for MediaScanner

Start with:
    python main.py

Requirements: standard library + optionally ffprobe/pymediainfo/mutagen for duration/hash support.
"""
import os
import json
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from scanner import Scanner
from compare import Compare
from settings import SettingsManager

APP_ROOT = Path(__file__).parent

class MediaScannerApp:
    def __init__(self, master):
        self.master = master
        master.title("MediaScanner")
        master.geometry("1000x650")

        # Settings
        self.settings = SettingsManager(APP_ROOT / "settings.json")
        self.settings_data = self.settings.load()

        # Scanner & Compare
        self.scan_queue = queue.Queue()
        self.scanner = None
        self.compare = Compare()

        # Notebook
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(fill="both", expand=True)

        # Create tabs according to settings order
        self.tabs = {}
        for name in self.settings_data.get("tab_order", ["Videos","Music","Photos","Other"]):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=name)
            self.tabs[name] = frame

        # Ensure important tabs exist
        for required in ("Compare","Settings"):
            if required not in self.tabs:
                frame = ttk.Frame(self.notebook)
                self.notebook.add(frame, text=required)
                self.tabs[required] = frame

        # Create UI for media tabs
        self.trees = {}
        for cat, frame in self.tabs.items():
            if cat in ("Compare","Settings"):
                continue
            self._build_media_tab(cat, frame)

        # Build compare and settings tabs
        self._build_compare_tab(self.tabs["Compare"])
        self._build_settings_tab(self.tabs["Settings"])

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(master, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x", side="bottom")

        # Progress
        self.progress = ttk.Progressbar(master, mode="determinate")
        self.progress.pack(fill="x", side="bottom")

        # Keep last scan data in memory
        self.last_scan = {"items": []}

    def _build_media_tab(self, name, parent):
        frm_top = ttk.Frame(parent)
        frm_top.pack(fill="x", padx=6, pady=6)
        ttk.Label(frm_top, text=f"{name}").pack(side="left")
        ttk.Button(frm_top, text="Scan Folder", command=lambda n=name: self.start_scan(n)).pack(side="left", padx=6)
        ttk.Button(frm_top, text="Export (json/txt)", command=lambda n=name: self.export_category(n)).pack(side="left", padx=6)
        ttk.Button(frm_top, text="Clear", command=lambda n=name: self.clear_tree(n)).pack(side="left", padx=6)
        # Sorting dropdown
        ttk.Label(frm_top, text="Sort by:").pack(side="left", padx=(20, 4))
        sort_choice = ttk.Combobox(frm_top, values=["Name", "Size", "Duration", "Ext"], width=10, state="readonly")
        sort_choice.set("Name")
        sort_choice.pack(side="left")

        ttk.Button(frm_top, text="Apply Sort", command=lambda n=name, c=sort_choice: self.sort_tree(n, c.get())).pack(side="left", padx=6)

        cols = ("Name","Path","Size","Duration","Type")
        tree = ttk.Treeview(parent, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.capitalize())
            tree.column(c, width=200 if c in ("Name","Path") else 90, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscroll=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.trees[name] = tree

    def _build_compare_tab(self, parent):
        frm = ttk.Frame(parent)
        frm.pack(fill="x", padx=6, pady=6)
        ttk.Button(frm, text="Live: Compare two folders", command=self.compare_two_folders).pack(side="left", padx=6)
        ttk.Button(frm, text="Compare folder vs saved scan", command=self.compare_folder_vs_file).pack(side="left", padx=6)
        ttk.Button(frm, text="Compare two saved scans", command=self.compare_file_vs_file).pack(side="left", padx=6)
        ttk.Button(frm, text="Export last compare", command=self.export_compare).pack(side="right", padx=6)

        # Two side-by-side trees for left/right folder contents + a summary tree below
        split = ttk.Frame(parent)
        split.pack(fill="both", expand=False, padx=6, pady=(6,0))

        # Left pane
        left_pane = ttk.Frame(split)
        left_pane.pack(side="left", fill="both", expand=True)
        ttk.Label(left_pane, text="Left").pack(anchor="w")
        lfrm = ttk.Frame(left_pane)
        lfrm.pack(fill="x")
        ttk.Label(lfrm, text="Sort by:").pack(side="left")
        self.left_sort_choice = ttk.Combobox(lfrm, values=["Name","Size","Ext"], width=10, state="readonly")
        self.left_sort_choice.set("Name")
        self.left_sort_choice.pack(side="left", padx=4)
        ttk.Button(lfrm, text="Apply", command=lambda: self.sort_compare_tree("left", self.left_sort_choice.get())).pack(side="left", padx=4)

        cols_lr = ("Name","Size","Ext")
        self.compare_tree_left = ttk.Treeview(left_pane, columns=cols_lr, show="headings")
        for c in cols_lr:
            self.compare_tree_left.heading(c, text=c)
            self.compare_tree_left.column(c, width=200 if c=="Name" else 90, anchor="w")
        vsb_l = ttk.Scrollbar(left_pane, orient="vertical", command=self.compare_tree_left.yview)
        self.compare_tree_left.configure(yscroll=vsb_l.set)
        vsb_l.pack(side="right", fill="y")
        self.compare_tree_left.pack(fill="both", expand=True)

        # Right pane
        right_pane = ttk.Frame(split)
        right_pane.pack(side="left", fill="both", expand=True)
        ttk.Label(right_pane, text="Right").pack(anchor="w")
        rfrm = ttk.Frame(right_pane)
        rfrm.pack(fill="x")
        ttk.Label(rfrm, text="Sort by:").pack(side="left")
        self.right_sort_choice = ttk.Combobox(rfrm, values=["Name","Size","Ext"], width=10, state="readonly")
        self.right_sort_choice.set("Name")
        self.right_sort_choice.pack(side="left", padx=4)
        ttk.Button(rfrm, text="Apply", command=lambda: self.sort_compare_tree("right", self.right_sort_choice.get())).pack(side="left", padx=4)

        self.compare_tree_right = ttk.Treeview(right_pane, columns=cols_lr, show="headings")
        for c in cols_lr:
            self.compare_tree_right.heading(c, text=c)
            self.compare_tree_right.column(c, width=200 if c=="Name" else 90, anchor="w")
        vsb_r = ttk.Scrollbar(right_pane, orient="vertical", command=self.compare_tree_right.yview)
        self.compare_tree_right.configure(yscroll=vsb_r.set)
        vsb_r.pack(side="right", fill="y")
        self.compare_tree_right.pack(fill="both", expand=True)

        # Summary tree (matches/only_left/only_right)
        cols = ("file","category","status","left_size","right_size")
        self.compare_tree = ttk.Treeview(parent, columns=cols, show="headings")
        for c in cols:
            self.compare_tree.heading(c, text=c.capitalize())
            self.compare_tree.column(c, width=200 if c=="file" else 100, anchor="w")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.compare_tree.yview)
        self.compare_tree.configure(yscroll=vsb.set)
        vsb.pack(side="right", fill="y")
        self.compare_tree.pack(fill="both", expand=True, padx=6, pady=(6,6))

        # tags for highlighting
        self.compare_tree_left.tag_configure("match", background="#d4f7d4")
        self.compare_tree_right.tag_configure("match", background="#d4f7d4")
        self.compare_tree.tag_configure("both_same", background="#d4f7d4")

        self.last_compare = []
        self.last_compare_left = []
        self.last_compare_right = []

    def _build_settings_tab(self, parent):
        frm = ttk.Frame(parent)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab order controls (simple up/down listbox)
        ttk.Label(frm, text="Tab order:").grid(row=0, column=0, sticky="w")
        self.lb_order = tk.Listbox(frm, height=6)
        for t in self.settings_data.get("tab_order", ["Videos","Music","Photos","Other"]):
            self.lb_order.insert("end", t)
        self.lb_order.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        btn_up = ttk.Button(frm, text="Up", command=self.move_tab_up)
        btn_down = ttk.Button(frm, text="Down", command=self.move_tab_down)
        btn_up.grid(row=1, column=1, sticky="n", padx=6)
        btn_down.grid(row=1, column=1, sticky="s", padx=6)

        # Hash option
        self.hash_var = tk.BooleanVar(value=self.settings_data.get("include_hash", False))
        cb_hash = ttk.Checkbutton(frm, text="Include SHA256 hash during scan (slow)", variable=self.hash_var)
        cb_hash.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8,0))

        # Export format
        ttk.Label(frm, text="Default export format:").grid(row=3, column=0, sticky="w", pady=(12,0))
        self.export_var = tk.StringVar(value=self.settings_data.get("export_format","json"))
        rb1 = ttk.Radiobutton(frm, text="json", value="json", variable=self.export_var)
        rb2 = ttk.Radiobutton(frm, text="txt", value="txt", variable=self.export_var)
        rb1.grid(row=4, column=0, sticky="w")
        rb2.grid(row=4, column=1, sticky="w")

        # Save button
        btn_save = ttk.Button(frm, text="Save Settings", command=self.save_settings)
        btn_save.grid(row=6, column=0, sticky="w", pady=12)

    def move_tab_up(self):
        sel = self.lb_order.curselection()
        if not sel: return
        i = sel[0]
        if i == 0: return
        val = self.lb_order.get(i)
        above = self.lb_order.get(i-1)
        self.lb_order.delete(i)
        self.lb_order.insert(i-1, val)
        self.lb_order.selection_set(i-1)

    def move_tab_down(self):
        sel = self.lb_order.curselection()
        if not sel: return
        i = sel[0]
        if i == self.lb_order.size()-1: return
        val = self.lb_order.get(i)
        below = self.lb_order.get(i+1)
        self.lb_order.delete(i)
        self.lb_order.insert(i+1, val)
        self.lb_order.selection_set(i+1)

    def save_settings(self):
        order = list(self.lb_order.get(0, "end"))
        self.settings_data["tab_order"] = order
        self.settings_data["include_hash"] = bool(self.hash_var.get())
        self.settings_data["export_format"] = self.export_var.get()
        self.settings.save(self.settings_data)
        messagebox.showinfo("Saved", "Settings saved. Restart to apply tab ordering visually.")

    def start_scan(self, category):
        folder = filedialog.askdirectory(title=f"Select {category} folder")
        if not folder:
            return

        self.status_var.set(f"Scanning {folder}...")
        self.progress["value"] = 0
        self.master.update_idletasks()

        def do_scan():
            self.scanner = Scanner(include_hash=False)
            items = self.scanner.scan_folder(folder, update_callback=self.on_scan_progress)
            self.last_scan["items"] = items

            # Filter category and display results
            filtered = [i for i in items if i["Category"] == category]
            
            # Use after to ensure display happens in main thread
            self.master.after(0, lambda: self.display_results(category, filtered))
            self.master.after(0, lambda: self.status_var.set(f"Scan complete ({len(filtered)} {category} items found)"))
            self.master.after(0, lambda: setattr(self.progress, "value", 100))

        threading.Thread(target=do_scan, daemon=True).start()


    def on_scan_progress(self, percent, current_file):
        """Callback for Scanner progress updates."""
        self.progress["value"] = percent
        self.status_var.set(f"Scanning: {os.path.basename(current_file)} ({percent}%)")
        self.master.update_idletasks()

    def sort_tree(self, category, sort_by):
        if not self.last_scan["items"]:
            messagebox.showinfo("No Data", "Please scan a folder first.")
            return

        sorted_items = self.scanner.sort_items(self.last_scan["items"], by=sort_by)
        filtered = [i for i in sorted_items if i["Category"] == category]
        self.display_results(category, filtered)
        self.status_var.set(f"Sorted by {sort_by}")

    def display_results(self, category, items):
        """Populate the Treeview in the given category tab with the provided items."""
        tree = self.trees.get(category)
        if not tree:
            return

        # Clear previous contents
        for row in tree.get_children():
            tree.delete(row)

        # Insert new rows
        for item in items:
            tree.insert(
                "",
                "end",
                values=(
                    item["Name"],
                    item["Path"],
                    item["Size_Display"],
                    item["Duration_Display"],
                    item["Ext"],
                ),
            )




    def master_event_populate(self, items):
        # Run in main thread via after
        def task():
            # clear all media trees
            for t in self.trees.values():
                for iid in t.get_children():
                    t.delete(iid)
            for it in items:
                cat = it.get("category","Other")
                if cat not in self.trees:
                    cat = "Other"
                tree = self.trees[cat]
                tree.insert("", "end", values=(it["name"], it["path"], it["size_display"], it.get("duration_display","N/A"), it["ext"]))
        self.master.after(10, task)

    def clear_tree(self, category):
        if category in self.trees:
            t = self.trees[category]
            for iid in t.get_children():
                t.delete(iid)

    def export_category(self, category):
        if not self.last_scan or not self.last_scan.get("items"):
            messagebox.showinfo("No data", "Please scan first.")
            return
        # filter items for category
        items = [it for it in self.last_scan["items"] if it.get("Category","Other")==category]
        if not items:
            messagebox.showinfo("Empty", f"No items in {category}")
            return
        fmt = self.export_var.get()
        path = filedialog.asksaveasfilename(defaultextension="."+fmt, filetypes=[(fmt.upper(), "*."+fmt)])
        if not path: return
        try:
            if fmt=="json":
                with open(path,"w",encoding="utf-8") as f:
                    json.dump(items, f, ensure_ascii=False, indent=2)
            else:
                with open(path,"w",encoding="utf-8") as f:
                    f.write("name\tpath\tsize\tduration\text\n")
                    for it in items:
                        f.write(f"{it['name']}\t{it['path']}\t{it['size_display']}\t{it.get('duration_display','N/A')}\t{it['ext']}\n")
            messagebox.showinfo("Exported", f"Export saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # Compare helpers
    def compare_two_folders(self):
        a = filedialog.askdirectory(title="Folder A", initialdir=os.path.expanduser("~"))
        if not a: return
        b = filedialog.askdirectory(title="Folder B", initialdir=os.path.expanduser("~"))
        if not b: return
        inc_hash = bool(self.hash_var.get())
        self.status_var.set("Starting comparison...")
        self.progress.config(mode="determinate")
        self.progress["value"] = 0
        self.master.update_idletasks()

        def update_progress(percent, current_file):
            self.master.after(0, lambda: self.progress.configure(value=percent))
            self.master.after(0, lambda: self.status_var.set(f"Comparing: {os.path.basename(current_file)} ({percent}%)"))
            self.master.update_idletasks()

        def do():
            data = self.compare.compare_folders(a, b, include_hash=inc_hash, update_callback=update_progress)
            # data is dict {left, right, results}
            self.last_compare = data.get("results", [])
            self.last_compare_left = data.get("left", [])
            self.last_compare_right = data.get("right", [])
            self.master.after(0, lambda: self.populate_compare(data))
            self.master.after(0, lambda: self.status_var.set("Compare complete"))
        threading.Thread(target=do, daemon=True).start()

    def compare_folder_vs_file(self):
        file = filedialog.askopenfilename(title="Select saved scan (json)", filetypes=[("json","*.json"),("txt","*.txt")])
        if not file: return
        folder = filedialog.askdirectory(title="Folder to compare", initialdir=os.path.expanduser("~"))
        if not folder: return
        inc_hash = bool(self.hash_var.get())
        self.status_var.set("Starting comparison...")
        self.progress.config(mode="determinate")
        self.progress["value"] = 0
        self.master.update_idletasks()

        def update_progress(percent, current_file):
            self.master.after(0, lambda: self.progress.configure(value=percent))
            self.master.after(0, lambda: self.status_var.set(f"Comparing: {os.path.basename(current_file)} ({percent}%)"))
            self.master.update_idletasks()

        def do():
            data = self.compare.compare_scanfile_vs_folder(file, folder, include_hash=inc_hash, update_callback=update_progress)
            self.last_compare = data.get("results", [])
            self.last_compare_left = data.get("left", [])
            self.last_compare_right = data.get("right", [])
            self.master.after(0, lambda: self.populate_compare(data))
            self.master.after(0, lambda: self.status_var.set("Compare complete"))
        threading.Thread(target=do, daemon=True).start()

    def compare_file_vs_file(self):
        a = filedialog.askopenfilename(title="Select saved scan A", filetypes=[("json","*.json"),("txt","*.txt")])
        if not a: return
        b = filedialog.askopenfilename(title="Select saved scan B", filetypes=[("json","*.json"),("txt","*.txt")])
        if not b: return
        self.status_var.set("Comparing two scan files...")
        self.progress.config(mode="indeterminate"); self.progress.start(10)
        def do():
            res = self.compare.compare_scanfiles(a,b)
            self.last_compare = res
            self.populate_compare(res)
            self.progress.stop()
            self.status_var.set("Compare complete")
        threading.Thread(target=do, daemon=True).start()

    def populate_compare(self, results):
        # results may be either a list (old format) or a dict {left,right,results}
        def task():
            # clear summary
            for iid in self.compare_tree.get_children():
                self.compare_tree.delete(iid)

            left_items = []
            right_items = []
            summary = []

            if isinstance(results, dict):
                left_items = results.get("left", [])
                right_items = results.get("right", [])
                summary = results.get("results", [])
            else:
                summary = results

            # helper to read fields with scanner/file compatibility
            def get_name(it):
                return (it.get("Name") or it.get("name") or "")
            def get_size(it):
                return it.get("Size") if it.get("Size") is not None else it.get("size")
            def get_size_display(it):
                return it.get("Size_Display") or it.get("size_display") or str(get_size(it) or "")
            def get_ext(it):
                return (it.get("Ext") or it.get("ext") or "").lower()

            # build index of right items for matching
            right_set = set((get_name(it).lower(), get_size(it), get_ext(it)) for it in right_items)
            left_set = set((get_name(it).lower(), get_size(it), get_ext(it)) for it in left_items)

            # populate left tree
            for iid in self.compare_tree_left.get_children():
                self.compare_tree_left.delete(iid)
            for it in left_items:
                name = get_name(it)
                size_disp = get_size_display(it)
                ext = get_ext(it)
                tag = ()
                key = (name.lower(), get_size(it), ext)
                tags = ("match",) if key in right_set else ()
                self.compare_tree_left.insert("", "end", values=(name, size_disp, ext), tags=tags)

            # populate right tree
            for iid in self.compare_tree_right.get_children():
                self.compare_tree_right.delete(iid)
            for it in right_items:
                name = get_name(it)
                size_disp = get_size_display(it)
                ext = get_ext(it)
                key = (name.lower(), get_size(it), ext)
                tags = ("match",) if key in left_set else ()
                self.compare_tree_right.insert("", "end", values=(name, size_disp, ext), tags=tags)

            # populate summary tree
            for r in summary:
                tag = ()
                if r.get("status") == "both_same":
                    tag = ("both_same",)
                self.compare_tree.insert("", "end", values=(r.get("file"), r.get("category"), r.get("status"), r.get("left_size",""), r.get("right_size","")), tags=tag)

        self.master.after(10, task)

    def sort_compare_tree(self, side, by):
        """
        Sort left/right compare lists by Name/Size/Ext.
        """
        # choose the list
        if side == "left":
            items = list(self.last_compare_left)
            tree = self.compare_tree_left
        else:
            items = list(self.last_compare_right)
            tree = self.compare_tree_right

        # helper field getter
        def get_name(it):
            return (it.get("Name") or it.get("name") or "").lower()
        def get_size(it):
            return it.get("Size") if it.get("Size") is not None else it.get("size") or 0
        def get_ext(it):
            return (it.get("Ext") or it.get("ext") or "").lower()

        if by == "Name":
            items.sort(key=lambda x: get_name(x))
        elif by == "Size":
            items.sort(key=lambda x: (get_size(x) if get_size(x) is not None else float('inf'), get_name(x)))
        elif by == "Ext":
            items.sort(key=lambda x: (get_ext(x), get_name(x)))

        # update the stored list and refresh display
        if side == "left":
            self.last_compare_left = items
        else:
            self.last_compare_right = items

        # repopulate using populate_compare with current data
        data = {"left": self.last_compare_left, "right": self.last_compare_right, "results": self.last_compare}
        self.populate_compare(data)

    def export_compare(self):
        if not self.last_compare:
            messagebox.showinfo("No compare", "Please perform a compare first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv"),("TXT","*.txt")])
        if not path: return
        try:
            with open(path,"w",encoding="utf-8") as f:
                f.write("file,category,status,left_size,right_size\n")
                for r in self.last_compare:
                    f.write(f"{r.get('file')},{r.get('category')},{r.get('status')},{r.get('left_size','')},{r.get('right_size','')}\n")
            messagebox.showinfo("Exported", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = MediaScannerApp(root)
    root.mainloop()
