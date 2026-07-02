"""Scan a Spectre model library to help build a PDK descriptor.

Finds corner sections and BSIM MOS models (with polarity) by reading the
lib and the model files it includes (one level of include following).
"""
import os
import re

_SECTION = re.compile(r"^\s*section\s+(\S+)")
_MODEL = re.compile(r"^\s*(?:inline\s+)?model\s+(\w+)\s+bsim\w*\s+type\s*=\s*([np])",
                    re.IGNORECASE)
_INCLUDE = re.compile(r'^\s*(?:ahdl_)?include\s+"([^"]+)"')
_SUBCKT = re.compile(r"^\s*(?:inline\s+)?subckt\s+(\w+)")


def _iter_lines(path, _depth=0, _seen=None):
    if _seen is None:
        _seen = set()
    if path in _seen or _depth > 3 or not os.path.exists(path):
        return
    _seen.add(path)
    base = os.path.dirname(path)
    try:
        for ln in open(path, errors="ignore"):
            yield ln
            m = _INCLUDE.match(ln)
            if m:
                inc = m.group(1)
                inc = inc if os.path.isabs(inc) else os.path.join(base, inc)
                yield from _iter_lines(inc, _depth + 1, _seen)
    except OSError:
        return


def scan_model_lib(path):
    """Return dict: corners=[...], mos=[(name, polarity)], subckts=[...]."""
    corners, mos, subs = [], {}, set()
    for ln in _iter_lines(path):
        m = _SECTION.match(ln)
        if m and m.group(1) not in corners:
            corners.append(m.group(1))
        m = _MODEL.match(ln)
        if m:
            mos.setdefault(m.group(1), m.group(2).lower())
        m = _SUBCKT.match(ln)
        if m:
            subs.add(m.group(1))
    return dict(corners=corners,
                mos=sorted(mos.items()),
                subckts=sorted(subs))


def mos_corner_sections(corners):
    """Best-guess the plain MOS corners (exclude bjt_/res_/mim_/dio_/var_)."""
    skip = ("bjt", "res", "mim", "dio", "var", "cap")
    return [c for c in corners
            if not any(c.lower().startswith(p) or ("_" + p) in c.lower()
                       for p in skip)]


def class_sections(corners, prefix):
    """{corner: section} for a device class, e.g. prefix='res' -> res_tt."""
    out = {}
    for c in corners:
        cl = c.lower()
        if cl.startswith(prefix + "_") or cl == prefix:
            # res_tt -> tt
            key = cl[len(prefix) + 1:] or "tt"
            out[key] = c
    return out
