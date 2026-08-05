/*
 * exb-postfx.c
 *
 * Composes a F3D final_shader (vec4 pixel(vec2 uv)) from ExbPostFxState.
 * GLES-safe: literal loop bounds, no continue, no scientific literals.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "exb-postfx.h"

void
exb_postfx_state_init_defaults (ExbPostFxState *state)
{
  g_return_if_fail (state != NULL);

  state->bloom = FALSE;
  state->bloom_threshold = 0.25;
  state->bloom_intensity = 1.25;
  state->bloom_radius = 5.0;

  state->godrays = FALSE;
  state->godrays_intensity = 0.5;
  state->godrays_decay = 0.94;
  state->godrays_density = 1.0;
  state->godrays_weight = 0.4;
}

static void
append_ascii_float (GString *body, const gchar *fmt, gdouble value)
{
  gchar buf[G_ASCII_DTOSTR_BUF_SIZE];

  g_ascii_formatd (buf, sizeof (buf), "%.6f", value);
  g_string_append_printf (body, fmt, buf);
}

gchar *
exb_postfx_build_shader (const ExbPostFxState *state)
{
  GString *body;

  g_return_val_if_fail (state != NULL, NULL);

  if (!state->bloom && !state->godrays)
    return NULL;

  /* Keep shader simple for VTK/GLES final-pass compilers. */
  body = g_string_new (
      "vec4 pixel(vec2 uv)\n"
      "{\n"
      "  vec3 color = texture(source, uv).rgb;\n"
      "  vec2 texel = 1.0 / vec2(resolution);\n");

  if (state->bloom)
    {
      g_string_append (body, "  {\n");
      append_ascii_float (body, "    float threshold = %s;\n",
                          state->bloom_threshold);
      append_ascii_float (body, "    float intensity = %s;\n",
                          state->bloom_intensity);
      append_ascii_float (body, "    float radius = %s;\n",
                          state->bloom_radius);
      /* Separable-ish 9x9 box on highlights; literal bounds, no continue. */
      g_string_append (
          body,
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
          "  }\n");
    }

  if (state->godrays)
    {
      g_string_append (body, "  {\n");
      append_ascii_float (body, "    float intensity = %s;\n",
                          state->godrays_intensity);
      append_ascii_float (body, "    float decay = %s;\n",
                          state->godrays_decay);
      append_ascii_float (body, "    float density = %s;\n",
                          state->godrays_density);
      append_ascii_float (body, "    float weight = %s;\n",
                          state->godrays_weight);
      /*
       * Screen-space shafts (GPU Gems style) on post-tonemap LDR.
       * Soft luma gate + synthetic sun near light_pos so dull scenes still
       * show rays; grayscale emit avoids speckled sample dots.
       */
      g_string_append (
          body,
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
          /* ~6x milder than prior 0.55 gain — intensity ~0.5 usable. */
          "    color += rays * intensity * vec3(1.05, 0.98, 0.88) * 0.1;\n"
          "  }\n");
    }

  g_string_append (
      body,
      "  return vec4(color, 1.0);\n"
      "}\n");
  return g_string_free (body, FALSE);
}
