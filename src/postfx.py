# SPDX-License-Identifier: GPL-3.0-or-later
"""PostFX helpers for CLI / tests (mirrors libexhibit/exb-postfx.c)."""

from __future__ import annotations

from typing import Any

# Match ExbPostFxState defaults (post-tonemap LDR).
DEFAULT_BLOOM_THRESHOLD = 0.25
DEFAULT_BLOOM_INTENSITY = 1.25
DEFAULT_BLOOM_RADIUS = 5.0
DEFAULT_GODRAYS_INTENSITY = 0.5
DEFAULT_GODRAYS_DECAY = 0.94
DEFAULT_GODRAYS_DENSITY = 1.0
DEFAULT_GODRAYS_WEIGHT = 0.4


def build_final_shader(
    *,
    bloom: bool = False,
    bloom_threshold: float = DEFAULT_BLOOM_THRESHOLD,
    bloom_intensity: float = DEFAULT_BLOOM_INTENSITY,
    bloom_radius: float = DEFAULT_BLOOM_RADIUS,
    godrays: bool = False,
    godrays_intensity: float = DEFAULT_GODRAYS_INTENSITY,
    godrays_decay: float = DEFAULT_GODRAYS_DECAY,
    godrays_density: float = DEFAULT_GODRAYS_DENSITY,
    godrays_weight: float = DEFAULT_GODRAYS_WEIGHT,
) -> str:
    """Build F3D ``render.effect.final_shader`` GLSL, or empty if no effects."""
    if not bloom and not godrays:
        return ""
    parts = [
        "vec4 pixel(vec2 uv)\n",
        "{\n",
        "  vec3 color = texture(source, uv).rgb;\n",
        "  vec2 texel = 1.0 / vec2(resolution);\n",
    ]
    if bloom:
        parts.append(
            "  {\n"
            f"    float threshold = {bloom_threshold:.6f};\n"
            f"    float intensity = {bloom_intensity:.6f};\n"
            f"    float radius = {bloom_radius:.6f};\n"
            "    vec3 bloom = vec3(0.0);\n"
            "    float wsum = 0.0;\n"
            "    for (int i = -4; i <= 4; i++)\n"
            "    {\n"
            "      for (int j = -4; j <= 4; j++)\n"
            "      {\n"
            "        float fi = float(i);\n"
            "        float fj = float(j);\n"
            "        float dist2 = fi * fi + fj * fj;\n"
            "        float w = exp(-dist2 * 0.12);\n"
            "        vec2 offset = vec2(fi, fj) * texel * radius;\n"
            "        vec2 suv = clamp(uv + offset, vec2(0.0), vec2(1.0));\n"
            "        vec3 s = texture(source, suv).rgb;\n"
            "        float luma = dot(s, vec3(0.2126, 0.7152, 0.0722));\n"
            "        float soft = smoothstep(threshold, threshold + 0.45, luma);\n"
            "        bloom += s * soft * w;\n"
            "        wsum += w;\n"
            "      }\n"
            "    }\n"
            "    bloom /= max(wsum, 0.0001);\n"
            "    color += bloom * intensity;\n"
            "  }\n"
        )
    if godrays:
        parts.append(
            "  {\n"
            f"    float intensity = {godrays_intensity:.6f};\n"
            f"    float decay = {godrays_decay:.6f};\n"
            f"    float density = {godrays_density:.6f};\n"
            f"    float weight = {godrays_weight:.6f};\n"
            "    vec2 light_pos = vec2(0.5, 0.82);\n"
            "    vec2 delta = (uv - light_pos) * (density / 32.0);\n"
            "    vec2 coord = uv;\n"
            "    vec3 rays = vec3(0.0);\n"
            "    float illum = 1.0;\n"
            "    for (int i = 0; i < 32; i++)\n"
            "    {\n"
            "      coord -= delta;\n"
            "      vec2 suv = clamp(coord, vec2(0.0), vec2(1.0));\n"
            "      vec3 s = texture(source, suv).rgb;\n"
            "      float luma = dot(s, vec3(0.2126, 0.7152, 0.0722));\n"
            "      float bright = smoothstep(0.18, 0.6, luma);\n"
            "      float near_sun = 1.0 - smoothstep(0.0, 0.16, length(suv - light_pos));\n"
            "      float emit = max(bright, near_sun * 0.35);\n"
            "      rays += vec3(emit) * illum * weight;\n"
            "      illum *= decay;\n"
            "    }\n"
            "    color += rays * intensity * vec3(1.05, 0.98, 0.88) * 0.1;\n"
            "  }\n"
        )
    parts.append("  return vec4(color, 1.0);\n}\n")
    return "".join(parts)


def bloom_options_from_args(args: Any) -> dict[str, Any]:
    """Exb GObject props from argparse namespace (missing attrs → defaults)."""
    return {
        "bloom": bool(getattr(args, "bloom", False)),
        "bloom-threshold": float(
            getattr(args, "bloom_threshold", DEFAULT_BLOOM_THRESHOLD)
        ),
        "bloom-intensity": float(
            getattr(args, "bloom_intensity", DEFAULT_BLOOM_INTENSITY)
        ),
        "bloom-radius": float(getattr(args, "bloom_radius", DEFAULT_BLOOM_RADIUS)),
        "godrays": bool(getattr(args, "godrays", False)),
        "godrays-intensity": float(
            getattr(args, "godrays_intensity", DEFAULT_GODRAYS_INTENSITY)
        ),
        "godrays-decay": float(
            getattr(args, "godrays_decay", DEFAULT_GODRAYS_DECAY)
        ),
        "godrays-density": float(
            getattr(args, "godrays_density", DEFAULT_GODRAYS_DENSITY)
        ),
        "godrays-weight": float(
            getattr(args, "godrays_weight", DEFAULT_GODRAYS_WEIGHT)
        ),
    }
