"""
Walks the "Ventures 3e Audio" folder in the Cambridge/CUPA Dropbox Business
team space, matches every audio file against data/catalog.json (by
filename), builds a video catalog from the "Grammar Videos" folders (no
pre-existing catalog for those - built straight from what's on disk), and
writes/updates data/links.json with a direct-streamable URL for every
matched file.

Requires DROPBOX_ACCESS_TOKEN in a local .env (see tools/.env, gitignored).
The token's account must have access to the CUPA US team space.

Usage:
    python build_links_from_dropbox.py
"""
import json
import os
import re
import sys
import time

import requests

ROOT_FOLDER = "/Ventures 3e Audio"
LEVEL_FOLDERS = ["Basic", "Level 1", "Level 2", "Level 3", "Level 4", "Transitions"]
VIDEO_LEVEL_NUM = {"0": "Basic", "1": "Level 1", "2": "Level 2", "3": "Level 3", "4": "Level 4", "5": "Transitions"}

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)


def load_env():
    env_path = os.path.join(PROJECT_ROOT, ".env")
    token = None
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            if line.startswith("DROPBOX_ACCESS_TOKEN="):
                token = line.strip().split("=", 1)[1]
    if not token:
        sys.exit("DROPBOX_ACCESS_TOKEN not found in .env")
    return token


def dbx_headers(token, root_namespace_id):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Dropbox-API-Path-Root": json.dumps({".tag": "root", "root": root_namespace_id}),
    }


def get_root_namespace_id(token):
    r = requests.post(
        "https://api.dropboxapi.com/2/users/get_current_account",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()["root_info"]["root_namespace_id"]


def list_folder_recursive(headers, path):
    entries = []
    r = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers=headers,
        json={"path": path, "recursive": True},
    )
    r.raise_for_status()
    data = r.json()
    entries.extend(data["entries"])
    while data.get("has_more"):
        r = requests.post(
            "https://api.dropboxapi.com/2/files/list_folder/continue",
            headers=headers,
            json={"cursor": data["cursor"]},
        )
        r.raise_for_status()
        data = r.json()
        entries.extend(data["entries"])
    return [e for e in entries if e[".tag"] == "file"]


def get_or_create_shared_link(headers, path):
    r = requests.post(
        "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
        headers=headers,
        json={"path": path},
    )
    if r.status_code == 200:
        return r.json()["url"]
    if r.status_code == 409:
        err = r.json().get("error", {})
        if err.get(".tag") == "shared_link_already_exists":
            existing = err.get("shared_link_already_exists", {}).get("metadata", {})
            if existing.get("url"):
                return existing["url"]
        # fall back to listing links for this path
        r2 = requests.post(
            "https://api.dropboxapi.com/2/sharing/list_shared_links",
            headers=headers,
            json={"path": path, "direct_only": True},
        )
        r2.raise_for_status()
        links = r2.json().get("links", [])
        if links:
            return links[0]["url"]
    raise RuntimeError(f"Could not get shared link for {path}: {r.status_code} {r.text}")


def to_direct_url(share_url):
    # Dropbox share pages (dl=0) render a preview page; raw=1 streams the
    # actual file content, which is what <audio>/<video> src needs.
    if "dl=0" in share_url:
        return share_url.replace("dl=0", "raw=1")
    sep = "&" if "?" in share_url else "?"
    return f"{share_url}{sep}raw=1"


def derive_video_unit_lesson(filename):
    m = re.match(r"Ventures3e_Level(\d)_Unit(\d+)_Lesson([A-Z])_GrammarPres\.mp4", filename)
    if not m:
        return None
    level_num, unit_num, lesson = m.groups()
    level = VIDEO_LEVEL_NUM.get(level_num)
    if not level:
        return None
    return level, f"Unit {int(unit_num)}", lesson


def build_video_catalog(video_files):
    # level -> unit -> [items]
    levels = {}
    for path in video_files:
        filename = path.rsplit("/", 1)[-1]
        parsed = derive_video_unit_lesson(filename)
        if not parsed:
            print("WARNING: unrecognized video filename:", filename)
            continue
        level, unit, lesson = parsed
        levels.setdefault(level, {})
        levels[level].setdefault(unit, [])
        levels[level][unit].append({
            "label": f"Lesson {lesson} Grammar Video",
            "filename": filename,
        })

    result = []
    for level in LEVEL_FOLDERS:
        if level not in levels:
            continue
        units = levels[level]

        def unit_key(u):
            return int(re.search(r"\d+", u).group())

        unit_list = [
            {"unit": u, "items": sorted(units[u], key=lambda i: i["label"])}
            for u in sorted(units.keys(), key=unit_key)
        ]
        result.append({"level": level, "units": unit_list})
    return result


def main():
    token = load_env()
    root_ns = get_root_namespace_id(token)
    headers = dbx_headers(token, root_ns)

    print("Listing Dropbox files...")
    all_files = list_folder_recursive(headers, ROOT_FOLDER)
    print(f"Found {len(all_files)} files total under {ROOT_FOLDER}")

    audio_files = [f for f in all_files if f["name"].lower().endswith(".mp3")]
    video_files = [f for f in all_files if f["name"].lower().endswith(".mp4")]
    print(f"  {len(audio_files)} audio files, {len(video_files)} video files")

    catalog_path = os.path.join(PROJECT_ROOT, "data", "catalog.json")
    catalog = json.load(open(catalog_path, encoding="utf-8"))
    known_filenames = set()
    for lvl in catalog:
        for cat in lvl["catalogs"]:
            for u in cat["units"]:
                for item in u["items"]:
                    known_filenames.add(item["filename"])

    links_path = os.path.join(PROJECT_ROOT, "data", "links.json")
    links = json.load(open(links_path, encoding="utf-8")) if os.path.exists(links_path) else {}

    matched_audio = [f for f in audio_files if f["name"] in known_filenames]
    unmatched_audio = [f for f in audio_files if f["name"] not in known_filenames]
    print(f"  {len(matched_audio)} audio files matched the catalog, {len(unmatched_audio)} did not")
    for f in unmatched_audio[:10]:
        print("    unmatched:", f["path_display"])

    to_link = matched_audio + video_files
    print(f"Requesting shared links for {len(to_link)} files (this can take a few minutes)...")
    failures = []
    for i, f in enumerate(to_link, 1):
        if f["name"] in links:
            continue
        try:
            share_url = get_or_create_shared_link(headers, f["path_lower"])
            links[f["name"]] = to_direct_url(share_url)
        except Exception as e:
            failures.append((f["path_display"], str(e)))
        if i % 25 == 0:
            print(f"  {i}/{len(to_link)}...")
            json.dump(links, open(links_path, "w", encoding="utf-8"), indent=2)

    json.dump(links, open(links_path, "w", encoding="utf-8"), indent=2)
    print(f"Wrote {len(links)} total links -> {links_path}")

    if failures:
        print(f"{len(failures)} files failed to get a shared link:")
        for path, err in failures[:10]:
            print("  ", path, "->", err)

    video_catalog = build_video_catalog([f["path_display"] for f in video_files])
    video_catalog_path = os.path.join(PROJECT_ROOT, "data", "video_catalog.json")
    json.dump(video_catalog, open(video_catalog_path, "w", encoding="utf-8"), indent=2)
    total_videos = sum(len(u["items"]) for lvl in video_catalog for u in lvl["units"])
    print(f"Wrote {total_videos} video items -> {video_catalog_path}")


if __name__ == "__main__":
    main()
