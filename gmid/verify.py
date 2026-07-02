"""Generate Spectre verification testbenches for designed topologies,
run AC + OP, and extract A0 / GBW / PM plus per-device operating points.

DC biasing of high-impedance outputs uses the classic L/C trick:
a huge inductor closes the loop at DC and opens it for AC, so the
AC response V(out)/V(in+) is the open-loop transfer function.
"""
import os
import glob
import subprocess

import numpy as np

from . import config
from . import pdk as pdkmod
from .psf import read_psfascii

HDR = """// gm/id tool verification - {title}
simulator lang=spectre
global 0
include "{lib}" section={corner}
opts options temp={temp} tnom=25
"""

AC_AN = """
ac1 ac start=1 stop=100G dec=20
op1 dc
"""


def _fmt(v):
    return "%.6g" % v


def _mos(name, d, g, s, b, model, w, l):
    return "%s (%s %s %s %s) %s w=%s l=%s\n" % (
        name, d, g, s, b, model, _fmt(w), _fmt(l))


def netlist_cs(design, spec, corner, temp):
    vdd, bias = spec["vdd"], design["bias"]
    m1, m2 = design["devices"][0], design["devices"][1]
    n = HDR.format(title="CS stage", lib=pdkmod.get().model_lib,
                   corner=corner, temp=temp)
    n += "vdd (vdd 0) vsource dc=%s\n" % _fmt(vdd)
    n += "vin (g1 0) vsource dc=%s mag=1\n" % _fmt(bias["vg1"])
    n += "vb2 (g2 0) vsource dc=%s\n" % _fmt(bias["vg2"])
    n += _mos("M1", "out", "g1", "0", "0", m1["model"], m1["w"], m1["l"])
    n += _mos("M2", "out", "g2", "vdd", "vdd", m2["model"], m2["w"], m2["l"])
    n += "cl (out 0) capacitor c=%s\n" % _fmt(spec["cl"])
    # DC choke pins output to designed level, open at AC frequencies
    n += "lch (out vfix) inductor l=1e15\n"
    n += "vfix (vfix 0) vsource dc=%s\n" % _fmt(bias["vout"])
    n += "save out g1\nsave M1:ids M1:gm M1:gds M1:vgs M1:vds M1:vdsat M1:vth\n"
    n += "save M2:ids M2:gm M2:gds M2:vgs M2:vds M2:vdsat M2:vth\n"
    n += AC_AN
    return n, ["M1", "M2"]


def _ota5t_core(design, spec):
    """Shared first-stage instancing for ota5t / miller (nodes fixed)."""
    m1, m2, m3, m4, m5 = design["devices"][:5]
    s = ""
    s += _mos("M1", "n1", "inp", "tail", "0", m1["model"], m1["w"], m1["l"])
    s += _mos("M2", "out1", "inm", "tail", "0", m2["model"], m2["w"], m2["l"])
    s += _mos("M3", "n1", "n1", "vdd", "vdd", m3["model"], m3["w"], m3["l"])
    s += _mos("M4", "out1", "n1", "vdd", "vdd", m4["model"], m4["w"], m4["l"])
    s += _mos("M5", "tail", "gtail", "0", "0", m5["model"], m5["w"], m5["l"])
    return s


def netlist_ota5t(design, spec, corner, temp):
    vdd, bias = spec["vdd"], design["bias"]
    n = HDR.format(title="5T OTA", lib=pdkmod.get().model_lib,
                   corner=corner, temp=temp)
    n += "vdd (vdd 0) vsource dc=%s\n" % _fmt(vdd)
    n += "vip (inp 0) vsource dc=%s mag=1\n" % _fmt(bias["vcm"])
    n += "vgt (gtail 0) vsource dc=%s\n" % _fmt(bias["vg5"])
    n += _ota5t_core(design, spec).replace("out1", "out")
    n += "cl (out 0) capacitor c=%s\n" % _fmt(spec["cl"])
    # unity feedback at DC only: L closes loop, C grounds inm for AC
    n += "lfb (out inm) inductor l=1e15\n"
    n += "cfb (inm 0) capacitor c=1e6\n"
    n += "save out inp inm tail\n"
    names = ["M1", "M2", "M3", "M4", "M5"]
    for m in names:
        n += "save %s:ids %s:gm %s:gds %s:vgs %s:vds %s:vdsat %s:vth\n" % ((m,) * 7)
    n += AC_AN
    return n, names


