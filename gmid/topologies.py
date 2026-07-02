"""gm/id-based iterative design procedures for the built-in topologies.

Each design function takes a spec dict and returns:
  devices: [{name, model, w, l, id, gm, gmid, vgs, vdsat, vds, vsb, ...}]
  metrics: {a0_db, gbw_hz, pm_deg, itotal, power, ...}
  bias:    node voltages needed by the verification netlist
"""
import math

from .lut import MosLUT

TWO_PI = 2 * math.pi


def _dev_entry(name, model, lut_res, vds, vsb, role):
    return dict(
        name=name, model=model, role=role,
        w=lut_res["W"], l=lut_res["L"],
        id=lut_res["ids"], gm=lut_res["gm"], gds=lut_res["gds"],
        gmid=lut_res["gm"] / max(lut_res["ids"], 1e-30),
        vgs=lut_res["vgs"], vth=lut_res["vth"], vdsat=lut_res["vdsat"],
        vds=vds, vsb=vsb,
        cgg=lut_res["cgg"], cgd=lut_res["cgd"], cdd=lut_res["cdd"],
    )


def design_cs(spec, corner="tt"):
    """共源级: NMOS input M1, PMOS current-source load M2, output at VDD/2."""
    vdd = spec["vdd"]
    gbw = spec["gbw"]
    cl = spec["cl"]
    nmos = MosLUT.get(spec["dev_n"], corner)
    pmos = MosLUT.get(spec["dev_p"], corner)
    gmid1, L1 = spec["gmid1"], spec["l1"]
    gmid2, L2 = spec["gmid2"], spec["l2"]
    vout = vdd / 2

    cl_eff = cl
    for _ in range(6):
        gm1 = TWO_PI * gbw * cl_eff
        m1 = nmos.size_for(L1, 0.0, vout, gmid1, gm=gm1)
        m2 = pmos.size_for(L2, 0.0, vdd - vout, gmid2, ids=m1["ids"])
        cl_eff = cl + m1["cdd"] + m2["cdd"]

    a0 = gm1 / (m1["gds"] + m2["gds"])
    devices = [
        _dev_entry("M1", spec["dev_n"], m1, vout, 0.0, "输入管"),
        _dev_entry("M2", spec["dev_p"], m2, vdd - vout, 0.0, "电流源负载"),
    ]
    metrics = dict(
        a0_db=20 * math.log10(a0),
        gbw_hz=gm1 / (TWO_PI * cl_eff),
        itotal=m1["ids"], power=m1["ids"] * vdd,
        vout_min=m1["vdsat"], vout_max=vdd - m2["vdsat"],
    )
    bias = dict(vg1=m1["vgs"], vg2=vdd - m2["vgs"], vout=vout)
    return dict(devices=devices, metrics=metrics, bias=bias)


