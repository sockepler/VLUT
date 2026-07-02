"""PDK registry: load device/grid descriptors from pdks/*.yaml."""
import os
import glob

import yaml

from . import config


def _frange(start, stop, step):
    n = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 6) for i in range(n)]


class PDK:
    def __init__(self, path):
        with open(path) as f:
            y = yaml.safe_load(f)
        self.path = path
        self.name = y["name"]
        self.title = y.get("title", self.name)
        self.model_lib = y["model_lib"]
        self.mos_corners = y["mos_corners"]
        self.default_corner = y.get("default_corner", self.mos_corners[0])
        self.default_temp = float(y.get("default_temp", 27.0))

        grids = y.get("grids", {})
        self.mos = {}
        for dev, d in (y.get("mos") or {}).items():
            g = grids[d["grid"]]
            vmax = float(g["vmax"])
            self.mos[dev] = dict(
                polarity=d["polarity"], vmax=vmax,
                wchar=float(d.get("wchar", 10e-6)),
                desc=d.get("desc", ""),
                Ls=[float(x) for x in g["Ls"]],
                vsbs=[float(x) for x in g["vsbs"]],
                vgs=_frange(0.0, vmax, float(g["vgs_step"])),
                vds=_frange(0.0, vmax, float(g["vds_step"])),
            )

        b = y.get("bjt") or {}
        self.bjt_sections = b.get("section", {})
        self.bjt_models = b.get("models", {})
        r = y.get("res") or {}
        self.res_sections = r.get("section", {})
        self.res_devices = r.get("devices", {})
        c = y.get("cap") or {}
        self.cap_sections = c.get("section", {})
        self.cap_devices = c.get("devices", {})

    def mos_models(self):
        return list(self.mos)

    def all_models(self):
        """model/subckt name -> class ('mos'/'bjt'/'res'/'cap')."""
        out = {m: "mos" for m in self.mos}
        for m in list(self.mos):
            out[m + "_ckt"] = "mos"    # inline-subckt mismatch wrappers
        for fam in self.bjt_models.values():
            for m in fam:
                out[m] = "bjt"
        for name, d in self.res_devices.items():
            out[d["subckt"]] = "res"
            out[name] = "res"
        for name, d in self.cap_devices.items():
            out[d["subckt"]] = "cap"
            out[name] = "cap"
        return out

    def lut_path(self, dev, corner):
        return os.path.join(config.LUT_DIR,
                            "%s_%s_%s.npz" % (self.name, dev, corner))


_registry = None
_active = None


def registry():
    global _registry
    if _registry is None:
        _registry = {}
        for fn in sorted(glob.glob(os.path.join(config.TOOL_ROOT,
                                                "pdks", "*.yaml"))):
            p = PDK(fn)
            _registry[p.name] = p
    return _registry


def get(name=None):
    global _active
    reg = registry()
    if name:
        _active = reg[name]
    if _active is None:
        _active = next(iter(reg.values()))
    return _active
