/*
 * exb-engine.c
 *
 * Copyright 2026 Nokse <nokse@posteo.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "exb-engine.h"
#include "exb-utils.h"
#include "exb-enums.h"

#include <f3d/camera_c_api.h>
#include <f3d/engine_c_api.h>
#include <f3d/image_c_api.h>
#include <f3d/options_c_api.h>
#include <f3d/scene_c_api.h>
#include <f3d/window_c_api.h>

typedef struct
{
  f3d_engine_t *engine;
  f3d_window_t *window;
  f3d_scene_t *scene;
  f3d_camera_t *camera;

  bool orthographic;

  int width;
  int height;
  double distance;

  GFile *file;
} ExbEnginePrivate;

G_DEFINE_TYPE_WITH_PRIVATE (ExbEngine, exb_engine, G_TYPE_OBJECT)

enum
{
  PROP_0,
  PROP_FILE,
  PROP_UP,
  PROP_ORTHOGRAPHIC,
  PROP_SHOW_GRID,
  PROP_GRID_ABSOLUTE,
  PROP_GRID_UNIT,
  PROP_GRID_COLOR,
  PROP_BLENDING,
  PROP_BLENDING_MODE,
  PROP_TONE_MAPPING,
  PROP_AMBIENT_OCCLUSION,
  PROP_ANTI_ALIASING,
  PROP_ANTI_ALIASING_MODE,
  PROP_HDRI_AMBIENT,
  PROP_HDRI_SKYBOX,
  PROP_HDRI_FILE,
  PROP_BLUR_BACKGROUND,
  PROP_BLUR_COC,
  PROP_LIGHT_INTENSITY,
  PROP_BACKGROUND_COLOR,
  PROP_SHOW_EDGES,
  PROP_EDGES_WIDTH,
  PROP_POINT_SIZE,
  PROP_SHOW_ARMATURE,
  PROP_MODEL_COLOR,
  PROP_MODEL_METALLIC,
  PROP_MODEL_ROUGHNESS,
  PROP_MODEL_OPACITY,
  PROP_TEXTURE_MATCAP,
  PROP_TEXTURE_BASE_COLOR,
  PROP_TEXTURE_EMISSIVE,
  PROP_TEXTURE_MATERIAL,
  PROP_NORMAL_SCALE,
  PROP_VOLUME_RENDERING,
  PROP_VOLUME_INVERSE_OPACITY,
  PROP_SHOW_SPRITES,
  PROP_SPRITES_SIZE,
  PROP_SPRITES_TYPE,
  PROP_ANIMATION_INDEX,
  N_PROPS
};

static GParamSpec *properties[N_PROPS];

enum
{
  SIGNAL_CHANGED,
  N_SIGNALS
};

static guint signals[N_SIGNALS];

typedef struct
{
  const char *prop_name;
  const char *f3d_key;
} OptionMap;

static const OptionMap option_maps[] = {
  { "show-grid",              "render.grid.enable"                },
  { "grid-absolute",          "render.grid.absolute"              },
  { "grid-unit",              "render.grid.unit"                  },
  { "grid-subdivisions",      "render.grid.subdivisions"          },
  { "grid-color",             "render.grid.color"                 },
  { "blending",               "render.effect.blending.enable"     },
  { "blending-mode",          "render.effect.blending.mode"       },
  { "tone-mapping",           "render.effect.tone_mapping"        },
  { "ambient-occlusion",      "render.effect.ambient_occlusion"   },
  { "anti-aliasing",          "render.effect.antialiasing.enable" },
  { "anti-aliasing-mode",     "render.effect.antialiasing.mode"   },
  { "hdri-ambient",           "render.hdri.ambient"               },
  { "hdri-skybox",            "render.background.skybox"          },
  { "hdri-file",              "render.hdri.file"                  },
  { "blur-background",        "render.background.blur.enable"     },
  { "blur-coc",               "render.background.blur.coc"        },
  { "light-intensity",        "render.light.intensity"            },
  { "background-color",       "render.background.color"           },
  { "show-edges",             "render.show_edges"                 },
  { "edges-width",            "render.line_width"                 },
  { "point-size",             "render.point_size"                 },
  { "show-armature",          "render.armature.enable"            },
  /* { "final-shader",           "render.effect.final_shader"        }, */
  { "model-color",            "model.color.rgb"                   },
  { "model-metallic",         "model.material.metallic"           },
  { "model-roughness",        "model.material.roughness"          },
  { "model-opacity",          "model.color.opacity"               },
  { "texture-matcap",         "model.matcap.texture"              },
  { "texture-base-color",     "model.color.texture"               },
  { "texture-emissive",       "model.emissive.texture"            },
  { "texture-material",       "model.material.texture"            },
  { "texture-normal",         "model.normal.texture"              },
  { "emissive-factor",        "model.emissive.factor"             },
  { "normal-scale",           "model.normal.scale"                },
  { "volume-rendering",       "model.volume.enable"               },
  { "volume-inverse-opacity", "model.volume.inverse"              },
  { "show-sprites",           "model.point_sprites.enable"        },
  { "sprites-size",           "model.point_sprites.size"          },
  { "sprites-type",           "model.point_sprites.type"          },
  /* { "scivis",                 "model.scivis.enable"               }, */
  /* { "scivis-component",       "model.scivis.component"            }, */
  /* { "cells",                  "model.scivis.cells"                }, */
  /* { "scalar",                 "model.scivis.array_name"           }, */
  { "up",                     "scene.up_direction"                },
  { "orthographic",           "scene.camera.orthographic"         },
  { "animation-index",        "scene.animation.index"             }
};