def design_ota5t(spec, corner="tt"):
    """五管OTA: NMOS差分对M1/M2, PMOS镜像负载M3/M4, NMOS尾电流M5."""
    vdd = spec["vdd"]
    gbw = spec["gbw"]
    cl = spec["cl"]
    vcm = spec.get("vcm", vdd / 2)
    nmos = MosLUT.get(spec["dev_n"], corner)
    pmos = MosLUT.get(spec["dev_p"], corner)
    gmid_in, L_in = spec["gmid_in"], spec["l_in"]
    gmid_ld, L_ld = spec["gmid_ld"], spec["l_ld"]
    gmid_tl, L_tl = spec["gmid_tail"], spec["l_tail"]

    vs = 0.4  # tail node initial guess
    cl_eff = cl
    for _ in range(8):
        gm1 = TWO_PI * gbw * cl_eff
        # input pair: bulk at 0, source at vs -> vsb=vs
        m34_probe = pmos.query(L_ld, 0.0, 0.4, gmid=gmid_ld)  # just for vsg guess
        vout = vdd - m34_probe["vgs"]
        m1 = nmos.size_for(L_in, vs, vout - vs, gmid_in, gm=gm1)
        vs = max(vcm - m1["vgs"], 0.05)
        idb = m1["ids"]
        m34 = pmos.size_for(L_ld, 0.0, m34_probe["vgs"], gmid_ld, ids=idb)
        m5 = nmos.size_for(L_tl, 0.0, vs, gmid_tl, ids=2 * idb)
        cl_eff = cl + m1["cdd"] + m34["cdd"]

    a0 = gm1 / (m1["gds"] + m34["gds"])
    # mirror pole at gate of M3/M4
    fp_mirror = m34["gm"] / (TWO_PI * (2 * m34["cgg"] + m1["cdd"]))
    gbw_real = gm1 / (TWO_PI * cl_eff)
    pm = 90 - math.degrees(math.atan(gbw_real / fp_mirror)) \
            + math.degrees(math.atan(gbw_real / (2 * fp_mirror)))
    dn, dp = spec["dev_n"], spec["dev_p"]
    devices = [
        _dev_entry("M1", dn, m1, vdd - m34["vgs"] - vs, vs, "差分对"),
        _dev_entry("M2", dn, m1, vdd - m34["vgs"] - vs, vs, "差分对"),
        _dev_entry("M3", dp, m34, m34["vgs"], 0.0, "镜像负载(二极管)"),
        _dev_entry("M4", dp, m34, m34["vgs"], 0.0, "镜像负载"),
        _dev_entry("M5", dn, m5, vs, 0.0, "尾电流源"),
    ]
    metrics = dict(
        a0_db=20 * math.log10(a0),
        gbw_hz=gbw_real, pm_deg=pm,
        itotal=2 * idb, power=2 * idb * vdd,
        vout_min=vs + m1["vdsat"], vout_max=vdd - m34["vdsat"],
        vcm_min=m1["vgs"] + m5["vdsat"],
        vcm_max=vdd - m34["vgs"] + m1["vth"],
        tail_node=vs, vout_dc=vdd - m34["vgs"],
    )
    bias = dict(vg5=m5["vgs"], vcm=vcm, vout=vdd - m34["vgs"])
    return dict(devices=devices, metrics=metrics, bias=bias)


