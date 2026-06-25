/*
 * exb-preset.c
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

#include "exb-preset.h"
#include "exb-engine.h"
#include "exb-debug.h"

struct _ExbPreset
{
  GObject parent_instance;

  char *name;
  GHashTable *properties;
};

G_DEFINE_FINAL_TYPE (ExbPreset, exb_preset, G_TYPE_OBJECT)

enum {
  PROP_0,
  PROP_NAME,
  N_PROPS
};

static GParamSpec *properties[N_PROPS];

static void
exb_preset_finalize (GObject *object)
{
  ExbPreset *self = EXB_PRESET (object);

  g_clear_pointer (&self->name, g_free);
  g_clear_pointer (&self->properties, g_hash_table_unref);

  G_OBJECT_CLASS (exb_preset_parent_class)->finalize (object);
}

static void
exb_preset_get_property (GObject    *object,
                         guint       prop_id,
                         GValue     *value,
                         GParamSpec *pspec)
{
  ExbPreset *self = EXB_PRESET (object);

  switch (prop_id)
    {
    case PROP_NAME:
      g_value_set_string (value, self->name);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
    }
}

static void
exb_preset_set_property (GObject      *object,
                         guint         prop_id,
                         const GValue *value,
                         GParamSpec   *pspec)
{
  ExbPreset *self = EXB_PRESET (object);

  switch (prop_id)
    {
    case PROP_NAME:
      exb_preset_set_name (self, g_value_get_string (value));
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
    }
}

static void
exb_preset_class_init (ExbPresetClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = exb_preset_finalize;
  object_class->get_property = exb_preset_get_property;
  object_class->set_property = exb_preset_set_property;

  properties[PROP_NAME] =
    g_param_spec_string ("name",
                         NULL, NULL,
                         NULL,
                         G_PARAM_READWRITE | G_PARAM_EXPLICIT_NOTIFY | G_PARAM_STATIC_STRINGS);

  g_object_class_install_properties (object_class, N_PROPS, properties);
}

static void
exb_preset_init (ExbPreset *self)
{
  self->properties = g_hash_table_new_full (g_str_hash,
                                            g_str_equal,
                                            g_free,
                                            (GDestroyNotify) g_variant_unref);
}

ExbPreset *
exb_preset_new (void)
{
  return g_object_new (EXB_TYPE_PRESET, NULL);
}

ExbPreset *
exb_preset_new_from_file (GFile *file)
{
  g_return_val_if_fail (G_IS_FILE (file), NULL);

  return NULL;
}

ExbPreset *
exb_preset_new_from_engine (ExbEngine  *engine,
                            const char *name)
{
  g_return_val_if_fail (EXB_IS_ENGINE (engine), NULL);
  g_return_val_if_fail (name != NULL, NULL);

  return NULL;
}

const char *
exb_preset_get_name (ExbPreset *self)
{
  g_return_val_if_fail (EXB_IS_PRESET (self), NULL);

  return self->name;
}

void
exb_preset_set_name (ExbPreset  *self,
                     const char *name)
{
  g_return_if_fail (EXB_IS_PRESET (self));

  if (g_set_str (&self->name, name))
    g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_NAME]);
}

void
exb_preset_apply (ExbPreset *self,
                  ExbEngine *engine)
{
  g_return_if_fail (EXB_IS_PRESET (self));
  g_return_if_fail (EXB_IS_ENGINE (engine));
}

void
exb_preset_save (ExbPreset  *self,
                 GFile      *file)
{
  g_return_if_fail (EXB_IS_PRESET (self));
  g_return_if_fail (G_IS_FILE (file));
}
