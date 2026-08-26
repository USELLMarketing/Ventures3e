"""
Parses the Ventures Arcade Audio React bundle (a minified createElement dump)
into a structured catalog.

The bundle has no separate data file - every audio link is baked in as
    href:"<url>",download:!0},"<label>")
so we regex those out directly, then derive (level, catalog, unit) purely
from the filename, since Cambridge's own naming convention encodes them
reliably (confirmed against the live rendered tabs):

    SB_Basic_...                    -> Basic / Student's Book Audio
    SB1_.. / SB2_.. / SB3_.. / SB4_..-> Level 1-4 / Student's Book Audio
    WB_Basic_...                    -> Basic / Workbook Audio
    WB1_.. / WB2_.. / WB3_.. / WB4_..-> Level 1-4 / Workbook Audio
    WB_Basic_Literacy_...            -> Basic / Literacy Workbook Audio
    Transitions3e_SB_...             -> Transitions / Student's Book Audio
    WB_Transitions_...                -> Transitions / Workbook Audio
    SB_Transitions_... (no "3e")     -> Transitions (2nd Edition) / Student's Book Audio

Usage:
    python extract_catalog.py source_bundle_main.js ../data/catalog.json
"""
import json
import re
import sys
from collections import OrderedDict

LINK_RE = re.compile(r'href:"([^"]+\.mp3)",download:!0\},"([^"]*)"\)')


def derive_unit(stem: str) -> str:
    m = re.search(r'Review[_ ]Units?_(\d+)_and_(\d+)', stem, re.I)
    if m:
        return f"Review: Units {m.group(1)} and {m.group(2)}"
    m = re.search(r'Welcome', stem, re.I)
    if m:
        return "Welcome Unit"
    m = re.search(r'Unit_?0*([0-9]+)', stem, re.I)
    if m:
        return f"Unit {int(m.group(1))}"
    return "Other"


def derive_level_catalog(filename: str, url: str):
    if filename.startswith("Transitions3e_SB"):
        return "Transitions", "Student's Book Audio"
    if filename.startswith("WB_Transitions"):
        # The bundle also contains a dead-code duplicate set of
        # WB_Transitions_* filenames hosted on the (dead) cambridge.org
        # domain, using an older page-numbering scheme. That set is not
        # reachable from any tab on the live site - only the CloudFront-
        # hosted set (matching what actually renders under Transitions >
        # Workbook Audio) is real. Skip the unreachable duplicate.
        if "cloudfront.net" not in url:
            return "SKIP", "SKIP"
        return "Transitions", "Workbook Audio"
    if filename.startswith("SB_Transitions"):
        # Bare "SB_Transitions_*" (no "3e") is the 2nd-Edition Student's
        # Book audio. It's not rendered inline anywhere in this 3rd-edition
        # site - it's only referenced via the external "Looking for the
        # Transitions 2nd Edition audio?" link - so it isn't part of what
        # this site actually shows. Skip it.
        return "SKIP", "SKIP"
    if filename.startswith("WB_Basic_Literacy"):
        return "Basic", "Literacy Workbook Audio"
    if filename.startswith("SB_Basic"):
        return "Basic", "Student's Book Audio"
    if filename.startswith("WB_Basic"):
        return "Basic", "Workbook Audio"
    m = re.match(r'^SB([1-4])_', filename)
    if m:
        return f"Level {m.group(1)}", "Student's Book Audio"
    m = re.match(r'^WB([1-4])_', filename)
    if m:
        return f"Level {m.group(1)}", "Workbook Audio"
    return "Unknown", "Unknown"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "source_bundle_main.js"
    out = sys.argv[2] if len(sys.argv) > 2 else "../data/catalog.json"

    data = open(src, encoding="utf-8").read()
    matches = LINK_RE.findall(data)

    seen_urls = set()
    # levels[level][catalog][unit] = [ {label, filename, originalUrl}, ... ]
    levels = OrderedDict()
    unknown = []

    for url, label in matches:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        label = label.strip()
        filename = url.rsplit("/", 1)[-1]
        level, catalog = derive_level_catalog(filename, url)
        if level == "SKIP":
            continue
        if level == "Unknown":
            unknown.append(filename)
            continue
        unit = derive_unit(filename)

        levels.setdefault(level, OrderedDict())
        levels[level].setdefault(catalog, OrderedDict())
        levels[level][catalog].setdefault(unit, [])
        levels[level][catalog][unit].append({
            "label": label,
            "filename": filename,
            "originalUrl": url,
        })

    result = []
    for level, catalogs in levels.items():
        level_entry = {"level": level, "catalogs": []}
        for catalog, units in catalogs.items():
            catalog_entry = {"catalog": catalog, "units": []}
            for unit, items in units.items():
                catalog_entry["units"].append({"unit": unit, "items": items})
            level_entry["catalogs"].append(catalog_entry)
        result.append(level_entry)

    total_items = sum(
        len(u["items"])
        for lvl in result
        for cat in lvl["catalogs"]
        for u in cat["units"]
    )

    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Parsed {len(matches)} raw link matches, {len(seen_urls)} unique URLs.")
    print(f"Wrote {total_items} items into {len(result)} levels -> {out}")
    if unknown:
        print(f"WARNING: {len(unknown)} filenames didn't match any known pattern:")
        for fn in unknown[:20]:
            print("  ", fn)


if __name__ == "__main__":
    main()