def design_miller(spec, corner="tt"):
    """两级Miller OTA (Allen-Holberg): 一级NMOS对+PMOS镜像, 二级PMOS共源M6+NMOS电流沉M7, Cc+Rz补偿."""
    vdd = spec["vdd"]
    gbw = spec["gbw"]
    cl = spec["cl"]
    pm_target = spec.get("pm", 60.0)
    vcm = spec.get("vcm", vdd / 2)
    nmos = MosLUT.get(spec["dev_n"], corner)
    pmos = MosLUT.get(spec["dev_p"], corner)
    gmid1, L1 = spec["gmid_in"], spec["l_in"]
    gmid_ld, L_ld = spec["gmid_ld"], spec["l_ld"]
    gmid_tl, L_tl = spec["gmid_tail"], spec["l_tail"]
    gmid6, L6 = spec["gmid2"], spec["l2"]
    gmid7, L7 = spec.get("gmid7", gmid_tl), spec.get("l7", L_tl)

    cc = spec.get("cc", 0.25 * cl)
    vout2 = vdd / 2
    vs = 0.4
    for _ in range(8):
        gm1 = TWO_PI * gbw * cc
        # phase margin: PM = 90 - atan(GBW/p2) - atan(GBW/z)
        # p2 = gm6/CL', z = gm6/Cc (Rz=0); solve gm6 by bisection on r=gm6/(2pi GBW)
        want = math.radians(90 - pm_target)
        lo, hi = 1e-15, 1e3
        for _ in range(80):
            r = math.sqrt(lo * hi)
            ang = math.atan(cl / r) + math.atan(cc / r)
            if ang > want:
                lo = r
            else:
                hi = r
        gm6 = TWO_PI * gbw * math.sqrt(lo * hi)

        m34p = pmos.query(L_ld, 0.0, 0.4, gmid=gmid_ld)
        vout1 = vdd - m34p["vgs"]
        m1 = nmos.size_for(L1, vs, vout1 - vs, gmid1, gm=gm1)
        vs = max(vcm - m1["vgs"], 0.05)
        idb = m1["ids"]
        m34 = pmos.size_for(L_ld, 0.0, m34p["vgs"], gmid_ld, ids=idb)
        m5 = nmos.size_for(L_tl, 0.0, vs, gmid_tl, ids=2 * idb)
        # M6: PMOS CS, VSG6 = vdd - vout1 = vsg of mirror -> consistent dc
        m6 = pmos.size_for(L6, 0.0, vdd - vout2, gmid6, gm=gm6)
        id6 = m6["ids"]
        m7 = nmos.size_for(L7, 0.0, vout2, gmid7, ids=id6)
        # bias consistency: force VSG6 == vdd-vout1 by adjusting gmid6? report gap instead

    a1 = gm1 / (m1["gds"] + m34["gds"])
    a2 = gm6 / (m6["gds"] + m7["gds"])
    gbw_real = gm1 / (TWO_PI * cc)
    p2 = gm6 / (TWO_PI * (cl + m6["cdd"] + m7["cdd"]))
    rz = 1.0 / gm6  # nulling resistor kills RHP zero
    pm = 90 - math.degrees(math.atan(gbw_real / p2))
    dn, dp = spec["dev_n"], spec["dev_p"]
    vout1 = vdd - m34["vgs"]
    devices = [
        _dev_entry("M1", dn, m1, vout1 - vs, vs, "差分对"),
        _dev_entry("M2", dn, m1, vout1 - vs, vs, "差分对"),
        _dev_entry("M3", dp, m34, m34["vgs"], 0.0, "镜像负载(二极管)"),
        _dev_entry("M4", dp, m34, m34["vgs"], 0.0, "镜像负载"),
        _dev_entry("M5", dn, m5, vs, 0.0, "尾电流源"),
        _dev_entry("M6", dp, m6, vdd - vout2, 0.0, "第二级共源"),
        _dev_entry("M7", dn, m7, vout2, 0.0, "第二级电流沉"),
    ]
    metrics = dict(
        a0_db=20 * math.log10(a1 * a2),
        a1_db=20 * math.log10(a1), a2_db=20 * math.log10(a2),
        gbw_hz=gbw_real, pm_deg=pm, p2_hz=p2,
        cc=cc, rz=rz,
        itotal=2 * idb + id6, power=(2 * idb + id6) * vdd,
        vout_min=m7["vdsat"], vout_max=vdd - m6["vdsat"],
        vsg6_design=m6["vgs"], vsg6_available=vdd - vout1,
        tail_node=vs, vout1_dc=vout1,
    )
    bias = dict(vg5=m5["vgs"], vg7=m7["vgs"], vcm=vcm,
                vout1=vout1, vout=vout2)
    return dict(devices=devices, metrics=metrics, bias=bias)


TOPOLOGIES = {
    "cs": dict(fn=design_cs, name="共源级 (电流源负载)",
               specs=["vdd", "gbw", "cl", "gmid1", "l1", "gmid2", "l2"]),
    "ota5t": dict(fn=design_ota5t, name="五管OTA",
                  specs=["vdd", "gbw", "cl", "vcm", "gmid_in", "l_in",
                         "gmid_ld", "l_ld", "gmid_tail", "l_tail"]),
    "miller": dict(fn=design_miller, name="两级Miller OTA",
                   specs=["vdd", "gbw", "cl", "pm", "vcm", "gmid_in", "l_in",
                          "gmid_ld", "l_ld", "gmid_tail", "l_tail",
                          "gmid2", "l2"]),
}