static const gsize option_maps_len = G_N_ELEMENTS(option_maps);

static const char *
options_map_lookup (const char *prop_name)
{
  for (gsize i = 0; i < option_maps_len; i++)
    if (g_str_equal(option_maps[i].prop_name, prop_name))
      return g_strdup (option_maps[i].f3d_key);
  return NULL;
}

/**
 * exb_engine_render_texture:
 * @self: a #ExbEngine
 *
 * Returns: (transfer full): A GdkTexture with the rendered image
 */
GdkTexture *
exb_engine_render_texture (ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  g_autoptr (f3d_image_t) img = NULL;
  g_autoptr (GdkTexture) texture = NULL;
  g_autoptr (GBytes) bytes = NULL;
  unsigned int width, height, channels;
  void *data = NULL;

  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);
  g_return_val_if_fail (priv->window != NULL, NULL);

  img = f3d_window_render_to_image (priv->window, FALSE);
  if (!img)
    return NULL;

  width = f3d_image_get_width (img);
  height = f3d_image_get_height (img);
  channels = f3d_image_get_channel_count (img);

  data = f3d_image_get_content (img);
  bytes = g_bytes_new (data, (size_t) width * height * channels);

  texture = gdk_memory_texture_new (
      (int) width, (int) height, channels == 4 ? GDK_MEMORY_R8G8B8A8 : GDK_MEMORY_R8G8B8, bytes,
      (size_t) width * channels);
  return g_steal_pointer(&texture);
}

gboolean
_exb_engine_load_file (ExbEngine  *self,
                       GFile      *file)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  g_autofree const char *file_path = NULL;

  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);

  file_path = g_file_get_path (file);

  if (!file_path)
    {
      g_message ("ExbEngine: No file path");
      return FALSE;
    }

  if (!priv->scene)
    {
      g_message ("ExbEngine: No scene");
      return FALSE;
    }

  g_message ("ExbEngine: Loading file: %s", file_path);

  if (!f3d_scene_supports (priv->scene, file_path))
    {
      g_message ("ExbEngine: File not supported");
      return FALSE;
    }

  f3d_scene_clear (priv->scene);
  f3d_scene_add (priv->scene, file_path);

  f3d_camera_reset_to_bounds (priv->camera, 0.9);

  g_signal_emit (self, signals[SIGNAL_CHANGED], 0);

  return TRUE;
}

/**
 * exb_engine_set_file:
 * @self: a #ExbEngine
 * @file: a #GFile
 */
void
exb_engine_set_file(ExbEngine *self,
                    GFile     *file)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));
  g_return_if_fail (G_IS_FILE (file));

  g_set_object (&priv->file, file);
  _exb_engine_load_file(self, file);
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_FILE]);
}

/**
 * exb_engine_get_file:
 * @self: a #ExbEngine
 *
 * Returns: (transfer none): A GFile
 */
GFile *
exb_engine_get_file(ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_val_if_fail (EXB_IS_ENGINE (self), NULL);

  return priv->file;
}

gboolean
exb_engine_render (ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);

  g_return_val_if_fail (priv->window != NULL, false);

  f3d_window_render (priv->window);

  return true;
}