def netlist_miller(design, spec, corner, temp):
    vdd, bias = spec["vdd"], design["bias"]
    mets = design["metrics"]
    m6, m7 = design["devices"][5], design["devices"][6]
    n = HDR.format(title="Miller OTA", lib=pdkmod.get().model_lib,
                   corner=corner, temp=temp)
    # two inverting stages -> overall non-inverting from inm (M2 gate);
    # drive inm, close the DC loop back into inp (M1 gate) instead
    n += "vdd (vdd 0) vsource dc=%s\n" % _fmt(vdd)
    n += "vim (inm 0) vsource dc=%s mag=1\n" % _fmt(bias["vcm"])
    n += "vgt (gtail 0) vsource dc=%s\n" % _fmt(bias["vg5"])
    n += "vg7 (g7 0) vsource dc=%s\n" % _fmt(bias["vg7"])
    n += _ota5t_core(design, spec)
    n += _mos("M6", "out", "out1", "vdd", "vdd", m6["model"], m6["w"], m6["l"])
    n += _mos("M7", "out", "g7", "0", "0", m7["model"], m7["w"], m7["l"])
    n += "cc (out1 nz) capacitor c=%s\n" % _fmt(mets["cc"])
    n += "rz (nz out) resistor r=%s\n" % _fmt(mets["rz"])
    n += "cl (out 0) capacitor c=%s\n" % _fmt(spec["cl"])
    n += "lfb (out inp) inductor l=1e15\n"
    n += "cfb (inp 0) capacitor c=1e6\n"
    n += "save out out1 inp inm tail\n"
    names = ["M1", "M2", "M3", "M4", "M5", "M6", "M7"]
    for m in names:
        n += "save %s:ids %s:gm %s:gds %s:vgs %s:vds %s:vdsat %s:vth\n" % ((m,) * 7)
    n += AC_AN
    return n, names


NETLISTERS = {"cs": netlist_cs, "ota5t": netlist_ota5t, "miller": netlist_miller}


def run_verification(topo, design, spec, corner="tt", temp=config.DEFAULT_TEMP):
    netlist, mos_names = NETLISTERS[topo](design, spec, corner, temp)
    rundir = os.path.join(config.WORK_DIR, "verify_%s" % topo)
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
        tail = open(log).read()[-2000:]
        raise RuntimeError("Spectre 验证失败:\n" + tail)

    ac = read_psfascii(os.path.join(rundir, "raw", "ac1.ac"))
    freq = np.real(ac["freq"])
    h = ac["out"]
    mag = np.abs(h)
    ph = np.unwrap(np.angle(h))
    a0 = mag[0]
    a0_db = 20 * np.log10(max(a0, 1e-12))
    # unity-gain crossing
    gbw = pm = None
    idx = np.where(mag < 1.0)[0]
    if len(idx) and idx[0] > 0:
        i = idx[0]
        lm0, lm1 = np.log10(mag[i - 1]), np.log10(mag[i])
        lf0, lf1 = np.log10(freq[i - 1]), np.log10(freq[i])
        t = (0 - lm0) / (lm1 - lm0)
        gbw = 10 ** (lf0 + t * (lf1 - lf0))
        ph_u = np.degrees(ph[i - 1] + t * (ph[i] - ph[i - 1]))
        pm = 180 + ph_u - np.degrees(ph[0])

    op = read_psfascii(os.path.join(rundir, "raw", "op1.dc"))
    devops = []
    for m in mos_names:
        e = dict(name=m)
        for p in ["ids", "gm", "gds", "vgs", "vds", "vdsat", "vth"]:
            key = "%s:%s" % (m, p)
            e[p] = float(abs(op[key][0])) if key in op else None
        e["gmid"] = e["gm"] / e["ids"] if e.get("ids") else None
        devops.append(e)

    curve_mask = freq <= (gbw * 100 if gbw else freq[-1])
    return dict(
        a0_db=float(a0_db),
        gbw_hz=float(gbw) if gbw else None,
        pm_deg=float(pm) if pm else None,
        devops=devops,
        netlist=netlist,
        bode=dict(freq=freq[curve_mask].tolist(),
                  mag_db=(20 * np.log10(np.maximum(mag[curve_mask], 1e-15))).tolist(),
                  phase_deg=np.degrees(ph[curve_mask]).tolist()),
    )
