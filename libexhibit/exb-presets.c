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

#include "exb-presets.h"
#include "exb-debug.h"

struct _ExbPresets
{
  GObject parent_instance;

  GListStore *store;
  char      **search_paths;
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

  g_clear_pointer (&self->search_paths, g_strfreev);

  G_OBJECT_CLASS (exb_presets_parent_class)->finalize (object);
}

static void
exb_presets_class_init (ExbPresetsClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = exb_presets_finalize;
}

static void
exb_presets_init (ExbPresets *self)
{
  self->store = g_list_store_new (EXB_TYPE_PRESET);

  g_signal_connect_object (self->store,
                           "items-changed",
                           G_CALLBACK (g_list_model_items_changed),
                           self,
                           G_CONNECT_SWAPPED);
}

/**
 * exb_presets_new:
 *
 * Returns: (transfer full): A new #ExbPresets
 */
ExbPresets *
exb_presets_new (void)
{
  return g_object_new (EXB_TYPE_PRESETS,
                       "item-type", EXB_TYPE_PRESET,
                       NULL);
}

/**
 * exb_presets_add_search_path:
 * @self: a #ExbPresets
 * @path: a directory or filename to search for presets
 *
 * Adds a single path to the search path list and loads any presets found there.
 */
void
exb_presets_add_search_path (ExbPresets *self,
                             const char *path)
{
  EXB_ENTRY;

  g_return_if_fail (EXB_IS_PRESETS (self));
  g_return_if_fail (path != NULL);

  EXB_EXIT;
}

/**
 * exb_presets_set_search_path:
 * @self: a #ExbPresets
 * @paths: (array zero-terminated=1): list of directories or filenames
 *
 * Replaces the current search paths and reloads all presets.
 */
void
exb_presets_set_search_path (ExbPresets         *self,
                             const char * const *paths)
{
  EXB_ENTRY;

  g_return_if_fail (EXB_IS_PRESETS (self));
  g_return_if_fail (paths != NULL);

  EXB_EXIT;
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

  return NULL;
}