void
exb_engine_set_size (ExbEngine *self,
                     uint       width,
                     uint       height)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));
  g_return_if_fail (priv->window != NULL);

  f3d_window_set_size (priv->window, width, height);

  priv->width = width;
  priv->height = height;
}

static bool
exb_engine_get_f3d_option (ExbEngine    *self,
                           GValue       *value,
                           GParamSpec   *pspec)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  g_autofree const char *f3d_key = NULL;
  g_autofree f3d_string_t *f3d_closest_key = NULL;
  f3d_options_t *options = NULL;
  unsigned int distance;
  GType type;

  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);
  g_return_val_if_fail (priv->engine != NULL, FALSE);

  options = f3d_engine_get_options (priv->engine);

  if (!(f3d_key = options_map_lookup (pspec->name)))
    {
      g_message ("ExbEngine: Invalid pspec '%s' while getting option", pspec->name);
      return FALSE;
    }

  f3d_options_get_closest_option (options, f3d_key, &f3d_closest_key, &distance);

  if (!g_str_equal (f3d_key, f3d_closest_key))
    {
      g_message ("ExbEngine: Invalid f3d key '%s' while getting option, closest is '%s'", f3d_key, f3d_closest_key);
      return FALSE;
    }

  if (!f3d_options_has_value (options, f3d_key))
  {
    g_message ("ExbEngine: Key '%s' has no value, default value is returned", pspec->name);
    return TRUE;
  }

  type = G_PARAM_SPEC_VALUE_TYPE (pspec);

  if (type == G_TYPE_BOOLEAN)
    {
      g_value_set_boolean (value, f3d_options_get_as_bool (options, f3d_key));
    }
  else if (type == G_TYPE_DOUBLE)
    {
      g_value_set_double (value, f3d_options_get_as_double (options, f3d_key));
    }
  else if (type == G_TYPE_INT)
    {
      g_value_set_int (value, f3d_options_get_as_int (options, f3d_key));
    }
  else if (type == GDK_TYPE_RGBA)
    {
      g_autofree const f3d_string_t *rgba_string = NULL;
      GdkRGBA rgba;

      rgba_string = f3d_options_get_as_string_representation (options, f3d_key);

      g_message ("ExbEngine: RGBA string is '%s'", rgba_string);

      if (rgba_string)
        {
          if (!gdk_rgba_parse (&rgba, rgba_string))
            {
              g_auto(GStrv) parts = NULL;

              parts = g_strsplit (rgba_string, ",", -1);

              if (g_strv_length (parts) != 3)
                {
                  return FALSE;
                }

              rgba.red   = g_ascii_strtod (parts[0], NULL);
              rgba.green = g_ascii_strtod (parts[1], NULL);
              rgba.blue  = g_ascii_strtod (parts[2], NULL);
              rgba.alpha = 1.0;
            }

          g_value_set_boxed (value, &rgba);
        }
    }
  else if (type == G_TYPE_FILE)
    {
      g_autofree const f3d_string_t *filepath = NULL;

      filepath = f3d_options_get_as_string_representation (options, f3d_key);

      if (filepath)
        {
          g_autoptr (GFile) file = g_file_new_for_path (filepath);
          g_value_set_object (value, file);
        }
      else
        {
          g_value_set_object (value, NULL);
        }
    }

  return TRUE;
}

