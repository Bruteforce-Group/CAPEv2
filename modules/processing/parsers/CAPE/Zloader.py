# Copyright (C) 2020 Kevin O'Reilly (kevoreilly@gmail.com)
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

DESCRIPTION = "Zloader configuration parser"
AUTHOR = "kevoreilly"

import logging
import struct

import pefile
import yara
from Cryptodome.Cipher import ARC4

log = logging.getLogger(__name__)

rule_source = """
rule Zloader
{
    meta:
        author = "kevoreilly"
        description = "Zloader Payload"
        cape_type = "Zloader Payload"
    strings:
        $rc4_init = {31 [1-3] 66 C7 8? 00 01 00 00 00 00 90 90 [0-5] 8? [5-90] 00 01 00 00 [0-15] (74|75)}
        $decrypt_conf = {e8 ?? ?? ?? ?? e8 ?? ?? ?? ?? e8 ?? ?? ?? ?? e8 ?? ?? ?? ?? 68 ?? ?? ?? ?? 68 ?? ?? ?? ?? e8 ?? ?? ?? ?? 83 c4 08 e8 ?? ?? ?? ??}
    condition:
        uint16(0) == 0x5A4D and any of them
}
"""
MAX_STRING_SIZE = 32

yara_rules = yara.compile(source=rule_source)


def decrypt_rc4(key, data):
    cipher = ARC4.new(key)
    return cipher.decrypt(data)


def string_from_offset(data, offset):
    return data[offset : offset + MAX_STRING_SIZE].split(b"\0", 1)[0]


def extract_config(filebuf):
    end_config = {}
    pe = pefile.PE(data=filebuf, fast_load=False)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    matches = yara_rules.match(data=filebuf)
    if not matches:
        return
    for match in matches:
        if match.rule != "Zloader":
            continue
        for item in match.strings:
            if "$decrypt_conf" in item.identifier:
                decrypt_conf = item.instances[0].offset + 21
    va = struct.unpack("I", filebuf[decrypt_conf : decrypt_conf + 4])[0]
    key = string_from_offset(filebuf, pe.get_offset_from_rva(va - image_base))
    data_offset = pe.get_offset_from_rva(struct.unpack("I", filebuf[decrypt_conf + 5 : decrypt_conf + 9])[0] - image_base)
    enc_data = filebuf[data_offset:].split(b"\0\0", 1)[0]
    raw = decrypt_rc4(key, enc_data)
    items = list(filter(None, raw.split(b"\x00\x00")))
    end_config["Botnet name"] = items[1].lstrip(b"\x00")
    end_config["Campaign ID"] = items[2]
    for item in items:
        item = item.lstrip(b"\x00")
        if item.startswith(b"http"):
            end_config.setdefault("address", []).append(item)
        elif len(item) == 16:
            end_config["RC4 key"] = item
    return end_config
