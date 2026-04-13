"""Build and query plant-scoped OPC tag indexes.

This module intentionally has no dependency on the RiMS project.  It reads the
large ``tags.CSV`` exported from that project and creates small per-prefix JSONL
indexes that the preprocessing portal/local backend can ship and query quickly.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

DEFAULT_PREFIXES = ("PJ1", "PJ2", "KY", "HN", "WR", "YJ")
DEFAULT_FIELDS = (
    "fulltagname",
    "plant",
    "sourcename",
    "tagname",
    "utagid",
    "description",
    "units",
)


@dataclass(frozen=True)
class TagIndexEntry:
    """Compact tag metadata needed for search and OPC NodeId lookup."""

    fulltagname: str
    plant: str
    sourcename: str
    tagname: str
    utagid: int
    description: str = ""
    units: str = ""

    @property
    def search_text(self) -> str:
        return " ".join(
            [self.fulltagname, self.tagname, self.description, self.units]
        ).lower()


def _read_csv_rows(tags_csv: Path) -> Iterator[dict[str, str]]:
    """Read tags.CSV robustly enough for mixed Korean/legacy encodings."""
    # The observed RiMS tags.CSV includes bytes that are not valid UTF-8.  Using
    # replacement keeps index generation deterministic and preserves ASCII tag
    # names/utagid, which are the fields required for OPC lookup.
    with tags_csv.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}


def _prefix_of(row: dict[str, str]) -> str:
    fulltagname = row.get("fulltagname", "").strip()
    if fulltagname:
        return fulltagname.split(".", 1)[0].upper()
    return row.get("plant", "").strip().upper()


def _entry_from_row(row: dict[str, str]) -> TagIndexEntry | None:
    fulltagname = row.get("fulltagname", "").strip()
    utagid_raw = row.get("utagid", "").strip()
    if not fulltagname or not utagid_raw:
        return None
    try:
        utagid = int(float(utagid_raw))
    except ValueError:
        return None
    return TagIndexEntry(
        fulltagname=fulltagname,
        plant=row.get("plant", "").strip().upper(),
        sourcename=row.get("sourcename", "").strip(),
        tagname=row.get("tagname", "").strip(),
        utagid=utagid,
        description=row.get("description", "").strip(),
        units=row.get("units", "").strip(),
    )


def build_tag_indexes(
    tags_csv: str | Path,
    output_dir: str | Path,
    prefixes: Iterable[str] = DEFAULT_PREFIXES,
) -> dict[str, int]:
    """Build one JSONL index per prefix and return row counts."""
    tags_csv_path = Path(tags_csv)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    normalized_prefixes = tuple(prefix.upper() for prefix in prefixes)
    handles = {
        prefix: (output_path / f"{prefix}.jsonl").open("w", encoding="utf-8")
        for prefix in normalized_prefixes
    }
    counts = dict.fromkeys(normalized_prefixes, 0)
    try:
        for row in _read_csv_rows(tags_csv_path):
            prefix = _prefix_of(row)
            if prefix not in handles:
                continue
            entry = _entry_from_row(row)
            if entry is None:
                continue
            handles[prefix].write(
                json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
            counts[prefix] += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "source": str(tags_csv_path),
        "format": "jsonl",
        "prefixes": counts,
        "fields": list(DEFAULT_FIELDS),
    }
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return counts


def load_entries(index_dir: str | Path, prefix: str) -> list[TagIndexEntry]:
    """Load entries for one prefix from a JSONL index."""
    path = Path(index_dir) / f"{prefix.upper()}.jsonl"
    entries: list[TagIndexEntry] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entries.append(TagIndexEntry(**json.loads(line)))
    return entries


def search_tags(
    index_dir: str | Path,
    prefixes: Iterable[str],
    query: str,
    *,
    limit: int = 100,
) -> list[TagIndexEntry]:
    """Search plant-scoped indexes by tag name, fulltagname, unit, or description."""
    terms = [term.lower() for term in query.split() if term.strip()]
    results: list[TagIndexEntry] = []
    for prefix in prefixes:
        for entry in load_entries(index_dir, prefix):
            haystack = entry.search_text
            if terms and not all(term in haystack for term in terms):
                continue
            results.append(entry)
            if len(results) >= limit:
                return results
    return results


def find_entry(index_dir: str | Path, fulltagname: str) -> TagIndexEntry:
    """Find one tag across all available prefix indexes."""
    target = fulltagname.strip()
    manifest_path = Path(index_dir) / "manifest.json"
    prefixes: Iterable[str]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prefixes = manifest.get("prefixes", {}).keys()
    else:
        prefixes = [path.stem for path in Path(index_dir).glob("*.jsonl")]
    for prefix in prefixes:
        for entry in load_entries(index_dir, prefix):
            if entry.fulltagname == target:
                return entry
    raise KeyError(f"태그를 찾지 못했습니다: {fulltagname}")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/search OPC tag indexes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build prefix JSONL indexes")
    build.add_argument("--tags-csv", required=True)
    build.add_argument("--output-dir", default="opc_assets/tag_index")
    build.add_argument("--prefix", action="append", dest="prefixes")

    search = subparsers.add_parser("search", help="Search built indexes")
    search.add_argument("--index-dir", default="opc_assets/tag_index")
    search.add_argument("--prefix", action="append", dest="prefixes", required=True)
    search.add_argument("--query", default="")
    search.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)
    if args.command == "build":
        counts = build_tag_indexes(
            args.tags_csv, args.output_dir, args.prefixes or DEFAULT_PREFIXES
        )
        for prefix, count in counts.items():
            print(f"{prefix}: {count}")
        return 0

    results = search_tags(args.index_dir, args.prefixes, args.query, limit=args.limit)
    for entry in results:
        print(
            json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":"))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
