#!/usr/bin/env python3
"""
Upload SlimeHive recordings to GitHub Releases.

Usage:
    python publish_recording.py recordings/sim_*.slimehive
    python publish_recording.py --list
"""

import argparse
import subprocess
import sys
import os

RELEASE_TAG = "recordings"

def ensure_release_exists():
    """Create recordings release if it doesn't exist"""
    result = subprocess.run(
        ["gh", "release", "view", RELEASE_TAG],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"Creating release: {RELEASE_TAG}")
        subprocess.run([
            "gh", "release", "create", RELEASE_TAG,
            "--title", "SlimeHive Recordings",
            "--notes", "Recorded simulations for the online viewer"
        ], check=True)

def upload(filepath):
    """Upload a recording file"""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        return False

    ensure_release_exists()

    print(f"Uploading: {filepath}")
    result = subprocess.run([
        "gh", "release", "upload", RELEASE_TAG, filepath,
        "--clobber"
    ])

    if result.returncode == 0:
        print(f"Success! View recordings at viewer URL")
        return True
    return False

def list_recordings():
    """List uploaded recordings"""
    result = subprocess.run(
        ["gh", "release", "view", RELEASE_TAG, "--json", "assets"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("No recordings release found")
        return

    import json
    data = json.loads(result.stdout)
    assets = [a for a in data.get("assets", []) if a["name"].endswith(".slimehive")]

    if not assets:
        print("No recordings uploaded yet")
        return

    print(f"Recordings ({len(assets)}):")
    for a in assets:
        print(f"  {a['name']}")

def main():
    parser = argparse.ArgumentParser(
        description="Upload SlimeHive recordings to GitHub Releases"
    )
    parser.add_argument("files", nargs="*", help="Recording files to upload")
    parser.add_argument("--list", action="store_true", help="List uploaded recordings")
    args = parser.parse_args()

    if args.list:
        list_recordings()
    elif args.files:
        for f in args.files:
            upload(f)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
