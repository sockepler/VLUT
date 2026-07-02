"""Quick single-shot Spectre calculators for R / MIM / BJT devices."""
import os
import subprocess

import numpy as np

from . import config
from . import pdk as pdkmod
from .psf import read_psfascii


def _run(name, netlist):
    rundir = os.path.join(config.WORK_DIR, "passive_%s" % name)
    os.makedirs(rundir, exist_ok=True)
    scs = os.path.join(rundir, "tb.scs")
    with open(scs, "w") as f:
        f.write(netlist)
    log = os.path.join(rundir, "spectre.log")
    with open(log, "w") as lf:
        r = subprocess.run([config.SPECTRE, scs, "-format", "psfascii",
                            "-raw", os.path.join(rundir, "raw")],
                           stdout=lf, stderr=subprocess.STDOUT, cwd=rundir)
    if r.returncode != 0:
        raise RuntimeError("Spectre 失败:\n" + open(log).read()[-1500:])
    return os.path.join(rundir, "raw")


HDR = """simulator lang=spectre
global 0
include "{lib}" section={sec}
opts options temp={temp} tnom=25
"""


def measure_res(rtype, w_um, l_um, corner="tt", temp=27.0, vbias=0.1):
    """Measure resistance of a PDK resistor at given W/L (um)."""
    pdk = pdkmod.get()
    info = pdk.res_devices[rtype]
    sec = pdk.res_sections[corner]
    n = HDR.format(lib=pdkmod.get().model_lib, sec=sec, temp=temp)
    ports = "(n1 0 0)" if info["terms"] == 3 else "(n1 0)"
    n += "v1 (n1 0) vsource dc=%g\n" % vbias
    n += "x1 %s %s w=%gu l=%gu\n" % (ports, info["subckt"], w_um, l_um)
    n += "save v1:p\nop1 dc\n"
    raw = _run("res", n)
    op = read_psfascii(os.path.join(raw, "op1.dc"))
    i = abs(float(op["v1:p"][0]))
    return vbias / max(i, 1e-30)


def solve_res_length(rtype, w_um, r_target, corner="tt", temp=27.0):
    """Iterate L until R matches target (R is affine in L -> secant)."""
    l = 10.0
    for _ in range(6):
        r = measure_res(rtype, w_um, l, corner, temp)
        if abs(r - r_target) / r_target < 1e-3:
            break
        l = max(0.5, l * r_target / r)
    return l, measure_res(rtype, w_um, l, corner, temp)


def measure_mim(mtype, w_um, l_um, corner="tt", temp=27.0):
    """Measure MIM capacitance via AC current at 1 MHz."""
    pdk = pdkmod.get()
    info = pdk.cap_devices[mtype]
    sec = pdk.cap_sections[corner]
    n = HDR.format(lib=pdkmod.get().model_lib, sec=sec, temp=temp)
    n += "v1 (n1 0) vsource dc=0.9 mag=1\n"
    n += "x1 (n1 0) %s wr=%gu lr=%gu\n" % (info["subckt"], w_um, l_um)
    n += "save v1:p\nac1 ac start=1M stop=2M lin=2\n"
    raw = _run("mim", n)
    ac = read_psfascii(os.path.join(raw, "ac1.ac"))
    i = abs(complex(ac["v1:p"][0]))
    return i / (2 * np.pi * 1e6)


def solve_mim_size(mtype, c_target, corner="tt", temp=27.0):
    """Square MIM: find side length for target C."""
    s = 25.0
    for _ in range(6):
        c = measure_mim(mtype, s, s, corner, temp)
        if abs(c - c_target) / c_target < 1e-3:
            break
        s = min(100.0, max(2.0, s * (c_target / c) ** 0.5))
    return s, measure_mim(mtype, s, s, corner, temp)


def bjt_sweep(model, vce=0.9, corner="tt", temp=27.0):
    """Sweep VBE, return IC / gm / beta curves (magnitudes)."""
    sec = pdkmod.get().bjt_sections[corner]
    pnp = model.startswith("pnp")
    n = HDR.format(lib=pdkmod.get().model_lib, sec=sec, temp=temp)
    sgn = "-1" if pnp else "1"
    n += "parameters vbe=0.7\n"
    n += "vb (b 0) vsource dc=%s*vbe\n" % sgn
    n += "vc (c 0) vsource dc=%s*%g\n" % (sgn, vce)
    n += "ve (e 0) vsource dc=0\n"
    n += "q1 (c b e) %s\n" % model
    n += "save q1:ic q1:ib q1:gm\n"
    n += "dc1 dc param=vbe start=0.3 stop=1.0 step=0.005\n"
    raw = _run("bjt", n)
    d = read_psfascii(os.path.join(raw, "dc1.dc"))
    vbe = np.abs(d["vbe"])
    ic = np.abs(d["q1:ic"])
    ib = np.maximum(np.abs(d["q1:ib"]), 1e-30)
    gm = np.abs(d["q1:gm"])
    ok = ic > 1e-12
    return dict(vbe=vbe[ok].tolist(), ic=ic[ok].tolist(),
                beta=(ic[ok] / ib[ok]).tolist(), gm=gm[ok].tolist())
