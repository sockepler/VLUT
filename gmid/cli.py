"""vlut-cli: headless engine for the ADE plugin (and scripting).

Subcommands:
  scan <netlist_dir>            list PDK devices found (JSON + SKILL list)
  run  <job.json>               gm/ID sweep: size -> full sim -> psf per point
  apply <results.json> <index>  emit SKILL that pushes that point's sizes
  pdks                          SKILL-readable PDK/device/LUT inventory
  char <pdk> <corner> <temp> <nproc> <dev...>   characterize LUTs

job.json:
{
  "netlist_dir": "/path/to/ade/netlist",
  "pdk": "smic18_mim10",            // optional, default: first
  "corner": "tt",
  "w_max": 10e-6,
  "max_iter": 8,
  "outdir": "/path/for/results",
  "parameters": {"CL": "2p"},       // ADE design-variable overrides
  "fixed":  [{"devices": ["M5"], "gmid": 10, "l": 0.7e-6}],
  "sweep":  {"devices": ["M1","M2"], "gmid": [8,12,16,20], "l": 0.5e-6}
}
"""
import json
import os
import sys
import traceback

from . import pdk as pdkmod
from .designer import NetlistDesign


def _skill_str(s):
    return '"%s"' % str(s).replace("\\", "/").replace('"', "'")


def scan(netlist_dir, pdk_name=None):
    pdk = pdkmod.get(pdk_name)
    nd = NetlistDesign(netlist_dir, pdk=pdk)
    devs = [dict(subckt=it.subckt or "", name=it.name, model=it.master,
                 w=it.w, l=it.l, m=it.m, count=len(it.paths))
            for it in nd.mos_items]
    print(json.dumps(dict(devices=devs), indent=1))
    return 0


def _match_items(nd, names):
    names = set(names)
    return [it for it in nd.mos_items if it.name in names]


def run(jobfile):
    job = json.load(open(jobfile))
    outdir = job["outdir"]
    os.makedirs(outdir, exist_ok=True)
    pdk = pdkmod.get(job.get("pdk"))
    corner = job.get("corner", pdk.default_corner)
    sweep = job.get("sweep") or {}
    values = sweep.get("gmid") or [None]
    points = []
    status_path = os.path.join(outdir, "status.txt")

    def status(msg):
        with open(status_path, "a") as f:
            f.write(msg + "\n")
        print(msg, flush=True)

    for i, gv in enumerate(values):
        tag = "pt%02d" % i
        status("[%d/%d] gm/ID=%s sizing..." % (i + 1, len(values), gv))
        nd = NetlistDesign(job["netlist_dir"], pdk=pdk, corner=corner,
                           w_max=float(job.get("w_max", 10e-6)))
        nd.dd.dir = _repoint(nd, job, tag)
        nd.dd.param_overrides = dict(job.get("parameters") or {})
        for f in job.get("fixed") or []:
            for it in _match_items(nd, f["devices"]):
                it.target_gmid = float(f["gmid"])
                it.target_l = float(f["l"]) if f.get("l") else None
        if gv is not None:
            for it in _match_items(nd, sweep["devices"]):
                it.target_gmid = float(gv)
                it.target_l = (float(sweep["l"])
                               if sweep.get("l") else None)
        ok, niter = nd.iterate(max_iter=int(job.get("max_iter", 8)),
                               tol=0.02)
        status("[%d/%d] sized (converged=%s, %d iters), running analyses..."
               % (i + 1, len(values), ok, niter))
        psf = nd.dd.run_full(tag)
        sizes = [dict(subckt=it.subckt or "", name=it.name, model=it.master,
                      w=it.w, l=it.l, m=it.m,
                      ids=it.op.get("ids"), gmid=it.op.get("gmid"))
                 for it in nd.mos_items]
        points.append(dict(index=i, gmid=gv, converged=ok, iters=niter,
                           psf=psf, sizes=sizes,
                           cellinfo={k or "": list(v) for k, v in
                                     nd.cellinfo.items()}))
        status("[%d/%d] done -> %s" % (i + 1, len(values), psf))

    res = dict(job=job, points=points)
    with open(os.path.join(outdir, "results.json"), "w") as f:
        json.dump(res, f, indent=1)
    # SKILL-readable summary (single line for lineread):
    # ((index gmid converged psfdir) ...)
    with open(os.path.join(outdir, "results.il"), "w") as f:
        f.write("(" + " ".join(
            "(%d %s %s %s)"
            % (p["index"], p["gmid"] if p["gmid"] is not None else 0,
               "t" if p["converged"] else "nil", _skill_str(p["psf"]))
            for p in points) + ")\n")
    status("ALL DONE")
    return 0