static bool
exb_engine_set_f3d_option (ExbEngine    *self,
                           const GValue *value,
                           GParamSpec   *pspec)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  g_autofree const char *f3d_key = NULL;
  g_autofree f3d_string_t *f3d_closest_key = NULL;
  f3d_options_t *options = NULL;
  unsigned int distance;
  GType type;

  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);
  g_return_val_if_fail (priv->engine != NULL, FALSE);

  options = f3d_engine_get_options (priv->engine);

  if (!(f3d_key = options_map_lookup (pspec->name)))
    {
      g_message ("ExbEngine: Invalid pspec '%s' while setting option", pspec->name);
      return FALSE;
    }

  f3d_options_get_closest_option (options, f3d_key, &f3d_closest_key, &distance);

  if (!g_str_equal (f3d_key, f3d_closest_key))
    {
      g_message ("ExbEngine: Invalid f3d key '%s' while getting option, closest is '%s'", f3d_key, f3d_closest_key);
      return FALSE;
    }

  type = G_PARAM_SPEC_VALUE_TYPE (pspec);

  if (type == G_TYPE_BOOLEAN)
    {
      f3d_options_set_as_bool (options, f3d_key, g_value_get_boolean (value));
    }
  else if (type == G_TYPE_DOUBLE)
    {
      f3d_options_set_as_double (options, f3d_key, g_value_get_double (value));
    }
  else if (type == G_TYPE_INT)
    {
      f3d_options_set_as_int (options, f3d_key, g_value_get_int (value));
    }
  else if (type == GDK_TYPE_RGBA)
    {
      const GdkRGBA *rgba = g_value_get_boxed (value);

      if (rgba)
        {
          g_autofree char *rgba_string = NULL;
          rgba_string = g_strdup_printf ("%lf,%lf,%lf", rgba->red, rgba->green, rgba->blue);
          f3d_options_set_as_string_representation (options, f3d_key, rgba_string);
        }
    }
  else if (type == G_TYPE_FILE)
    {
      GFile *file = g_value_get_object (value);

      if (file)
        {
          g_autofree char *filepath = g_file_get_path (file);
          f3d_options_set_as_string_representation (options, f3d_key, filepath);
        }
      else
        {
          f3d_options_set_as_string_representation (options, f3d_key, "");
        }
    }

  g_signal_emit (self, signals[SIGNAL_CHANGED], 0);
  return TRUE;
}

static void
exb_engine_get_property (GObject    *object,
                         guint       prop_id,
                         GValue     *value,
                         GParamSpec *pspec)
{
  ExbEngine *self = EXB_ENGINE (object);

  g_return_if_fail (EXB_IS_ENGINE (self));

  switch (prop_id)
    {
    case PROP_FILE:
      g_value_set_object (value, exb_engine_get_file (self));
      break;
    case PROP_SPRITES_TYPE:
      break;
    case PROP_ANTI_ALIASING_MODE:
      break;
    case PROP_BLENDING_MODE:
      break;
    case PROP_UP:
      break;
    default:
      if (!exb_engine_get_f3d_option (self, value, pspec))
        G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
exb_engine_set_property (GObject      *object,
                         guint         prop_id,
                         const GValue *value,
                         GParamSpec   *pspec)
{
  ExbEngine *self = EXB_ENGINE (object);

  g_return_if_fail (EXB_IS_ENGINE (self));

  switch (prop_id)
    {
    case PROP_FILE:
      exb_engine_set_file (self, g_value_get_object (value));
      break;
    case PROP_SPRITES_TYPE:
      break;
    case PROP_ANTI_ALIASING_MODE:
      break;
    case PROP_BLENDING_MODE:
      break;
    case PROP_UP:
      break;
    default:
      if (!exb_engine_set_f3d_option (self, value, pspec))
        G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
exb_engine_finalize (GObject *object)
{
  ExbEngine *self = EXB_ENGINE (object);
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));

  g_message ("ExbEngine: Finalizing");

  g_clear_object (&priv->file);
  g_clear_pointer (&priv->engine, f3d_engine_delete);

  G_OBJECT_CLASS (exb_engine_parent_class)->finalize (object);
}

void
_exb_engine_initialize (ExbEngine *self,
                        bool       standalone)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));

  if (standalone)
    {
      g_message ("ExbViewer: Initializing F3D with automatic (offscreen)");
      priv->engine = f3d_engine_create (true);
    }
  else if (g_getenv ("WAYLAND_DISPLAY"))
    {
      g_message ("ExbViewer: Initializing F3D with external EGL");
      priv->engine = f3d_engine_create_external_egl ();
    }
  else if (g_getenv ("DISPLAY"))
    {
      g_message ("ExbViewer: Initializing F3D with external GLX");
      priv->engine = f3d_engine_create_external_glx ();
    }

  if (!priv->engine)
    {
      g_warning ("ExbViewer: Failed to initialize F3D engine");
      return;
    }

  priv->window = f3d_engine_get_window (priv->engine);
  priv->scene = f3d_engine_get_scene (priv->engine);
  priv->camera = f3d_window_get_camera (priv->window);

  g_message ("ExbViewer: Window=%p, Scene=%p", priv->window, priv->scene);

  priv->orthographic = FALSE;
  priv->distance = 1;

  f3d_engine_autoload_plugins ();

  if (priv->file)
    _exb_engine_load_file (self, priv->file);
}

static void
exb_engine_init (ExbEngine *self G_GNUC_UNUSED)
{
  g_message ("ExbEngine: Initializing instance");
}

