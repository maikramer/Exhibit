#!/usr/bin/env python3
"""Smoke: construct ExbWindow and seed tab 0 (run inside Flatpak)."""
import faulthandler
import sys
import traceback
from pathlib import Path

faulthandler.enable(file=sys.stderr, all_threads=True)

log = Path("/tmp/exb-smoke.txt")


def w(msg: str) -> None:
    with log.open("a") as f:
        f.write(msg + "\n")
        f.flush()
    print(msg, flush=True)


def main() -> int:
    if log.exists():
        log.unlink()
    w("start")
    import os

    # Isolate from host session restore / user GSettings.
    os.environ.setdefault("GSETTINGS_BACKEND", "memory")
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Exb", "0")
    from gi.repository import Adw, GLib, Gio

    Adw.init()
    w("adw ok")

    pkgdatadir = "/app/share/exhibit"
    resource = Gio.Resource.load(f"{pkgdatadir}/exhibit.gresource")
    resource._register()
    w("resource ok")
    from exhibit.window import ExbWindow

    w("import window ok")
    app = Adw.Application(application_id="io.github.nokse22.Exhibit.smoke")
    app.register()
    w("app registered")
    try:
        win = ExbWindow(application=app)
        w("window created")
        pages = win.tab_view.get_n_pages()
        w(f"pages={pages}")
        w(f"tab_bar_view={win.tab_bar.get_view()}")
        w(f"has_outliner={hasattr(win, 'object_tree_revealer')}")
        w(f"split_paned={win.split_compare_main_paned is not None}")
        eng = win.engine
        w(f"engine_ok={eng is not None}")
        viewer = win.f3d_viewer
        w(f"bridge_engine={viewer.engine is not None}")
        if pages != 1:
            w(f"FAIL expected 1 page got {pages}")
            return 1

        # Optional: open two models into tabs (paths via EXB_SMOKE_MODELS).
        models = [
            p
            for p in os.environ.get("EXB_SMOKE_MODELS", "").split(":")
            if p and Path(p).is_file()
        ]
        if len(models) >= 2:
            w(f"opening {len(models)} models")
            win._open_model_paths(models[:2])
            ctx = GLib.MainContext.default()
            pages2 = 1
            for i in range(400):
                while ctx.pending():
                    ctx.iteration(False)
                pages2 = win.tab_view.get_n_pages()
                if pages2 >= 2:
                    break
                # Give warm-load / queue advance wall time.
                GLib.usleep(25_000)
            pending = list(getattr(win, "_pending_open_paths", None) or [])
            w(f"pages_after_open={pages2} pending={pending!r}")
            if pages2 < 2:
                # Explicit second tab — proves tab API even if queue stalled (no GL).
                win.load_file(filepath=models[1], new_tab=True)
                for _ in range(100):
                    while ctx.pending():
                        ctx.iteration(False)
                pages2 = win.tab_view.get_n_pages()
                w(f"pages_after_explicit={pages2}")
            if pages2 < 2:
                w("FAIL expected >=2 tabs after two files")
                return 1
        else:
            w("skip multi-file (set EXB_SMOKE_MODELS=a.glb:b.glb)")

        w("OK")
        return 0
    except Exception:
        w("EXCEPTION")
        w(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
