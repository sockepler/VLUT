"""MOS characterization: run Spectre DC sweeps and build gm/id LUTs.

One spectre run per (L, VSB) point: outer parametric sweep over VDS,
inner dc sweep over VGS.  Results are assembled into a 4-D array
(L, VSB, VDS, VGS) per op parameter and saved via pdk.lut_path().
"""
import os
import glob
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import config
from . import pdk as pdkmod
from .psf import read_psfascii

NETLIST_TMPL = """// gm/id char {dev} L={lg} VSB={vsb} corner={corner}
simulator lang=spectre
global 0
include "{modellib}" section={corner}

parameters vgs=0 vds=0 lg={lg} wg={wg}

vd (d 0) vsource dc={sd}*vds
vg (g 0) vsource dc={sd}*vgs
vs (s 0) vsource dc=0
vb (b 0) vsource dc={sb}*{vsb}

M1 (d g s b) {dev} l=lg w=wg

opts options temp={temp} tnom=25

save {saves}

swpvds sweep param=vds values=[{vds_list}] {{
    dcvgs dc param=vgs values=[{vgs_list}]
}}
"""


def _netlist(pdk, dev, corner, lg, vsb, temp):
    d = pdk.mos[dev]
    pol = d["polarity"]
    sd = "-1" if pol == "p" else "1"   # drain/gate sign
    sb = "1" if pol == "p" else "-1"   # bulk: nmos b=-vsb, pmos b=+vsb (source at 0)
    saves = " ".join("M1:%s" % p for p in config.MOS_PARAMS)
    return NETLIST_TMPL.format(
        dev=dev, corner=corner, lg="%.6gu" % lg, wg="%.6g" % d["wchar"],
        modellib=pdk.model_lib, sd=sd, sb=sb, vsb="%.6g" % vsb,
        temp=temp, saves=saves,
        vds_list=" ".join("%.6g" % v for v in d["vds"]),
        vgs_list=" ".join("%.6g" % v for v in d["vgs"]),
    )


def _run_one(pdk, dev, corner, il, lg, ivsb, vsb, temp, workdir):
    """Run one (L, VSB) spectre job; return (il, ivsb, {param: 2D [vds, vgs]})."""
    d = pdk.mos[dev]
    rundir = os.path.join(workdir, "L%02d_B%02d" % (il, ivsb))
    os.makedirs(rundir, exist_ok=True)
    scs = os.path.join(rundir, "char.scs")
    with open(scs, "w") as f:
        f.write(_netlist(pdk, dev, corner, lg, vsb, temp))
    raw = os.path.join(rundir, "raw")
    log = os.path.join(rundir, "spectre.log")
    with open(log, "w") as lf:
        r = subprocess.run([config.SPECTRE, scs, "-format", "psfascii",
                            "-raw", raw],
                           stdout=lf, stderr=subprocess.STDOUT, cwd=rundir)
    if r.returncode != 0:
        raise RuntimeError("spectre failed for %s L=%g VSB=%g, see %s"
                           % (dev, lg, vsb, log))
    nvds, nvgs = len(d["vds"]), len(d["vgs"])
    out = {p: np.full((nvds, nvgs), np.nan, dtype=np.float64)
           for p in config.MOS_PARAMS}
    files = sorted(glob.glob(os.path.join(raw, "swpvds-*_dcvgs.dc")))
    if len(files) != nvds:
        raise RuntimeError("expected %d dc files, got %d in %s"
                           % (nvds, len(files), raw))
    for i, fn in enumerate(files):
        data = read_psfascii(fn)
        for p in config.MOS_PARAMS:
            arr = data.get("M1:%s" % p)
            if arr is None or len(arr) != nvgs:
                raise RuntimeError("missing/short M1:%s in %s" % (p, fn))
            out[p][i, :] = arr
    shutil.rmtree(raw, ignore_errors=True)
    return il, ivsb, out


class CharJob:
    """Background characterization job with progress reporting."""

    def __init__(self, devices, corner=None, temp=None,
                 nproc=config.MAX_PARALLEL_SPECTRE, pdk=None):
        self.pdk = pdk or pdkmod.get()
        self.devices = devices
        self.corner = corner or self.pdk.default_corner
        self.temp = self.pdk.default_temp if temp is None else temp
        self.nproc = nproc
        self.total = sum(len(self.pdk.mos[d]["Ls"]) *
                         len(self.pdk.mos[d]["vsbs"]) for d in devices)
        self.done = 0
        self.state = "pending"
        self.message = ""
        self._lock = threading.Lock()
        self._thread = None
        self._stop = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.state = "running"
        self._thread.start()

    def stop(self):
        self._stop = True

    def progress(self):
        with self._lock:
            return dict(state=self.state, done=self.done, total=self.total,
                        message=self.message)

    def _run(self):
        try:
            for dev in self.devices:
                if self._stop:
                    break
                self._char_device(dev)
            with self._lock:
                self.state = "finished" if not self._stop else "stopped"
                self.message = "done"
        except Exception as e:
            with self._lock:
                self.state = "error"
                self.message = str(e)

    def _char_device(self, dev):
        d = self.pdk.mos[dev]
        workdir = os.path.join(config.WORK_DIR,
                               "char_%s_%s" % (dev, self.corner))
        os.makedirs(workdir, exist_ok=True)
        Ls, vsbs = d["Ls"], d["vsbs"]
        nL, nB = len(Ls), len(vsbs)
        nD, nG = len(d["vds"]), len(d["vgs"])
        cube = {p: np.full((nL, nB, nD, nG), np.nan, dtype=np.float32)
                for p in config.MOS_PARAMS}
        jobs = [(il, lg, ib, vb) for il, lg in enumerate(Ls)
                for ib, vb in enumerate(vsbs)]
        with ThreadPoolExecutor(max_workers=self.nproc) as ex:
            futs = [ex.submit(_run_one, self.pdk, dev, self.corner, il, lg,
                              ib, vb, self.temp, workdir)
                    for il, lg, ib, vb in jobs]
            for fut in as_completed(futs):
                il, ib, out = fut.result()
                for p in config.MOS_PARAMS:
                    # store magnitudes: PMOS ids/vth/vdsat come out negative
                    cube[p][il, ib] = np.abs(out[p]).astype(np.float32)
                with self._lock:
                    self.done += 1
                    self.message = "%s: %d/%d" % (dev, self.done, self.total)
        np.savez_compressed(
            self.pdk.lut_path(dev, self.corner),
            L=np.asarray(Ls, dtype=np.float64) * 1e-6,
            VSB=np.asarray(vsbs, dtype=np.float64),
            VDS=np.asarray(d["vds"], dtype=np.float64),
            VGS=np.asarray(d["vgs"], dtype=np.float64),
            W=np.float64(d["wchar"]),
            polarity=d["polarity"], vmax=np.float64(d["vmax"]),
            temp=np.float64(self.temp),
            **cube)
        shutil.rmtree(workdir, ignore_errors=True)