def apply_point(resultsfile, index, outfile=None):
    res = json.load(open(resultsfile))
    pt = res["points"][int(index)]
    by_cell = {}
    for s in pt["sizes"]:
        info = pt["cellinfo"].get(s["subckt"] or "")
        if not info or not info[0]:
            continue
        by_cell.setdefault(tuple(info), []).append(s)
    lines = ["let((cv inst)"]
    for (lib, cell), items in by_cell.items():
        lines.append('cv = dbOpenCellViewByType("%s" "%s" "schematic" nil "a")'
                     % (lib, cell))
        for s in items:
            mpar = "mr" if s["model"].endswith("_ckt") else "m"
            lines.append('inst = dbFindAnyInstByName(cv "%s")' % s["name"])
            lines.append('when(inst '
                         'dbReplaceProp(inst "w" "string" "%.4gu") '
                         'dbReplaceProp(inst "l" "string" "%.4gu") '
                         'dbReplaceProp(inst "%s" "string" "%d"))'
                         % (s["w"] * 1e6, s["l"] * 1e6, mpar, s["m"]))
        lines.append("dbSave(cv)")
        lines.append("dbClose(cv)")
    lines.append("t)")
    skill = "\n".join(lines)
    if outfile:
        open(outfile, "w").write(skill)
    else:
        print(skill)
    return 0


def _repoint(nd, job, tag):
    """Give each sweep point its own work dir (redo the copy)."""
    import shutil
    from . import config
    src = nd.dd.dir
    dst = os.path.join(job["outdir"], "work_" + tag)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    nd.dd.netlist.path = os.path.join(
        dst, os.path.basename(nd.dd.netlist.path))
    nd.dd.input_scs = os.path.join(dst, "input.scs")
    return dst


def pdks():
    """One-line SKILL inventory:
    ((name title (corners...) ((dev polarity (lut-corners...)) ...)) ...)"""
    from .lut import available_luts
    out = []
    for name, p in pdkmod.registry().items():
        luts = available_luts(p)
        devs = " ".join(
            '("%s" "%s" (%s))' % (d, p.mos[d]["polarity"],
                                  " ".join('"%s"' % c for c in
                                           sorted(luts.get(d, []))))
            for d in p.mos)
        out.append('("%s" "%s" (%s) (%s))'
                   % (name, p.title,
                      " ".join('"%s"' % c for c in p.mos_corners), devs))
    print("(" + " ".join(out) + ")")
    return 0


def char(pdk_name, corner, temp, nproc, devices):
    from .char_mos import CharJob
    import time
    pdk = pdkmod.get(pdk_name)
    bad = [d for d in devices if d not in pdk.mos]
    if bad:
        print("unknown devices: %s" % " ".join(bad))
        return 1
    job = CharJob(devices, corner=corner, temp=float(temp),
                  nproc=int(nproc), pdk=pdk)
    job.start()
    last = -1
    while True:
        p = job.progress()
        if p["done"] != last:
            last = p["done"]
            print("progress %d/%d %s" % (p["done"], p["total"],
                                         p["message"]), flush=True)
        if p["state"] in ("finished", "error", "stopped"):
            print("charend %s %s" % (p["state"], p["message"]), flush=True)
            return 0 if p["state"] == "finished" else 1
        time.sleep(1)


def main():
    try:
        cmd = sys.argv[1]
        if cmd == "scan":
            sys.exit(scan(sys.argv[2],
                          sys.argv[3] if len(sys.argv) > 3 else None))
        if cmd == "run":
            sys.exit(run(sys.argv[2]))
        if cmd == "apply":
            sys.exit(apply_point(sys.argv[2], sys.argv[3],
                                 sys.argv[4] if len(sys.argv) > 4 else None))
        if cmd == "pdks":
            sys.exit(pdks())
        if cmd == "char":
            sys.exit(char(sys.argv[2], sys.argv[3], sys.argv[4],
                          sys.argv[5], sys.argv[6:]))
        print(__doc__)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
