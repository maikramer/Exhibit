#!/usr/bin/env python3
"""Probe final_shader / bloom via Exb standalone (run inside flatpak)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("Exb", "0")
gi.require_version("Gio", "2.0")
from gi.repository import Exb, Gio


def render(eng, out: Path, name: str) -> None:
    fs = eng.get_property("final-shader") or ""
    bloom = eng.get_property("bloom")
    print(f"=== {name} bloom={bloom} fs_len={len(fs)}")
    print(fs[:220].replace("\n", "\\n"))
    tex = eng.render_texture()
    path = out / f"{name}.png"
    if tex is None:
        print("RENDER FAIL")
        return
    tex.save_to_filename(str(path))
    print(f"wrote {path} size={path.stat().st_size}")


def main() -> int:
    model = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if model is None or not model.is_file():
        print("usage: probe_bloom_shader.py MODEL", file=sys.stderr)
        return 2

    eng = Exb.Engine.new_standalone()
    eng.set_size(256, 256)
    eng.set_property("show-grid", False)
    props = [
        p.name
        for p in eng.list_properties()
        if "bloom" in p.name or "final" in p.name
    ]
    print("props", props)
    eng.load_file(Gio.File.new_for_path(str(model)))
    out = Path(tempfile.mkdtemp(prefix="exhibit-bloom-"))

    eng.set_property("bloom", False)
    eng.set_property("final-shader", "")
    render(eng, out, "off")

    eng.set_property(
        "final-shader",
        "vec4 pixel(vec2 uv){vec3 v=texture(source,uv).rgb;return vec4(1.0-v,1.0);}",
    )
    render(eng, out, "negative")

    eng.set_property("final-shader", "")
    eng.set_property("bloom", True)
    eng.set_property("bloom-threshold", 0.75)
    eng.set_property("bloom-intensity", 0.5)
    eng.set_property("bloom-radius", 4.0)
    render(eng, out, "bloom")

    simple = """vec4 pixel(vec2 uv)
{
  vec3 color = texture(source, uv).rgb;
  vec2 texel = 4.0 / vec2(resolution);
  vec3 sum = vec3(0.0);
  for (int i = -2; i <= 2; i++)
  {
    for (int j = -2; j <= 2; j++)
    {
      vec3 s = texture(source, uv + vec2(float(i), float(j)) * texel).rgb;
      float luma = dot(s, vec3(0.2126, 0.7152, 0.0722));
      sum += s * max(luma - 0.75, 0.0);
    }
  }
  return vec4(color + sum * 0.1, 1.0);
}
"""
    eng.set_property("bloom", False)
    eng.set_property("final-shader", simple)
    render(eng, out, "simple")

    print("outdir", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
