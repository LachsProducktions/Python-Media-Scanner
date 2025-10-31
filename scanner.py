"""
scanner.py - scanning and categorization logic

Provides Scanner.scan_folder(folder, update_callback=None, include_hash=False).
Returns list of items with fields:
  name, path, size (bytes), size_display, ext, category, duration (seconds or None), duration_display, hash (optional)
"""
import os
import subprocess
from pathlib import Path
import time
import json
import hashlib

# Optional libs
try:
    from pymediainfo import MediaInfo
except Exception:
    MediaInfo = None

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

# Extensive extension lists
VIDEO_EXTS = {'.mp4','.mkv','.avi','.mov','.flv','.wmv','.webm','.ts','.m2ts','.vob','.mpeg','.mpg','.ogv','.3gp','.f4v','.mxf','.hevc','.h264','.h265'}
AUDIO_EXTS = {'.mp3','.wav','.flac','.aac','.m4a','.ogg','.opus','.wma','.aiff','.alac','.mid','.midi','.amr','.ape','.ra','.rm'}
IMAGE_EXTS = {'.jpg','.jpeg','.png','.bmp','.gif','.tiff','.tif','.heic','.webp','.raw','.cr2','.nef','.orf','.arw','.dng','.psd','.svg'}

ALL_KNOWN = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS

def sizeof_fmt(num, suffix="B"):
    for unit in ['','Ki','Mi','Gi','Ti']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Pi{suffix}"

def run_ffprobe_duration(path):
    try:
        result = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1', str(path)],
                                capture_output=True, text=True, timeout=15)
        out = result.stdout.strip()
        if out:
            return float(out)
    except Exception:
        return None
    return None

def pymediainfo_duration(path):
    if MediaInfo is None:
        return None
    try:
        mi = MediaInfo.parse(path)
        for t in mi.tracks:
            if getattr(t, "duration", None):
                return float(t.duration)/1000.0
    except Exception:
        return None
    return None

def mutagen_duration(path):
    if MutagenFile is None:
        return None
    try:
        m = MutagenFile(path)
        if m and getattr(m, "info", None):
            return getattr(m.info,"length", None)
    except Exception:
        return None
    return None

def get_duration(path):
    d = run_ffprobe_duration(path)
    if d:
        return d
    d = pymediainfo_duration(path)
    if d:
        return d
    d = mutagen_duration(path)
    if d:
        return d
    return None

def sha256_of_file(path, block_size=65536):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()

class Scanner:
    def __init__(self, include_hash=False):
        self.include_hash = include_hash

    def scan_folder(self, root_path, update_callback=None):
        """
        Scans folder recursively and returns list of item dicts.
        Calls update_callback(progress, current_file) with progress from 0–100.
        """
        items = []
        root = Path(root_path)

        # Collect all files first for total count
        all_files = []
        for dirpath, _, files in os.walk(root):
            for fname in files:
                all_files.append(Path(dirpath) / fname)

        total = len(all_files)
        if total == 0:
            return []

        for count, full in enumerate(all_files, start=1):
            try:
                ext = full.suffix.lower()
                size = full.stat().st_size
                category = self._categorize_by_ext(ext)
                duration = None
                duration_display = "N/A"

                if ext in VIDEO_EXTS or ext in AUDIO_EXTS:
                    try:
                        duration = get_duration(full)
                        duration_display = self._fmt_duration(duration)
                    except Exception:
                        duration = None
                        duration_display = "Error"

                size_display = sizeof_fmt(size)
                hval = sha256_of_file(full) if self.include_hash else None

                item = {
                    "name": full.name,
                    "path": str(full),
                    "size": size,
                    "size_display": size_display,
                    "ext": ext,
                    "category": category,
                    "duration": duration,
                    "duration_display": duration_display,
                }
                if self.include_hash:
                    item["sha256"] = hval

                items.append(item)
            except Exception as e:
                print(f"Error scanning {full}: {e}")
            finally:
                if update_callback:
                    progress = int((count / total) * 100)
                    update_callback(progress, str(full))

        return items
    
    def sort_items(self, items, by="name"):
        """
        Sorts scanned items by name, size, duration, or extension.
        Ties are broken alphabetically by name.
        """
        key_funcs = {
            "name": lambda x: (x["name"].lower(),),
            "size": lambda x: (x["size"], x["name"].lower()),
            "duration": lambda x: (
                x["duration"] if x["duration"] is not None else float("inf"),
                x["name"].lower(),
            ),
            "ext": lambda x: (x["ext"], x["name"].lower()),
        }

        key_func = key_funcs.get(by, key_funcs["name"])
        return sorted(items, key=key_func)



    def _categorize_by_ext(self, ext):
        if ext in VIDEO_EXTS:
            return "Videos"
        if ext in AUDIO_EXTS:
            return "Musik"
        if ext in IMAGE_EXTS:
            return "Fotos"
        return "Other"

    def _fmt_duration(self, seconds):
        if not seconds:
            return "N/A"
        minutes, sec = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"


    def _categorize_by_ext(self, ext):
        if ext in VIDEO_EXTS:
            return "Videos"
        if ext in AUDIO_EXTS:
            return "Musik"
        if ext in IMAGE_EXTS:
            return "Fotos"
        return "Other"

# If run directly, quick scan demo
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--hash", action="store_true")
    args = ap.parse_args()
    s = Scanner(include_hash=args.hash)
    res = s.scan_folder(args.root, update_callback=lambda c,p: print(c,p))
    print(f"Found {len(res)} files")
