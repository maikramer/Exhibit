#!/usr/bin/python3

# thumbnailer.py
#
# Copyright 2026 Nokse <nokse@posteo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import asyncio
import gi

gi.require_version('Exb', '0')

from gi.repository import Gio, Exb
from gi.events import GLibEventLoopPolicy

asyncio.set_event_loop_policy(GLibEventLoopPolicy())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate thumbnails for 3D models')
    parser.add_argument('input',  type=str, help='Path to input file')
    parser.add_argument('output', type=str, help='Path to output png thumbnail')
    parser.add_argument('size',   type=int, help='Thumbnail image size')
    arguments = parser.parse_args()

    async def main():
        file = Gio.File.new_for_path(arguments.input)
        engine = Exb.Engine.new_standalone()
        presets = Exb.Presets.new()
        preset = presets.get_default_for(file.get_path())
        engine.apply_preset(preset)
        await engine.load_file(file)
        engine.set_size(arguments.size, arguments.size)
        texture = engine.render_texture()
        texture.save_to_png(arguments.output)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
