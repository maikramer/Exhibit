#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Profile the host pytest suite (CPU + allocations + temp leaks).

Stdlib only (cProfile + tracemalloc). Writes a report under ``.profile/``.

  ./tools/profile_pytest.py
  ./tools/profile_pytest.py -k prepare --top 40
  ./tools/profile_pytest.py --no-profile   # leak scan + durations only

Flatpak/GUI RSS: ``tools/profile_tab_memory.py`` (needs display).
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".profile"
TEMP_PREFIXES = (
    "exhibit-meshopt-",
    "exhibit-parts-",
    "exhibit-skinw-",
    "exhibit-ktx-",
    "exhibit-pack-",
)


def _exhibit_temps(tmpdir: str | None = None) -> list[Path]:
    base = Path(tmpdir or tempfile.gettempdir())
    found: list[Path] = []
    try:
        for entry in base.iterdir():
            name = entry.name
            if any(name.startswith(prefix) for prefix in TEMP_PREFIXES):
                found.append(entry)
    except OSError:
        pass
    return sorted(found)


def _temp_report(paths: list[Path]) -> tuple[int, int]:
    total = 0
    alive = 0
    for path in paths:
        try:
            total += path.stat().st_size
            alive += 1
        except OSError:
            pass
    return alive, total


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KiB"
    if n < 1024**3:
        return f"{n / (1024**2):.1f} MiB"
    return f"{n / (1024**3):.2f} GiB"


def _write_cprofile(pr: cProfile.Profile, path: Path, top: int) -> str:
    stream = io.StringIO()
    stats = pstats.Stats(pr, stream=stream).sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats(top)
    text = stream.getvalue()
    path.write_text(text, encoding="utf-8")
    # Also dump binary for snakeviz / tuna.
    pr.dump_stats(str(path.with_suffix(".pstats")))
    return text


def _write_tracemalloc(snapshot: tracemalloc.Snapshot, path: Path, top: int) -> str:
    lines = [
        "Top allocation sites (traceback → size)",
        "",
    ]
    stats = snapshot.statistics("traceback")
    for index, stat in enumerate(stats[:top], start=1):
        lines.append(f"#{index}: {_format_bytes(stat.size)} in {stat.count} blocks")
        for frame in stat.traceback.format()[-6:]:
            lines.append(f"  {frame}")
        lines.append("")
    # Also by filename for a quick map.
    lines.append("--- by file ---")
    for stat in snapshot.statistics("filename")[:top]:
        lines.append(f"{_format_bytes(stat.size):>10}  {stat.traceback}")
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="How many rows to keep in CPU/alloc reports (default 30)",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Skip cProfile/tracemalloc (still runs pytest --durations + leak scan)",
    )
    parser.add_argument(
        "--clean-stale-temps",
        action="store_true",
        help="Delete pre-existing /tmp/exhibit-* files before the run",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra pytest args (prefix with -- if needed)",
    )
    args = parser.parse_args(argv)

    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = OUT_DIR / f"pytest-profile-{stamp}.md"
    cpu_path = OUT_DIR / f"pytest-cprofile-{stamp}.txt"
    mem_path = OUT_DIR / f"pytest-tracemalloc-{stamp}.txt"

    before_temps = _exhibit_temps()
    if args.clean_stale_temps and before_temps:
        removed = 0
        for path in before_temps:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        print(f"Removed {removed} stale exhibit temp(s) under {tempfile.gettempdir()}")
        before_temps = _exhibit_temps()

    before_count, before_bytes = _temp_report(before_temps)
    print(
        f"Temps before: {before_count} files, {_format_bytes(before_bytes)} "
        f"({tempfile.gettempdir()})"
    )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--durations=30",
        "-q",
        *pytest_args,
    ]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    start = time.perf_counter()
    if args.no_profile:
        proc = subprocess.run(cmd, cwd=ROOT, env=env)
        exit_code = proc.returncode
        cpu_text = "(skipped)"
        mem_text = "(skipped)"
        peak_traced = 0
    else:
        tracemalloc.start(25)
        pr = cProfile.Profile()
        pr.enable()
        # Run pytest in-process so profilers see exhibit code.
        import pytest

        exit_code = int(pytest.main(cmd[3:]))
        pr.disable()
        current, peak = tracemalloc.get_traced_memory()
        peak_traced = peak
        snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        cpu_text = _write_cprofile(pr, cpu_path, args.top)
        mem_text = _write_tracemalloc(snapshot, mem_path, args.top)
        print(f"tracemalloc peak: {_format_bytes(peak_traced)} (current {_format_bytes(current)})")

    elapsed = time.perf_counter() - start

    # Ask prepare cache for leftovers (best-effort; import after tests).
    cache_lines: list[str] = []
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from exhibit import meshopt_decompress as meshopt

        stats = meshopt.prepare_cache_stats()
        cache_lines = [
            f"entries={stats['entries']}",
            f"refs={stats['refs']}",
            f"orphans={stats['orphans']}",
            f"bytes={_format_bytes(stats['bytes'])}",
        ]
        if stats["entries"] or stats["refs"] or stats["orphans"]:
            meshopt.clear_prepare_cache()
            cache_lines.append("cleared via clear_prepare_cache()")
    except Exception as exc:
        cache_lines = [f"(unavailable: {exc})"]

    after_temps = _exhibit_temps()
    after_count, after_bytes = _temp_report(after_temps)
    leaked = [p for p in after_temps if p not in before_temps]
    leaked_count, leaked_bytes = _temp_report(leaked)

    # Extract durations block from last pytest run is awkward in-process;
    # re-run is expensive. Rely on console output already printed by pytest.
    summary = f"""# Pytest profile {stamp}

- cwd: `{ROOT}`
- elapsed: **{elapsed:.2f}s**
- exit: `{exit_code}`
- tracemalloc peak: **{_format_bytes(peak_traced) if not args.no_profile else "n/a"}**

## Temp files (`/tmp/exhibit-*`)

| When | Files | Size |
|------|------:|-----:|
| Before | {before_count} | {_format_bytes(before_bytes)} |
| After | {after_count} | {_format_bytes(after_bytes)} |
| New this run | {leaked_count} | {_format_bytes(leaked_bytes)} |

New temps:
{chr(10).join(f"- `{p}` ({_format_bytes(p.stat().st_size)})" for p in leaked[:40]) or "- (none)"}

## Prepare cache (post-suite)

{chr(10).join("- " + line for line in cache_lines)}

## Artifacts

- CPU (text): `{cpu_path.relative_to(ROOT) if not args.no_profile else "n/a"}`
- CPU (pstats): `{(cpu_path.with_suffix(".pstats")).relative_to(ROOT) if not args.no_profile else "n/a"}`
- Allocations: `{mem_path.relative_to(ROOT) if not args.no_profile else "n/a"}`

View CPU interactively (optional):

```sh
pip install snakeviz
snakeviz {cpu_path.with_suffix(".pstats").relative_to(ROOT) if not args.no_profile else "…"}
```

## CPU top (cumulative)

```
{cpu_text[:12000] if not args.no_profile else "(skipped)"}
```

## Allocations top

```
{mem_text[:12000] if not args.no_profile else "(skipped)"}
```
"""
    report_path.write_text(summary, encoding="utf-8")
    print(f"Report: {report_path}")
    print(
        f"Temps after: {after_count} files, {_format_bytes(after_bytes)} "
        f"(new this run: {leaked_count}, {_format_bytes(leaked_bytes)})"
    )
    if leaked_count:
        print("WARNING: suite left new exhibit temp files — likely missing release/clear")
        return max(exit_code, 2) if exit_code else 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
