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

def _normalize_name(name):
    """Remove resolution markers and normalize name for comparison"""
    # List of common resolution markers to remove
    res_markers = ['720p', '1080p', '2160p', '4k', 'uhd', '480p', 'hdtv', 'fullhd', 'hd']
    name = name.lower()
    # Remove resolution markers
    for marker in res_markers:
        name = name.replace(marker, '')
    # Clean up any leftover dots, spaces, or brackets that might be artifacts
    name = name.replace('.', ' ').replace('[', ' ').replace(']', ' ')
    name = ' '.join(name.split())  # normalize spaces
    return name

def _index_items(items):
    # create dict keyed by normalized name to catch same content in different qualities
    idx = {}
    for it in items:
        # Use pre-normalized name or try both cases
        name = it.get("name") or it.get("Name") or ""
        if not name:
            continue
            
        # Use normalized name as key for comparison
        key = _normalize_name(name)
        
        # Group items with same normalized name
        idx.setdefault(key, []).append(it)
    return idx

class Compare:
    def __init__(self):
        pass

    def compare_folders(self, folder_a, folder_b, include_hash=False, update_callback=None):
        s = Scanner(include_hash=include_hash)
        if update_callback:
            update_callback(0, f"Scanning folder: {folder_a}")
        left = s.scan_folder(folder_a, lambda p,f: update_callback(p//2, f) if update_callback else None)

        if update_callback:
            update_callback(50, f"Scanning folder: {folder_b}")
        right = s.scan_folder(folder_b, lambda p,f: update_callback(50 + p//2, f) if update_callback else None)

        if update_callback:
            update_callback(100, "Comparing results...")

        results = self._compare_lists(left, right)
        return {"left": left, "right": right, "results": results}

    def compare_scanfile_vs_folder(self, scanfile, folder, include_hash=False, update_callback=None):
        if update_callback:
            update_callback(0, f"Loading scan file: {scanfile}")
        left = self._load_scanfile(scanfile)

        if update_callback:
            update_callback(20, f"Scanning folder: {folder}")
        s = Scanner(include_hash=include_hash)
        right = s.scan_folder(folder, lambda p,f: update_callback(20 + int(p*0.8), f) if update_callback else None)

        if update_callback:
            update_callback(100, "Comparing results...")

        results = self._compare_lists(left, right)
        return {"left": left, "right": right, "results": results}

    def compare_scanfiles(self, file_a, file_b):
        a = self._load_scanfile(file_a)
        b = self._load_scanfile(file_b)
        return self._compare_lists(a, b)

    def _load_scanfile(self, path):
        p = Path(path)
        items = []
        
        try:
            # First try to load as JSON
            if p.suffix.lower() == ".json":
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            
            # If not JSON or not a list, try tab-delimited format
            with open(p, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
                
                # Check if file is empty
                if not lines:
                    return []
                
                # Determine if first line is header
                first_line = lines[0].lower()
                has_header = "name" in first_line and "path" in first_line
                
                # Skip header if present
                if has_header:
                    lines = lines[1:]
                
                # Process remaining lines
                for ln in lines:
                    parts = ln.split("\t")
                    if not ln.strip():  # Skip empty lines
                        continue
                        
                    if len(parts) >= 2:  # At least name and path
                        name = parts[0].strip()
                        path = parts[1].strip()
                        size = parts[2].strip() if len(parts) > 2 else "N/A"
                        ext = Path(name).suffix.lower() if name else ""
                        
                        items.append({
                            "name": name,
                            "path": path,
                            "size_display": size,
                            "ext": ext,
                            "category": "Other"
                        })
                    else:  # Single column format
                        name = parts[0].strip()
                        if name:
                            ext = Path(name).suffix.lower()
                            items.append({
                                "name": name,
                                "path": name,
                                "size_display": "N/A",
                                "ext": ext,
                                "category": "Other"
                            })
            
            return items
            
        except Exception as e:
            print(f"Error loading scan file: {str(e)}")
            return []  # Return empty list instead of raising error

    def _normalize_item(self, item):
        """Normalize item fields to consistent lowercase keys."""
        # Capture numeric size when available, and keep the user-friendly size display
        size_val = None
        raw_size = None
        if "Size" in item:
            raw_size = item.get("Size")
        elif "size" in item:
            raw_size = item.get("size")

        if raw_size is not None:
            # If it's already numeric, keep it. If it's a numeric string, try to convert.
            if isinstance(raw_size, (int, float)):
                size_val = int(raw_size)
            else:
                try:
                    size_val = int(raw_size)
                except Exception:
                    # could be human-friendly string like '1.5 GB' - leave numeric size as None
                    size_val = None

        size_display = (
            item.get("Size_Display") or 
            item.get("size_display") or 
            (str(size_val) if size_val is not None else "")
        )

        return {
            "name": item.get("Name") or item.get("name") or "",
            "path": item.get("Path") or item.get("path") or "",
            "size": size_val,
            "size_display": size_display,
            "duration_display": item.get("Duration_Display") or item.get("duration_display") or "N/A",
            "ext": (item.get("Ext") or item.get("ext") or "").lower(),
            "category": item.get("Category") or item.get("category") or "Other"
        }

    def _items_match(self, left, right):
        """Compare two items to determine if they match."""
        # Prefer numeric size comparison when both sides provide it
        lsize = left.get("size")
        rsize = right.get("size")
        if isinstance(lsize, (int, float)) and isinstance(rsize, (int, float)):
            return int(lsize) == int(rsize)

        # Fallback: compare the human-friendly size display if both exist
        ldisp = (left.get("size_display") or "").lower().replace(" ", "").replace(",", "")
        rdisp = (right.get("size_display") or "").lower().replace(" ", "").replace(",", "")
        if ldisp and rdisp:
            return ldisp == rdisp

        # Final fallback: compare normalized names
        left_name = _normalize_name(left["name"])
        right_name = _normalize_name(right["name"])
        return left_name == right_name

    def _compare_lists(self, left, right):
        # Normalize all items first
        left = [self._normalize_item(item) for item in left]
        right = [self._normalize_item(item) for item in right]
        
        # Index items by normalized name
        li = _index_items(left)
        ri = _index_items(right)
        all_keys = set(li.keys()) | set(ri.keys())
        
        results = []
        for k in sorted(all_keys):
            left_items = li.get(k, [])
            right_items = ri.get(k, [])
            
            if left_items and right_items:
                # Get first item from each side
                left_item = left_items[0]
                right_item = right_items[0]
                
                # Compare items
                # Always consider items with same normalized name as matches
                status = "both_same"
                    
                results.append({
                    "file": k,
                    "category": left_item["category"],
                    "status": status,
                    "left_size": left_item.get("size_display", ""),
                    "right_size": right_item.get("size_display", "")
                })
            elif left_items:
                left_item = left_items[0]
                results.append({
                    "file": k,
                    "category": left_item["category"],
                    "status": "only_left",
                    "left_size": left_item.get("size_display") or left_item.get("size", ""),
                    "right_size": ""
                })
            else:
                right_item = right_items[0]
                results.append({
                    "file": k,
                    "category": right_item["category"],
                    "status": "only_right",
                    "left_size": "",
                    "right_size": right_item.get("size_display") or right_item.get("size", "")
                })
        
        return results
