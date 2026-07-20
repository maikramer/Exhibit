#!/usr/bin/env python3
"""Open/close large GLB tabs and report RSS — run inside Exhibit flatpak.

  flatpak run --filesystem=host --command=python3 io.github.nokse22.Exhibit \
    /home/maikeu/GitClones/Exhibit/tools/profile_tab_memory.py
"""

from __future__ import annotations

import gc
import os
import sys
import time
import traceback

PKGDATADIR = os.environ.get("EXHIBIT_PKGDATADIR", "/app/share/exhibit")
PATCHED = os.environ.get("EXHIBIT_PATCHED_PKG")
MESH_DIR = os.environ.get(
    "EXHIBIT_MESH_DIR",
    "/home/maikeu/GitClones/GameDev/VibeGame/examples/simple-rpg/public/assets/meshes/_intermediate",
)
MAX_FILES = int(os.environ.get("EXHIBIT_PROFILE_FILES", "4"))
SETTLE_S = float(os.environ.get("EXHIBIT_SETTLE_S", "2.5"))
LOAD_TIMEOUT_S = float(os.environ.get("EXHIBIT_LOAD_TIMEOUT_S", "120"))

if PATCHED:
    sys.path.insert(0, PATCHED)
sys.path.insert(1, PKGDATADIR)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


def rss_mb() -> float:
    with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def hwm_mb() -> float:
    with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] rss={rss_mb():8.1f} MiB  {msg}", flush=True)


def pick_meshes(directory: str, limit: int) -> list[str]:
    paths = []
    with os.scandir(directory) as it:
        for entry in it:
            if entry.is_file() and entry.name.lower().endswith(".glb"):
                paths.append((entry.stat().st_size, entry.path))
    paths.sort(reverse=True)
    return [p for _size, p in paths[:limit]]


def wait_until(predicate, timeout_s: float, step_s: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        # Drain main context while waiting.
        ctx = GLib.MainContext.default()
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(step_s)
    return False


def pump(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    ctx = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.05)


def close_all_loaded_tabs(win) -> int:
    closed = 0
    # Keep closing until only empty/unloaded tabs remain (or one untitled).
    for _ in range(32):
        pages = []
        for i in range(win.tab_view.get_n_pages()):
            page = win.tab_view.get_nth_page(i)
            child = page.get_child()
            if getattr(child, "loaded", False) or getattr(child, "filepath", ""):
                pages.append(page)
        if not pages:
            break
        page = pages[-1]
        win.tab_view.close_page(page)
        pump(0.3)
        closed += 1
    return closed


def main() -> int:
    meshes = pick_meshes(MESH_DIR, MAX_FILES)
    if not meshes:
        print(f"No GLBs in {MESH_DIR}", file=sys.stderr)
        return 2

    log(f"patched={PATCHED or '(installed)'}")
    for path in meshes:
        log(f"mesh {os.path.basename(path)} ({os.path.getsize(path)/1024/1024:.1f} MiB)")

    resource = Gio.Resource.load(os.path.join(PKGDATADIR, "exhibit.gresource"))
    resource._register()

    from exhibit.main import Viewer3dApplication
    from exhibit.window import Viewer3dWindow

    # Non-unique so profiling does not steal / attach to a running Exhibit.
    app = Viewer3dApplication()
    app.set_flags(
        Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN
    )
    GLib.set_prgname("exhibit-mem-profile")

    baseline = {"rss": 0.0}
    results: list[tuple[str, float]] = []

    def on_activate(application: Adw.Application) -> None:
        win = Viewer3dWindow(application=application)
        win.present()
        pump(1.0)
        gc.collect()
        pump(0.5)
        baseline["rss"] = rss_mb()
        log(f"BASELINE after empty window  hwm={hwm_mb():.1f}")

        peak_after_loads = baseline["rss"]
        for idx, path in enumerate(meshes):
            log(f"LOAD[{idx}] start {os.path.basename(path)}")
            before = rss_mb()
            win.load_file(filepath=path)
            ok = wait_until(
                lambda p=path: any(
                    getattr(t, "filepath", "") == p and getattr(t, "loaded", False)
                    for t in win._iter_tabs()
                ),
                LOAD_TIMEOUT_S,
            )
            pump(SETTLE_S)
            gc.collect()
            pump(0.3)
            after = rss_mb()
            peak_after_loads = max(peak_after_loads, after)
            delta = after - before
            results.append((f"load:{os.path.basename(path)}", after))
            log(
                f"LOAD[{idx}] {'OK' if ok else 'TIMEOUT'} "
                f"delta={delta:+.1f} MiB tabs={win.tab_view.get_n_pages()}"
            )
            if not ok:
                print("Abort: load timeout", file=sys.stderr)
                application.quit()
                return

        log(f"PEAK after all loads={peak_after_loads:.1f} MiB")
        closed = close_all_loaded_tabs(win)
        pump(SETTLE_S)
        gc.collect()
        pump(1.0)
        after_close = rss_mb()
        results.append(("after_close_tabs", after_close))
        log(f"CLOSE tabs closed={closed} rss={after_close:.1f}")

        # Second wave: reopen same files (warm cache / engine churn).
        for idx, path in enumerate(meshes[:2]):
            log(f"RELOAD[{idx}] {os.path.basename(path)}")
            win.load_file(filepath=path)
            wait_until(
                lambda p=path: any(
                    getattr(t, "filepath", "") == p and getattr(t, "loaded", False)
                    for t in win._iter_tabs()
                ),
                LOAD_TIMEOUT_S,
            )
            pump(SETTLE_S)

        closed2 = close_all_loaded_tabs(win)
        pump(SETTLE_S)
        gc.collect()
        pump(1.5)
        final = rss_mb()
        results.append(("final", final))
        log(f"FINAL after second close wave closed={closed2}")

        retained = final - baseline["rss"]
        leak_suspect = retained > 80.0  # MiB hard threshold for these huge assets
        print("---- SUMMARY ----", flush=True)
        print(f"baseline_rss_mib={baseline['rss']:.1f}", flush=True)
        print(f"peak_rss_mib={peak_after_loads:.1f}", flush=True)
        print(f"final_rss_mib={final:.1f}", flush=True)
        print(f"retained_vs_baseline_mib={retained:.1f}", flush=True)
        print(f"hwm_mib={hwm_mb():.1f}", flush=True)
        print(f"leak_suspect={'YES' if leak_suspect else 'NO'}", flush=True)
        for label, value in results:
            print(f"point {label}={value:.1f}", flush=True)

        # Probe prepare-cache / engines still alive.
        try:
            from exhibit import meshopt_decompress as md

            cache_n = len(getattr(md, "_prepare_cache", {}))
            refs_n = len(getattr(md, "_prepare_refs", {}))
            print(f"prepare_cache_entries={cache_n}", flush=True)
            print(f"prepare_refs_entries={refs_n}", flush=True)
        except Exception as exc:
            print(f"prepare_cache_probe_error={exc}", flush=True)

        engines = 0
        for tab in win._iter_tabs():
            if getattr(tab.viewer, "engine", None) is not None:
                engines += 1
        print(f"alive_engines_in_tabs={engines}", flush=True)
        print(f"n_pages={win.tab_view.get_n_pages()}", flush=True)

        application.quit()

    app.connect("activate", on_activate)
    try:
        return app.run([])
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
