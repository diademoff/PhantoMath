#!/usr/bin/env python3
"""Extract every string pool in resources.arsc (global + per-package).

Photomath keeps its ~3020 solver-explanation templates in a *package* string
pool (typeChunks). No res/values/*.xml references them, so apktool never emits
them. The native solver resolves them by resource id at runtime.
"""
import struct, sys, json

U16 = lambda b, o: struct.unpack_from("<H", b, o)[0]
U32 = lambda b, o: struct.unpack_from("<I", b, o)[0]
UTF8_FLAG = 1 << 8

NAMES = {0x0001: "STRING_POOL", 0x0002: "TABLE", 0x0200: "TABLE_PACKAGE",
         0x0201: "TABLE_TYPE", 0x0202: "TABLE_TYPE_SPEC"}


def read_pool(b, off):
    count, style_count, flags, sstart, _t = struct.unpack_from("<IIIII", b, off + 8)
    is_utf8 = bool(flags & UTF8_FLAG)
    hdr = U16(b, off + 2)
    out = []
    for i in range(count):
        so = U32(b, off + hdr + 4 * i)
        p = off + sstart + so
        if is_utf8:
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
    return out, is_utf8


def walk(b, start, end, depth=0, found=None, verbose=True):
    found = found if found is not None else []
    o = start
    while o + 8 <= end:
        typ, hdr, size = struct.unpack_from("<HHI", b, o)
        if size < 8 or o + size > end:
            break
        if verbose:
            print("  " * depth + f"@{o} 0x{typ:04x} {NAMES.get(typ,'?'):<16} hdr={hdr} size={size}")
        if typ == 0x0001:
            try:
                s, u8 = read_pool(b, o)
                found.append({"offset": o, "utf8": u8, "strings": s})
                if verbose:
                    print("  " * depth + f"    -> {len(s)} strings")
            except Exception as e:
                print("  " * depth + f"    !! {e}")
        elif typ in (0x0002, 0x0200):
            # container: children start right after this chunk's header
            walk(b, o + hdr, o + size, depth + 1, found, verbose)
        o += size
    return found


if __name__ == "__main__":
    b = open(sys.argv[1], "rb").read()
    tbl_hdr = U16(b, 2)
    pools = walk(b, 12 + (tbl_hdr - 12), len(b))
    if len(sys.argv) > 2:
        json.dump(pools, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
        print("wrote", sys.argv[2], "pools:", [(p["offset"], len(p["strings"])) for p in pools])