static void
exb_engine_class_init (ExbEngineClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = exb_engine_finalize;
  object_class->get_property = exb_engine_get_property;
  object_class->set_property = exb_engine_set_property;

  signals[SIGNAL_CHANGED] =
      g_signal_new ("changed", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST, 0,
                    NULL, NULL, g_cclosure_marshal_VOID__VOID, G_TYPE_NONE, 0);

  properties[PROP_FILE] =
      g_param_spec_object ("file",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_EXPLICIT_NOTIFY | G_PARAM_STATIC_STRINGS);

  properties[PROP_ORTHOGRAPHIC] =
      g_param_spec_boolean ("orthographic",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SHOW_GRID] =
      g_param_spec_boolean ("show-grid",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_GRID_ABSOLUTE] =
      g_param_spec_boolean ("grid-absolute",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_GRID_UNIT] =
      g_param_spec_double ("grid-unit",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_GRID_COLOR] =
      g_param_spec_boxed ("grid-color",
                          NULL, NULL,
                          GDK_TYPE_RGBA,
                          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_BLENDING] =
      g_param_spec_boolean ("blending",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_TONE_MAPPING] =
      g_param_spec_boolean ("tone-mapping",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_AMBIENT_OCCLUSION] =
      g_param_spec_boolean ("ambient-occlusion",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_ANTI_ALIASING] =
      g_param_spec_boolean ("anti-aliasing",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_HDRI_AMBIENT] =
      g_param_spec_boolean ("hdri-ambient",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_HDRI_SKYBOX] =
      g_param_spec_boolean ("hdri-skybox",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_HDRI_FILE] =
      g_param_spec_object ("hdri-file",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_BLUR_BACKGROUND] =
      g_param_spec_boolean ("blur-background",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_BLUR_COC] =
      g_param_spec_double ("blur-coc",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 20.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_LIGHT_INTENSITY] =
      g_param_spec_double ("light-intensity",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_BACKGROUND_COLOR] =
      g_param_spec_boxed ("background-color",
                          NULL, NULL,
                          GDK_TYPE_RGBA,
                          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SHOW_EDGES] =
      g_param_spec_boolean ("show-edges",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_EDGES_WIDTH] =
      g_param_spec_double ("edges-width",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_POINT_SIZE] =
      g_param_spec_double ("point-size",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SHOW_ARMATURE] =
      g_param_spec_boolean ("show-armature",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_MODEL_COLOR] =
      g_param_spec_boxed ("model-color",
                          NULL, NULL,
                          GDK_TYPE_RGBA,
                          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_MODEL_METALLIC] =
      g_param_spec_double ("model-metallic",
                           NULL, NULL,
                           0.0, 1.0, 0.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_MODEL_ROUGHNESS] =
      g_param_spec_double ("model-roughness",
                           NULL, NULL,
                           0.0, 1.0, 0.5,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_MODEL_OPACITY] =
      g_param_spec_double ("model-opacity",
                           NULL, NULL,
                           0.0, 1.0, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_TEXTURE_MATCAP] =
      g_param_spec_object ("texture-matcap",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_TEXTURE_BASE_COLOR] =
      g_param_spec_object ("texture-base-color",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_TEXTURE_EMISSIVE] =
      g_param_spec_object ("texture-emissive",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_TEXTURE_MATERIAL] =
      g_param_spec_object ("texture-material",
                           NULL, NULL,
                           G_TYPE_FILE,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_NORMAL_SCALE] =
      g_param_spec_double ("normal-scale",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_VOLUME_RENDERING] =
      g_param_spec_boolean ("volume-rendering",
                            NULL, NULL,
                            FALSE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_VOLUME_INVERSE_OPACITY] =
      g_param_spec_boolean ("volume-inverse-opacity",
                            NULL, NULL,
                            FALSE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SHOW_SPRITES] =
      g_param_spec_boolean ("show-sprites",
                            NULL, NULL,
                            FALSE,
                            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SPRITES_SIZE] =
      g_param_spec_double ("sprites-size",
                           NULL, NULL,
                           0.0, G_MAXDOUBLE, 1.0,
                           G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_SPRITES_TYPE] =
      g_param_spec_enum ("sprites-type",
                         NULL, NULL,
                         exb_sprite_type_get_type (),
                         EXB_SPRITE_TYPE_SPHERE, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_UP] =
      g_param_spec_enum ("up",
                         NULL, NULL,
                         exb_direction_get_type (),
                         EXB_DIRECTION_POSITIVE_Y, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_ANIMATION_INDEX] =
      g_param_spec_int ("animation-index",
                        NULL, NULL,
                        0, 1000, 0,
                        G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_ANTI_ALIASING_MODE] =
      g_param_spec_enum ("anti-aliasing-mode",
                         NULL, NULL,
                         exb_anti_aliasing_mode_get_type (),
                         EXB_ANTI_ALIASING_MODE_FXAA, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  properties[PROP_BLENDING_MODE] =
      g_param_spec_enum ("blending-mode",
                         NULL, NULL,
                         exb_blending_mode_get_type (),
                         EXB_BLENDING_MODE_DDP, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);

  g_object_class_install_properties (object_class, N_PROPS, properties);
}

static void
update_distance (ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  graphene_vec3_t camera_position;
  double f3d_camera_position[3];

  g_return_if_fail (EXB_IS_ENGINE (self));
  g_return_if_fail (priv->camera);

  f3d_camera_get_position (priv->camera, f3d_camera_position);
  graphene_vec3_init_from_float (&camera_position, (float *) f3d_camera_position);
  priv->distance = graphene_vec3_length (&camera_position);
}

static double
get_gimble_limit (ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  return priv->distance / 10.0;
}

/**
 * exb_engine_new_standalone:
 *
 * Returns: (transfer full): A new #ExbEngine to be used alone without a #ExbView
 */
ExbEngine *
exb_engine_new_standalone (void)
{
  ExbEngine *engine = g_object_new (EXB_TYPE_ENGINE, NULL);

  _exb_engine_initialize (engine, true);

  return engine;
}

/**
 * exb_engine_zoom:
 * @self: a #ExbEngine
 * @factor: zoom factor
 *
 */
void
exb_engine_zoom (ExbEngine *self,
                 double     factor)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));

  if (!priv->camera)
    return;

  if (priv->orthographic)
    {
      f3d_camera_zoom (priv->camera, factor);
    }
  else
    {
      f3d_camera_dolly (priv->camera, factor);
    }

  update_distance (self);
}

