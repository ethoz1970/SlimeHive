#!/usr/bin/env python3
"""
Publish SlimeHive recordings for the online viewer.

Usage:
    python publish_recording.py recordings/sim_*.slimehive     # Copy to docs/viewer/recordings
    python publish_recording.py --list                          # List published recordings
    python publish_recording.py --clean                         # Remove all published recordings
"""

import argparse
import shutil
import json
import os
import re
from datetime import datetime

VIEWER_RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), 'docs', 'viewer', 'recordings')
INDEX_FILE = os.path.join(VIEWER_RECORDINGS_DIR, 'index.json')


def ensure_dir():
    """Ensure recordings directory exists"""
    os.makedirs(VIEWER_RECORDINGS_DIR, exist_ok=True)


def load_index():
    """Load existing index or return empty list"""
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r') as f:
            return json.load(f)
    return []


def save_index(recordings):
    """Save index file"""
    with open(INDEX_FILE, 'w') as f:
        json.dump(recordings, f, indent=2)


def parse_recording_date(filename):
    """Extract date from recording filename"""
    # Pattern: sim_MODE_Ndrones_YYYY-MM-DD_HHMMSS.slimehive
    match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{6})', filename)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        try:
            dt = datetime.strptime(f"{date_str}_{time_str}", "%Y-%m-%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
    return ""


def publish(filepath):
    """Copy a recording to the viewer directory"""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        return False

    ensure_dir()
    filename = os.path.basename(filepath)
    dest = os.path.join(VIEWER_RECORDINGS_DIR, filename)

    # Copy file
    shutil.copy2(filepath, dest)
    print(f"Published: {filename}")

    # Update index
    recordings = load_index()

    # Remove existing entry with same name
    recordings = [r for r in recordings if r['name'] != filename]

    # Add new entry
    recordings.append({
        'name': filename,
        'date': parse_recording_date(filename),
        'size': os.path.getsize(dest)
    })

    # Sort by date descending
    recordings.sort(key=lambda r: r['date'], reverse=True)
    save_index(recordings)

    return True


def list_recordings():
    """List published recordings"""
    recordings = load_index()

    if not recordings:
        print("No recordings published yet")
        print(f"Run: python publish_recording.py recordings/*.slimehive")
        return

    print(f"Published recordings ({len(recordings)}):")
    for r in recordings:
        size_kb = r.get('size', 0) // 1024
        print(f"  {r['name']} ({size_kb}KB) - {r.get('date', 'unknown')}")


def clean():
    """Remove all published recordings"""
    if os.path.exists(VIEWER_RECORDINGS_DIR):
        for f in os.listdir(VIEWER_RECORDINGS_DIR):
            os.remove(os.path.join(VIEWER_RECORDINGS_DIR, f))
        print("Cleaned all published recordings")
    else:
        print("Nothing to clean")


def main():
    parser = argparse.ArgumentParser(
        description="Publish SlimeHive recordings for online viewer"
    )
    parser.add_argument("files", nargs="*", help="Recording files to publish")
    parser.add_argument("--list", action="store_true", help="List published recordings")
    parser.add_argument("--clean", action="store_true", help="Remove all published recordings")
    args = parser.parse_args()

    if args.clean:
        clean()
    elif args.list:
        list_recordings()
    elif args.files:
        for f in args.files:
            publish(f)
        print(f"\nRecordings ready at: docs/viewer/recordings/")
        print("Commit and push to deploy to GitHub Pages")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
