#!/usr/bin/env python3
import re, sys
from pathlib import Path

def fix_enum_literals(text: str) -> str:
    lines = text.splitlines(True)
    out = []
    in_enum = False
    enum_name = None
    for ln in lines:
        if not in_enum:
            m = re.match(r'\s*typedef\s+enum\s+([A-Za-z0-9_]+)\s*\{', ln)
            if m:
                in_enum = True
                enum_name = m.group(1)
                out.append(ln); continue
            out.append(ln)
        else:
            if enum_name and re.match(r'\s*}\s*e_' + re.escape(enum_name) + r'\s*;', ln):
                in_enum = False
                enum_name = None
                out.append(ln); continue
            if enum_name:
                ln = re.sub(r'\b' + re.escape(enum_name) + r'_t\b(?=\s*=)', enum_name + '__t', ln)
            out.append(ln)
    return "".join(out)

def main():
    d = Path(sys.argv[1]).resolve()
    changed = 0
    for f in list(d.glob("*.h")) + list(d.glob("*.c")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        new = fix_enum_literals(txt)
        if new != txt:
            f.write_text(new, encoding="utf-8")
            changed += 1
    print(changed)
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: fix_asn1_enum_collision.py <generated_dir>", file=sys.stderr)
        sys.exit(2)
    main()
