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
#include "exb-enums.h"

#define PRESET_GROUP   "preset"
#define GENERAL_GROUP  "general"

struct _ExbPreset
{
  GObject parent_instance;

  gchar *name;
  gchar *formats;
  GHashTable *properties;
};

G_DEFINE_FINAL_TYPE (ExbPreset, exb_preset, G_TYPE_OBJECT)

enum {
  PROP_0,
  PROP_NAME,
  PROP_FORMATS,
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

    case PROP_FORMATS:
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

    case PROP_FORMATS:
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

  properties[PROP_FORMATS] =
    g_param_spec_string ("formats",
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

static void
exb_preset_load_from_key_file (ExbPreset  *self,
                               GKeyFile   *key_file)
{
  g_autofree gchar *name = NULL;
  g_autofree gchar *formats = NULL;
  g_auto(GStrv) keys = NULL;
  gsize n_keys = 0;

  EXB_ENTRY;

  name = g_key_file_get_string (key_file, GENERAL_GROUP, "name", NULL);
  if (name)
    exb_preset_set_name (self, name);

  formats = g_key_file_get_string (key_file, GENERAL_GROUP, "formats", NULL);
  if (!g_set_str (&self->formats, formats))
    {
      EXB_EXIT;
    }

  if (!g_key_file_has_group (key_file, PRESET_GROUP))
    EXB_EXIT;

  keys = g_key_file_get_keys (key_file, PRESET_GROUP, &n_keys, NULL);
  if (!keys)
    EXB_EXIT;

  for (gsize i = 0; i < n_keys; i++)
  {
    GObjectClass *klass = NULL;
    GParamSpec *pspec = NULL;
    GValue value = G_VALUE_INIT;
    GValue *heap_value = NULL;
    GType type = G_TYPE_INVALID;
    g_autofree gchar *str_val = NULL;

    klass = g_type_class_ref (EXB_TYPE_ENGINE);
    pspec = g_object_class_find_property (klass, keys[i]);
    g_type_class_unref (klass);

    if (!pspec)
      continue;

    type = pspec->value_type;

    if (type == G_TYPE_INT)
      {
        gint v = g_key_file_get_integer (key_file, PRESET_GROUP, keys[i], NULL);
        g_value_init (&value, G_TYPE_INT);
        g_value_set_int (&value, v);
      }
    else if (type == G_TYPE_BOOLEAN)
      {
        gboolean v = g_key_file_get_boolean (key_file, PRESET_GROUP, keys[i], NULL);
        g_value_init (&value, G_TYPE_BOOLEAN);
        g_value_set_boolean (&value, v);
      }
    else if (type == G_TYPE_DOUBLE)
      {
        gdouble v = g_key_file_get_double (key_file, PRESET_GROUP, keys[i], NULL);
        g_value_init (&value, G_TYPE_DOUBLE);
        g_value_set_double (&value, v);
      }
    else if (type == G_TYPE_STRING)
      {
        str_val = g_key_file_get_string (key_file, PRESET_GROUP, keys[i], NULL);
        g_value_init (&value, G_TYPE_STRING);
        g_value_set_string (&value, str_val);
      }
    else if (type == GDK_TYPE_RGBA)
      {
        GdkRGBA rgba;

        str_val = g_key_file_get_string (key_file, PRESET_GROUP, keys[i], NULL);
        if (!str_val || !gdk_rgba_parse (&rgba, str_val))
          continue;
        g_value_init (&value, GDK_TYPE_RGBA);
        g_value_set_boxed (&value, &rgba);
      }
    else if (type == G_TYPE_FILE)
      {
        g_autoptr (GFile) file = NULL;

        str_val = g_key_file_get_string (key_file, PRESET_GROUP, keys[i], NULL);
        file = str_val ? g_file_new_for_path (str_val) : NULL;
        g_value_init (&value, G_TYPE_FILE);
        g_value_set_object (&value, file);
      }
    else if ((type == EXB_TYPE_ANTI_ALIASING) ||
             (type == EXB_TYPE_BLENDING)      ||
             (type == EXB_TYPE_SPRITES)       ||
             (type == EXB_TYPE_DIRECTION))
      {
        g_autoptr (GEnumClass) enum_class = NULL;
        GEnumValue *enum_value = NULL;

        str_val = g_key_file_get_string (key_file, PRESET_GROUP, keys[i], NULL);
        if (!str_val)
          continue;
        enum_class = g_type_class_ref (type);
        enum_value = g_enum_get_value_by_nick (enum_class, str_val);
        if (!enum_value)
          {
            g_warning ("Unknown enum nick '%s' for property '%s'", str_val, keys[i]);
            continue;
          }
        g_value_init (&value, type);
        g_value_set_enum (&value, enum_value->value);
      }
    else
      {
        g_warning ("Unsupported property type '%s' for key '%s'", g_type_name (type), keys[i]);
        continue;
      }

    heap_value = g_new0 (GValue, 1);
    g_value_init (heap_value, G_VALUE_TYPE (&value));
    g_value_copy (&value, heap_value);
    g_value_unset (&value);

    g_hash_table_insert (self->properties, g_strdup (keys[i]), heap_value);
  }
}

ExbPreset *
exb_preset_new_from_file (GFile *file)
{
  ExbPreset *self;
  g_autofree gchar *path = NULL;
  g_autoptr (GError) error = NULL;
  g_autoptr (GKeyFile) key_file = NULL;

  EXB_ENTRY;

  g_return_val_if_fail (G_IS_FILE (file), NULL);

  path = g_file_get_path (file);
  key_file = g_key_file_new ();

  if (!g_key_file_load_from_file (key_file, path, G_KEY_FILE_NONE, &error))
    {
      g_warning ("Failed to load preset from '%s': %s", path, error->message);
      EXB_RETURN (NULL);
    }

  self = g_object_new (EXB_TYPE_PRESET, NULL);
  exb_preset_load_from_key_file (self, key_file);

  EXB_RETURN (self);
}

ExbPreset *
exb_preset_new_from_engine (ExbEngine  *engine,
                            const gchar *name)
{
  g_return_val_if_fail (EXB_IS_ENGINE (engine), NULL);
  g_return_val_if_fail (name != NULL, NULL);

  return NULL;
}

const gchar *
exb_preset_get_name (ExbPreset *self)
{
  g_return_val_if_fail (EXB_IS_PRESET (self), NULL);

  return self->name;
}

void
exb_preset_set_name (ExbPreset  *self,
                     const gchar *name)
{
  g_return_if_fail (EXB_IS_PRESET (self));

  if (g_set_str (&self->name, name))
    g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_NAME]);
}

const gchar *
exb_preset_get_formats (ExbPreset *self)
{
  g_return_val_if_fail (EXB_IS_PRESET (self), NULL);

  return self->formats;
}

void
exb_preset_set_formats (ExbPreset  *self,
                        const gchar *formats)
{
  g_return_if_fail (EXB_IS_PRESET (self));

  if (g_set_str (&self->formats, formats))
    g_object_notify_by_pspec (G_OBJECT (self), properties[PROP_FORMATS]);
}

static void
apply_preset_property (const gchar *key,
                       GValue     *value,
                       ExbEngine  *engine)
{
  g_message ("Key: %s", key);
  g_object_set_property (G_OBJECT (engine), key, value);
}

bool
_exb_preset_apply (ExbPreset *self,
                   ExbEngine *engine)
{
  EXB_ENTRY;

  g_return_val_if_fail (EXB_IS_PRESET (self), FALSE);
  g_return_val_if_fail (EXB_IS_ENGINE (engine), FALSE);

  g_hash_table_foreach (self->properties,
                        (GHFunc)apply_preset_property,
                        engine);

  // TODO reset other properties

  EXB_RETURN (TRUE);
}
