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

#include <f3d/camera_c_api.h>
#include <f3d/engine_c_api.h>
#include <f3d/image_c_api.h>
#include <f3d/interactor_c_api.h>
#include <f3d/log_c_api.h>
#include <f3d/options_c_api.h>
#include <f3d/scene_c_api.h>
#include <f3d/utils_c_api.h>
#include <f3d/window_c_api.h>

G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_engine_t, f3d_engine_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_context_t, f3d_context_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_image_t, f3d_image_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_options_t, f3d_options_delete)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (f3d_light_state_t, f3d_light_state_free)

G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_color_t, (void (*) (f3d_color_t *)) NULL)
G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_light_state_t, f3d_light_state_free)
G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_colormap_t, f3d_colormap_free)
G_DEFINE_AUTO_CLEANUP_CLEAR_FUNC (f3d_reader_info_t, f3d_engine_free_readers_info)

typedef struct
{
  f3d_engine_t *engine;
  f3d_window_t *window;
  f3d_scene_t *scene;
  f3d_camera_t *camera;

  bool orthographic;

  GFile *file;
} ExbEnginePrivate;

G_DEFINE_TYPE_WITH_PRIVATE (ExbEngine, exb_engine, G_TYPE_OBJECT)

enum
{
  PROP_0,
  PROP_FILE,
  PROP_ORTHOGRAPHIC,
  N_PROPS
};

static GParamSpec *properties[N_PROPS];

/**
 * exb_engine_get_allowed_extensions:
 *
 * Returns: (transfer full): A list of strings
 */
char **
exb_engine_get_allowed_extensions (void)
{
  g_autofree f3d_reader_info_t *readers = NULL;
  GPtrArray *array;
  int count = 0;

  readers = f3d_engine_get_readers_info (&count);
  if (!readers)
    return NULL;

  array = g_ptr_array_new_with_free_func (g_free);

  for (int i = 0; i < count; i++)
    {
      if (readers[i].extensions)
        {
          for (char **ext = readers[i].extensions; *ext; ext++)
            {
              g_ptr_array_add (array, g_strdup (*ext));
            }
        }
    }

  g_ptr_array_add (array, NULL);
  return (char **) g_ptr_array_free (array, FALSE);
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

  g_message ("ExbEngine: Loading file: %s", g_file_get_path (file));
  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);

  if (!priv->scene)
    return FALSE;

  if (!f3d_scene_supports (priv->scene, g_file_get_path (file)))
    return FALSE;

  f3d_scene_clear (priv->scene);
  f3d_scene_add (priv->scene, g_file_get_path (file));

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
 * Returns: (transfer full): A GFile
 */
GFile *
exb_engine_get_file(ExbEngine *self)
{
  g_return_val_if_fail (EXB_IS_ENGINE (self), NULL);

  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  return priv->file;
}

gboolean
exb_engine_render (ExbEngine *self)
{
  g_return_val_if_fail (EXB_IS_ENGINE (self), false);

  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  g_return_val_if_fail (priv->window != NULL, false);

  f3d_window_render (priv->window);

  return true;
}

void
exb_engine_set_size (ExbEngine *self,
                     uint       width,
                     uint       height)
{
  g_return_if_fail (EXB_IS_ENGINE (self));

  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  f3d_window_set_size (priv->window, width, height);
}

bool
exb_engine_get_orthographic (ExbEngine *self)
{
  g_return_val_if_fail (EXB_IS_ENGINE (self), FALSE);

  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  return priv->orthographic;
}

void
exb_engine_set_orthographic (ExbEngine *self,
                             bool       orthographic)
{
  g_return_if_fail (EXB_IS_ENGINE (self));

  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

  priv->orthographic = orthographic;
  g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_ORTHOGRAPHIC]);
}

static void
exb_engine_get_property (GObject    *object,
                         guint       prop_id,
                         GValue     *value,
                         GParamSpec *pspec G_GNUC_UNUSED)
{
  ExbEngine *self = EXB_ENGINE (object);

  switch (prop_id)
    {
    case PROP_FILE:
      g_value_set_object (value, exb_engine_get_file (self));
      break;
    case PROP_ORTHOGRAPHIC:
      g_value_set_boolean (value, exb_engine_get_orthographic (self));
    default:
      break;
    }
}

static void
exb_engine_set_property (GObject      *object,
                         guint         prop_id,
                         const GValue *value,
                         GParamSpec   *pspec G_GNUC_UNUSED)
{
  ExbEngine *self = EXB_ENGINE (object);

  switch (prop_id)
    {
    case PROP_FILE:
      exb_engine_set_file (self, g_value_get_object (value));
      break;
    case PROP_ORTHOGRAPHIC:
      exb_engine_set_orthographic (self, g_value_get_boolean (value));
    default:
      break;
    }
}

static void
exb_engine_finalize (GObject *object)
{
  g_message ("ExbEngine: Finalizing");
  ExbEngine *self = EXB_ENGINE (object);
  ExbEnginePrivate *priv = exb_engine_get_instance_private (self);

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

  priv->orthographic = FALSE;

  f3d_engine_autoload_plugins ();
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

  g_object_class_install_properties (object_class, N_PROPS, properties);
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
}
