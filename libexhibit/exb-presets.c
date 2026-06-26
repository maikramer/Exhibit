/*
 * exb-presets.c
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

#include "config.h"

#include "exb-presets.h"
#include "exb-debug.h"

struct _ExbPresets
{
  GObject parent_instance;

  GListStore *store;
  GPtrArray *search_paths;
};

static void exb_presets_list_model_init (GListModelInterface *iface);

G_DEFINE_FINAL_TYPE_WITH_CODE (ExbPresets, exb_presets, G_TYPE_OBJECT,
                               G_IMPLEMENT_INTERFACE (G_TYPE_LIST_MODEL,
                                                      exb_presets_list_model_init))

static GType
exb_presets_get_item_type (GListModel *model)
{
  return EXB_TYPE_PRESET;
}

static guint
exb_presets_get_n_items (GListModel *model)
{
  return g_list_model_get_n_items (G_LIST_MODEL (EXB_PRESETS (model)->store));
}

static gpointer
exb_presets_get_item (GListModel *model,
                      guint       position)
{
  return g_list_model_get_item (G_LIST_MODEL (EXB_PRESETS (model)->store), position);
}

static void
exb_presets_list_model_init (GListModelInterface *iface)
{
  iface->get_item_type = exb_presets_get_item_type;
  iface->get_n_items   = exb_presets_get_n_items;
  iface->get_item      = exb_presets_get_item;
}

static void
exb_presets_finalize (GObject *object)
{
  ExbPresets *self = EXB_PRESETS (object);

  g_clear_pointer (&self->search_paths, g_ptr_array_unref);

  G_OBJECT_CLASS (exb_presets_parent_class)->finalize (object);
}

static void
exb_presets_class_init (ExbPresetsClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = exb_presets_finalize;
}

static void
exb_presets_scan_paths (ExbPresets *self)
{
  for (guint i = 0; i < self->search_paths->len; i++)
    {
      const gchar *path = g_ptr_array_index (self->search_paths, i);
      g_autoptr (GDir) dir = NULL;
      g_autoptr (GError) error = NULL;
      const gchar *filename;

      dir = g_dir_open (path, 0, &error);
      if (dir == NULL)
        {
          g_warning ("Could not open path '%s': %s", path, error->message);
          continue;
        }

      while ((filename = g_dir_read_name (dir)) != NULL)
        {
          g_autofree gchar *full_path = NULL;
          g_autoptr (GFile) file = NULL;
          g_autoptr (ExbPreset) preset = NULL;

          if (!g_str_has_suffix (filename, ".ini"))
            continue;

          full_path = g_build_filename (path, filename, NULL);
          file = g_file_new_for_path (full_path);
          preset = exb_preset_new_from_file (file);

          if (preset == NULL)
            {
              g_warning ("Could not load preset '%s'", full_path);
              continue;
            }

          g_list_store_append (self->store, g_steal_pointer (&preset));
        }
    }
}

static void
on_store_items_changed (GListModel *model,
                        guint       position,
                        guint       removed,
                        guint       added,
                        ExbPresets *self)
{
  g_list_model_items_changed (G_LIST_MODEL (self), position, removed, added);
}

static void
exb_presets_init (ExbPresets *self)
{
  g_autofree gchar *user_path = NULL;

  self->search_paths = g_ptr_array_new_with_free_func (g_free);
#ifndef DATADIR
  user_path = g_build_filename (g_get_user_data_dir (),
                                "libexhibit",
                                "presets",
                                NULL);
#else
  user_path = g_build_filename (DATADIR,
                                "libexhibit",
                                "presets",
                                NULL);
#endif
  g_ptr_array_add (self->search_paths, g_steal_pointer (&user_path));

  self->store = g_list_store_new (EXB_TYPE_PRESET);

  exb_presets_scan_paths (self);

  g_signal_connect_object (self->store,
                           "items-changed",
                           G_CALLBACK (on_store_items_changed),
                           self,
                           G_CONNECT_DEFAULT);
}

/**
 * exb_presets_new:
 *
 * Returns: (transfer full): (type ExbPresets) A new #ExbPresets.
 */
ExbPresets *
exb_presets_new (void)
{
  return g_object_new (EXB_TYPE_PRESETS,
                       NULL);
}

/**
 * exb_presets_new_with_paths:
 * @paths: (array zero-terminated=1) (element-type utf8): A list of paths.
 *
 * Returns: (transfer full): (type ExbPresets) A new #ExbPresets.
 */
ExbPresets *
exb_presets_new_with_paths (const char * const *paths)
{
  ExbPresets *presets = g_object_new (EXB_TYPE_PRESETS, NULL);

  if (paths != NULL)
    {
      for (gint i = 0; paths[i] != NULL; i++)
        g_ptr_array_add (presets->search_paths, g_strdup (paths[i]));
    }

  return presets;
}

/**
 * exb_presets_lookup:
 * @self: a #ExbPresets
 * @name: the preset name to look up
 *
 * Returns: (transfer none) (nullable): The matching #ExbPreset, or %NULL
 */
ExbPreset *
exb_presets_lookup (ExbPresets *self,
                    const char *name)
{
  g_return_val_if_fail (EXB_IS_PRESETS (self), NULL);
  g_return_val_if_fail (name != NULL, NULL);

  for (guint i = 0; i < g_list_model_get_n_items (G_LIST_MODEL (self->store)); i++)
    {
      g_autoptr (ExbPreset) preset = g_list_model_get_item (G_LIST_MODEL (self->store), i);
      g_autoptr (GString) cmp_name = NULL;
      const char *preset_name;

      preset_name = exb_preset_get_name (preset);

      cmp_name = g_string_new_take (g_ascii_strdown (preset_name, -1));
      g_string_replace (cmp_name, " ", "_", 0);

      g_message("%s : %s", cmp_name->str, preset_name);

      if (g_strcmp0 (name, cmp_name->str) == 0)
        return preset;
    }

  return NULL;
}

/**
 * exb_presets_get_default_for:
 * @self: a #ExbPresets
 * @filename: the filename
 *
 * Returns: (transfer none) (nullable): The matching #ExbPreset, or %NULL
 */
ExbPreset *
exb_presets_get_default_for (ExbPresets *self,
                             const char *filename)
{
  g_return_val_if_fail (EXB_IS_PRESETS (self), NULL);
  g_return_val_if_fail (filename != NULL, NULL);

  for (guint i = 0; i < g_list_model_get_n_items (G_LIST_MODEL (self->store)); i++)
    {
      g_autoptr (ExbPreset) preset = g_list_model_get_item (G_LIST_MODEL (self->store), i);
      g_autoptr (GRegex) match_regex = NULL;
      const char *preset_formats;

      preset_formats = exb_preset_get_formats (preset);

      g_message ("%s, %s", preset_formats, filename);

      match_regex = g_regex_new (preset_formats, G_REGEX_DEFAULT, G_REGEX_MATCH_DEFAULT, NULL);

      if (match_regex && g_regex_match (match_regex, filename, 0, NULL))
        return preset;
    }

  return NULL;
}