/**
 * exb_engine_pan:
 * @self: a #ExbEngine
 * @dx: dx factor
 * @dy: dy factor
 *
 */
void
exb_engine_pan (ExbEngine *self,
                double     dx,
                double     dy)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  double factor;

  g_return_if_fail (EXB_IS_ENGINE (self));

  if (!priv->camera)
    return;

  factor = 0.0000001 * priv->width + 0.001 * priv->distance;
  f3d_camera_pan (priv->camera, -dx * factor, dy * factor, 0);

  update_distance (self);
}

/**
 * exb_engine_rotate:
 * @self: a #ExbEngine
 * @dx: dx factor
 * @dy: dy factor
 *
 */
void
exb_engine_rotate (ExbEngine *self,
                   double     dx,
                   double     dy)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  double elevation;
  double azimuth;

  g_return_if_fail (EXB_IS_ENGINE (self));

  if (!priv->camera)
    return;

  elevation = dy * 0.5;
  azimuth = -dx * 0.5;

  f3d_camera_azimuth (priv->camera, azimuth);
  f3d_camera_elevation (priv->camera, elevation);

  update_distance (self);
}

/**
 * exb_engine_reset_camera:
 * @self: a #ExbEngine
 *
 */
void
exb_engine_reset_camera (ExbEngine *self)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_if_fail (EXB_IS_ENGINE (self));

  f3d_camera_reset_to_bounds (priv->camera, 1.0);
  update_distance (self);

  g_signal_emit (self, signals [SIGNAL_CHANGED], 0);
}

/**
 * exb_engine_rotate_with_limit:
 * @self: a #ExbEngine
 * @dx: dx factor
 * @dy: dy factor
 *
 * Rotate the view while keeping the scene pointing up
 *
 */
void
exb_engine_rotate_with_limit (ExbEngine *self,
                              double     dx,
                              double     dy)
{
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);
  double elevation;
  double azimuth;

  g_return_if_fail (EXB_IS_ENGINE (self));

  if (!priv->camera)
    return;

  elevation = dy * 0.5;
  azimuth = -dx * 0.5;

  if (priv->distance > get_gimble_limit (self) ||
     (priv->distance < get_gimble_limit (self)))
  {
    f3d_camera_elevation (priv->camera, elevation);
  }

  f3d_camera_azimuth (priv->camera, azimuth);

  update_distance (self);
}
