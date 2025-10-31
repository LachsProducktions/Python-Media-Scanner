"""
compare.py - comparison utilities.

Provides:
 - compare_folders(folder_a, folder_b, include_hash=False)
 - compare_scanfile_vs_folder(scanfile, folder, include_hash=False)
 - compare_scanfiles(file_a, file_b)

Comparison result: list of dicts:
  file, category, status ('only_left','only_right','both_same','both_differ'), left_size, right_size
"""
import os
import json
from pathlib import Path
from scanner import Scanner

def _index_items(items):
    # create dict keyed by relative name or path basename; using basename to catch duplicates on different folders
    idx = {}
    for it in items:
        key = it["name"]  # using name for comparison; could be improved using relative path
        idx.setdefault(key, []).append(it)
    return idx

class Compare:
    def __init__(self):
        pass

    def compare_folders(self, folder_a, folder_b, include_hash=False):
        s = Scanner(include_hash=include_hash)
        left = s.scan_folder(folder_a, update_callback=None)
        right = s.scan_folder(folder_b, update_callback=None)
        return self._compare_lists(left, right)

    def compare_scanfile_vs_folder(self, scanfile, folder, include_hash=False):
        left = self._load_scanfile(scanfile)
        s = Scanner(include_hash=include_hash)
        right = s.scan_folder(folder, update_callback=None)
        return self._compare_lists(left, right)

    def compare_scanfiles(self, file_a, file_b):
        a = self._load_scanfile(file_a)
        b = self._load_scanfile(file_b)
        return self._compare_lists(a, b)

    def _load_scanfile(self, path):
        p = Path(path)
        if p.suffix.lower() == ".txt" or p.suffix.lower() == ".json":
            with open(p,"r",encoding="utf-8") as f:
                data = json.load(f)
            # data expected to be a list of items
            return data
        else:
            # try to parse simple txt/tab format
            items = []
            with open(p,"r",encoding="utf-8") as f:
                lines = f.readlines()
            for ln in lines:
                parts = ln.strip().split("\t")
                if len(parts) >= 3:
                    name = parts[0]; full = parts[1]; size = parts[2]
                    items.append({"name": name, "path": full, "size_display": size, "ext": Path(full).suffix.lower(), "category": "Other"})
            return items

    def _compare_lists(self, left, right):
        li = _index_items(left)
        ri = _index_items(right)
        all_keys = set(li.keys()) | set(ri.keys())
        results = []
        for k in sorted(all_keys):
            left_items = li.get(k, [])
            right_items = ri.get(k, [])
            # Basic matching: if same name present in both
            if left_items and right_items:
                # compare sizes (first entry chosen if multiple)
                lsz = left_items[0].get("size", None)
                rsz = right_items[0].get("size", None)
                if lsz == rsz:
                    status = "both_same"
                else:
                    status = "both_differ"
                results.append({
                    "file": k,
                    "category": left_items[0].get("category", right_items[0].get("category","")),
                    "status": status,
                    "left_size": lsz,
                    "right_size": rsz
                })
            elif left_items:
                results.append({
                    "file": k,
                    "category": left_items[0].get("category",""),
                    "status": "only_left",
                    "left_size": left_items[0].get("size"),
                    "right_size": ""
                })
            else:
                results.append({
                    "file": k,
                    "category": right_items[0].get("category",""),
                    "status": "only_right",
                    "left_size": "",
                    "right_size": right_items[0].get("size")
                })
        return results
