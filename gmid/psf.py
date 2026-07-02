"""Minimal psfascii parser for Spectre DC/AC results.

Only handles what the tool generates: scalar FLOAT DOUBLE traces (dc)
and COMPLEX DOUBLE traces (ac).
"""
import re
import numpy as np

_num = re.compile(r'^"([^"]+)"\s+(.*)$')


def read_psfascii(path):
    """Return dict name -> np.ndarray (float or complex) from a psfascii file."""
    data = {}
    in_value = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not in_value:
                if line == "VALUE":
                    in_value = True
                continue
            if line in ("END", ""):
                continue
            m = _num.match(line)
            if not m:
                continue
            name, rest = m.group(1), m.group(2).strip()
            if rest.startswith('"'):
                # dc-op format: "name" "unit" value PROP( ... )
                end = rest.find('"', 1)
                rest = rest[end + 1:].strip()
            if rest.startswith("("):  # complex "(re im)"
                re_im = rest.strip("()").split()
                val = complex(float(re_im[0]), float(re_im[1]))
            else:
                tok = rest.split()[0] if rest else ""
                try:
                    val = float(tok)
                except ValueError:
                    continue
            data.setdefault(name, []).append(val)
    return {k: np.asarray(v) for k, v in data.items()}
