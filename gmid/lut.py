"""LUT loading, interpolation, derived quantities and inverse lookups."""
import os
import glob
import math

import numpy as np

from . import config

# derived expressions available to plots/queries.  Each maps to a function
# of the raw parameter dict (per-width quantities use W of the LUT).
DERIVED = {
    "gmid":  ("gm/ID [1/V]",        lambda p: p["gm"] / _c(p["ids"])),
    "idw":   ("ID/W [A/m]",         lambda p: p["ids"] / p["W"]),
    "gm":    ("gm [S]",             lambda p: p["gm"]),
    "gmw":   ("gm/W [S/m]",         lambda p: p["gm"] / p["W"]),
    "ids":   ("ID [A]",             lambda p: p["ids"]),
    "gds":   ("gds [S]",            lambda p: p["gds"]),
    "gain":  ("gm/gds (本征增益)",   lambda p: p["gm"] / _c(p["gds"])),
    "ft":    ("fT [Hz]",            lambda p: p["gm"] / (2 * math.pi * _c(p["cgg"]))),
    "vth":   ("Vth [V]",            lambda p: p["vth"]),
    "vdsat": ("Vdsat [V]",          lambda p: p["vdsat"]),
    "vov":   ("Vov=Vgs-Vth [V]",    lambda p: p["vgs"] - p["vth"]),
    "vgs":   ("Vgs [V]",            lambda p: p["vgs"]),
    "cgg":   ("Cgg [F]",            lambda p: p["cgg"]),
    "cggw":  ("Cgg/W [F/m]",        lambda p: p["cgg"] / p["W"]),
    "cgsw":  ("Cgs/W [F/m]",        lambda p: p["cgs"] / p["W"]),
    "cgdw":  ("Cgd/W [F/m]",        lambda p: p["cgd"] / p["W"]),
    "cddw":  ("Cdd/W [F/m]",        lambda p: p["cdd"] / p["W"]),
    "gmbs":  ("gmb [S]",            lambda p: p["gmbs"]),
    "ftgmid": ("fT*gm/ID [Hz/V]",   lambda p: p["gm"] / (2 * math.pi * _c(p["cgg"])) * p["gm"] / _c(p["ids"])),
}


def _c(a, floor=1e-30):
    """Clamp away from zero to avoid division blowups."""
    return np.maximum(a, floor)


def available_luts(pdk):
    """dev -> [corners] for one PDK."""
    out = {}
    pre = pdk.name + "_"
    for fn in glob.glob(os.path.join(config.LUT_DIR, pre + "*.npz")):
        base = os.path.basename(fn)[:-4][len(pre):]
        dev, corner = base.rsplit("_", 1)
        out.setdefault(dev, []).append(corner)
    return out


class MosLUT:
    _cache = {}

    @classmethod
    def get(cls, dev, corner, pdk=None):
        from . import pdk as pdkmod
        pdk = pdk or pdkmod.get()
        key = (pdk.name, dev, corner)
        if key not in cls._cache:
            path = pdk.lut_path(dev, corner)
            if not os.path.exists(path):
                raise FileNotFoundError(
                    "LUT not found: %s (run characterization first)" % path)
            cls._cache[key] = cls(path, dev, corner)
        return cls._cache[key]

    def __init__(self, path, dev, corner):
        z = np.load(path, allow_pickle=False)
        self.dev, self.corner = dev, corner
        self.L = z["L"]          # meters
        self.VSB = z["VSB"]
        self.VDS = z["VDS"]
        self.VGS = z["VGS"]
        self.W = float(z["W"])
        self.vmax = float(z["vmax"])
        self.polarity = str(z["polarity"])
        self.raw = {p: z[p].astype(np.float64) for p in config.MOS_PARAMS}

    # ---- low level: slice at (L, VSB, VDS) with linear interp, keep VGS axis
    def _slice(self, L, vsb, vds):
        out = {}
        for p, cube in self.raw.items():
            a = _interp_axis(cube, self.L, L, axis=0)
            a = _interp_axis(a, self.VSB, vsb, axis=0)
            a = _interp_axis(a, self.VDS, vds, axis=0)
            out[p] = a  # 1-D over VGS
        out["vgs"] = self.VGS.copy()
        out["W"] = self.W
        return out

    def curve(self, xexpr, yexpr, L, vsb, vds):
        s = self._slice(L, vsb, vds)
        x = DERIVED[xexpr][1](s)
        y = DERIVED[yexpr][1](s)
        # drop off-state points (gm/id meaningless below ~10fA/um)
        ok = s["ids"] / self.W > 1e-9
        return x[ok], y[ok]

    # ---- point query at given gm/id (or vgs / vov)
    def query(self, L, vsb, vds, gmid=None, vgs=None, vov=None):
        s = self._slice(L, vsb, vds)
        grid_vgs = s["vgs"]
        if vgs is None:
            if gmid is not None:
                g = s["gm"] / _c(s["ids"])
                ok = s["ids"] / self.W > 1e-9
                g, gv = g[ok], grid_vgs[ok]
                # gm/id decreases monotonically with vgs -> invert
                idx = np.argsort(g)
                vgs = float(np.interp(gmid, g[idx], gv[idx]))
                if gmid > g.max() or gmid < g.min():
                    raise ValueError("gm/id=%.3g 超出范围 [%.3g, %.3g]"
                                     % (gmid, g.min(), g.max()))
            elif vov is not None:
                vthv = s["vth"]
                f = grid_vgs - vthv - vov
                # find zero crossing of f (monotonic increasing)
                vgs = float(np.interp(0.0, f, grid_vgs))
            else:
                raise ValueError("需要 gmid / vgs / vov 之一")
        res = {}
        for p in config.MOS_PARAMS:
            res[p] = float(np.interp(vgs, grid_vgs, s[p]))
        res["vgs"] = float(vgs)
        d = dict(res)
        d["W"] = self.W
        for name, (_, fn) in DERIVED.items():
            arr = {k: np.asarray(v) for k, v in d.items()}
            try:
                res[name] = float(fn(arr))
            except Exception:
                res[name] = float("nan")
        res["W_char"] = self.W
        return res

    def size_for(self, L, vsb, vds, gmid, gm=None, ids=None):
        """Given target gm (or ID) at a gm/id point, return W and scaled params."""
        q = self.query(L, vsb, vds, gmid=gmid)
        if gm is not None:
            ids = gm / gmid
        if ids is None:
            raise ValueError("需要 gm 或 ids")
        scale = ids / q["ids"]          # width scale vs characterized W
        W = self.W * scale
        out = dict(q)
        for p in ["ids", "gm", "gds", "gmbs", "cgg", "cgs", "cgd", "cgb",
                  "cdd", "css"]:
            out[p] = q[p] * scale
        out["W"] = W
        out["L"] = L
        return out


def _interp_axis(arr, grid, val, axis):
    """Linear interpolation of ndarray along one axis at scalar val."""
    val = float(val)
    if val <= grid[0]:
        return np.take(arr, 0, axis=axis)
    if val >= grid[-1]:
        return np.take(arr, len(grid) - 1, axis=axis)
    i = int(np.searchsorted(grid, val) - 1)
    t = (val - grid[i]) / (grid[i + 1] - grid[i])
    a = np.take(arr, i, axis=axis)
    b = np.take(arr, i + 1, axis=axis)
    return a * (1 - t) + b * t
