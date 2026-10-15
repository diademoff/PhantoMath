#!/usr/bin/env python3
"""Full resources.arsc resolver: resource id -> name -> localized string value.

Recovers Photomath's solver-explanation templates. They live in the table as
TYPE_STRING resources named `step_<key>` and are read at runtime via
Resources.getIdentifier("step_" + key, "string", pkg) -- see
c/a/a/l/g/c0.java. No res/values/*.xml references them, so apktool never emits
them; only a raw table walk finds them.
"""
import struct, sys, json, collections

U8 = lambda b, o: b[o]
U16 = lambda b, o: struct.unpack_from("<H", b, o)[0]
U32 = lambda b, o: struct.unpack_from("<I", b, o)[0]

TYPE_NULL, TYPE_REFERENCE, TYPE_STRING = 0x00, 0x01, 0x03
TYPE_INT_DEC = 0x10


def read_pool(b, off):
    hdr = U16(b, off + 2)
    count, _sc, flags, sstart, _t = struct.unpack_from("<IIIII", b, off + 8)
    utf8 = bool(flags & (1 << 8))
    out = []
    for i in range(count):
        p = off + sstart + U32(b, off + hdr + 4 * i)
        if utf8:
            n1 = b[p]; p += 1
            if n1 & 0x80: p += 1
            n2 = b[p]; p += 1
            if n2 & 0x80:
                n2 = ((n2 & 0x7F) << 8) | b[p]; p += 1
            out.append(b[p:p + n2].decode("utf-8", "replace"))
        else:
            n = U16(b, p); p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | U16(b, p); p += 2
            out.append(b[p:p + n * 2].decode("utf-16-le", "replace"))
    return out


def parse_config(b, off):
    """Return (lang, country, density, sdk) from ResTable_config."""
    size = U16(b, off)
    lang = b[off + 8:off + 10].decode("ascii", "replace").rstrip("\x00")
    country = b[off + 10:off + 12].decode("ascii", "replace").rstrip("\x00")
    density = U16(b, off + 12)
    sdk = U16(b, off + 24)
    return (lang, country, density, sdk)


def chunks(b, start, end):
    o = start
    while o + 8 <= end:
        t, h, s = struct.unpack_from("<HHI", b, o)
        if s < 8 or o + s > end:
            break
        yield o, t, h, s
        o += s


def main(path):
    b = open(path, "rb").read()
    pool = read_pool(b, 12)                     # global string pool (values)
    global_pool_size = U32(b, 12 + 4)          # packages start right after it
    pkg_start = 12 + global_pool_size
    packages = []
    for poff, ptype, phdr, psize in chunks(b, pkg_start, len(b)):
        if ptype != 0x0200:
            continue
        pkg_id = U32(b, poff + 8)
        name = b[poff + 12:poff + 12 + 256].decode("utf-16-le", "replace").rstrip("\x00")
        # ResTable_package: typeStrings at +268, keyStrings at +276 (both offsets
        # from the package chunk start). Type names and entry key names live in
        # separate pools -- using one for both silently loses every resource.
        type_str_off = poff + U32(b, poff + 268)
        key_str_off = poff + U32(b, poff + 276)
        typenames = read_pool(b, type_str_off)[:U32(b, type_str_off + 8)]
        keynames = read_pool(b, key_str_off)

        # resId -> {locale -> (name, value)}
        resources = collections.defaultdict(dict)
        for o, t, h, s in chunks(b, poff + phdr, poff + psize):
            if t != 0x0201:                     # ResTable_type
                continue
            res_type_id = U8(b, o + 8)
            flags = U8(b, o + 9)
            entry_count = U32(b, o + 12)
            entries_start = U32(b, o + 16)
            cfg = parse_config(b, o + 20)
            lang = cfg[0] or "default"
            type_name = typenames[res_type_id - 1] if res_type_id <= len(typenames) else f"t{res_type_id}"
            # This aapt2 build does not use the AOSP ResTable_entry layout.
            # It writes a flat u32 offset array at headerSize (one word per
            # entry) and, at entriesStart, an array of 16-byte records:
            #   { uint32 entry_size(=8); uint32 key; Res_value value }
            # i.e. the Res_value is inlined right after an 8-byte entry header.
            # Verified against step_animation_algtiles_draw_empty_yellow and
            # abc_action_bar_home_description ("Navigate home").
            offsets_at = o + h
            entries_at = o + entries_start
            for slot in range(entry_count):
                if offsets_at + 4 * slot + 4 > len(b):
                    break
                doff = U32(b, offsets_at + 4 * slot)
                eo = entries_at + doff
                if eo + 16 > len(b):
                    continue
                esize = U32(b, eo)
                key = U32(b, eo + 4)
                if esize < 8:
                    continue
                vsize, _r0, dtype, ddata = struct.unpack_from("<HBBI", b, eo + 8)
                if dtype != TYPE_STRING:
                    continue
                if key >= len(keynames):
                    continue
                val = pool[ddata] if ddata < len(pool) else ""
                rid = 0x7f000000 | (pkg_id << 24) | (res_type_id << 16) | key
                resources[rid][lang] = (keynames[key], val)
        packages.append({"id": pkg_id, "name": name,
                         "resources": {str(k): v for k, v in resources.items()}})
        print(f"package 0x{pkg_id:02x} {name}: {len(resources)} string resources", file=sys.stderr)
    return packages


if __name__ == "__main__":
    pkgs = main(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        json.dump(pkgs, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        print("wrote", out, file=sys.stderr)

    # quick report on step_* strings
    allres = {}
    for p in pkgs:
        for rid, langs in p["resources"].items():
            for lang, (nm, val) in langs.items():
                allres.setdefault(nm, {})[lang] = val
    steps = {k: v for k, v in allres.items() if k.startswith("step_")}
    print(f"\nstep_* resources: {len(steps)}", file=sys.stderr)
    langs = collections.Counter()
    for v in steps.values():
        for l in v:
            langs[l] += 1
    print("locales:", dict(langs), file=sys.stderr)
    for k in list(steps)[:8]:
        print(" ", k, "->", {l: t[:70] for l, t in steps[k].items()}, file=sys.stderr)