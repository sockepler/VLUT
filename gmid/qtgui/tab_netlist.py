"""Netlist Designer tab: load an ADE netlist, run OP, iterate gm/id sizing."""
import os
import subprocess

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLineEdit,
                             QPushButton, QLabel, QTableWidget, QSpinBox,
                             QTableWidgetItem, QMessageBox, QFileDialog,
                             QPlainTextEdit, QSplitter)

from ..i18n import tr
from ..designer import NetlistDesign
from .common import parse_si, fmt_si, Worker

COLS = ["col_device", "col_model", "col_count", "col_W", "col_m",
        "col_Wtot", "col_L", "col_id", "col_gmid", "col_vgs", "col_vds",
        "col_vdsat", "col_gain", "col_target_gmid", "col_target_L"]
EDITABLE = {13, 14}          # target gm/ID, target L


class NetlistTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.nd = None
        self._worker = None

        top = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText(tr("netlist_dir"))
        b_browse = QPushButton(tr("browse"))
        b_browse.clicked.connect(self._browse)
        self.b_load = QPushButton(tr("load"))
        self.b_load.clicked.connect(self.load)
        top.addWidget(self.path, 1)
        top.addWidget(b_browse)
        top.addWidget(self.b_load)

        actions = QHBoxLayout()
        self.b_op = QPushButton(tr("run_op"))
        self.b_op.clicked.connect(self.run_op)
        self.b_iter = QPushButton(tr("iterate"))
        self.b_iter.clicked.connect(self.iterate)
        self.maxiter = QSpinBox()
        self.maxiter.setRange(1, 30)
        self.maxiter.setValue(8)
        self.b_save = QPushButton(tr("save_as"))
        self.b_save.clicked.connect(self.save_as)
        self.b_push = QPushButton(tr("push_virtuoso"))
        self.b_push.clicked.connect(self.push)
        for b in (self.b_op, self.b_iter, self.b_save, self.b_push):
            b.setEnabled(False)
        self.wmax = QLineEdit("10")
        self.wmax.setMaximumWidth(60)
        actions.addWidget(self.b_op)
        actions.addWidget(self.b_iter)
        actions.addWidget(QLabel(tr("max_iter")))
        actions.addWidget(self.maxiter)
        actions.addWidget(QLabel(tr("wmax")))
        actions.addWidget(self.wmax)
        actions.addWidget(self.b_save)
        actions.addWidget(self.b_push)
        actions.addStretch(1)
        actions.addWidget(QLabel(tr("hint_target")))

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLS])

        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(2000)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.logbox)
        split.setSizes([500, 150])

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(actions)
        lay.addWidget(split, 1)

    # ---------- helpers ----------
    def _log(self, msg):
        self.logbox.appendPlainText(msg)

    def _busy(self, on):
        for b in (self.b_load, self.b_op, self.b_iter, self.b_save,
                  self.b_push):
            b.setEnabled(not on and self.nd is not None)
        self.b_load.setEnabled(not on)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("netlist_dir"))
        if d:
            self.path.setText(d)

    # ---------- load ----------
    def load(self):
        src = self.path.text().strip()
        if not src or not os.path.exists(src):
            QMessageBox.warning(self, tr("error"), tr("no_netlist"))
            return
        try:
            self.nd = NetlistDesign(src, pdk=self.ctx.pdk(),
                                    corner=self.ctx.corner())
        except Exception as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        self._log(tr("loaded_n") % (len(self.nd.mos_items),
                                    len(self.nd.other_items)))
        for r in self.nd.dd.remap_log:
            self._log("  [remap] " + r)
        self._fill_table()
        self._busy(False)

    def _fill_table(self):
        items = self.nd.mos_items
        t = self.table
        t.setRowCount(len(items))
        for i, it in enumerate(items):
            op = it.op or {}
            gain = (op.get("gm", 0) / op.get("gds", 1)
                    if op.get("gds") else None)
            vals = [it.label(), it.master, str(len(it.paths)),
                    "%.3f" % (it.w * 1e6) if it.w else "—",
                    "%d" % it.m,
                    "%.2f" % (it.wtotal * 1e6) if it.w else "—",
                    "%.3f" % (it.l * 1e6) if it.l else "—",
                    fmt_si(op.get("ids"), "A"),
                    "%.2f" % op["gmid"] if op.get("gmid") else "—",
                    "%.3f" % op["vgs"] if op.get("vgs") is not None else "—",
                    "%.3f" % op["vds"] if op.get("vds") is not None else "—",
                    "%.3f" % op["vdsat"] if op.get("vdsat") is not None else "—",
                    "%.1f" % gain if gain else "—",
                    "" if it.target_gmid is None else "%g" % it.target_gmid,
                    "" if it.target_l is None else "%g" % (it.target_l * 1e6)]
            for j, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if j not in EDITABLE:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                else:
                    cell.setBackground(Qt.yellow if False else cell.background())
                t.setItem(i, j, cell)
        t.resizeColumnsToContents()

    def _collect_targets(self):
        wmax = parse_si(self.wmax.text())
        if wmax:
            self.nd.w_max = wmax * 1e-6
        for i, it in enumerate(self.nd.mos_items):
            g = self.table.item(i, 13)
            l = self.table.item(i, 14)
            it.target_gmid = parse_si(g.text()) if g and g.text().strip() else None
            lv = parse_si(l.text()) if l and l.text().strip() else None
            it.target_l = lv * 1e-6 if lv else None

    # ---------- actions ----------
    def run_op(self):
        if not self.nd:
            return
        self._busy(True)
        self._worker = Worker(self.nd.run_op)
        self._worker.done.connect(self._op_done)
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _op_done(self, _):
        self._collect_targets_safe()
        self._fill_table()
        self._busy(False)
        self._log("OP done")

    def _collect_targets_safe(self):
        try:
            self._collect_targets()
        except Exception:
            pass

    def iterate(self):
        if not self.nd:
            return
        self._collect_targets()
        n_t = sum(1 for it in self.nd.mos_items if it.target_gmid)
        if not n_t:
            QMessageBox.information(self, tr("iterate"), tr("hint_target"))
            return
        self._busy(True)
        maxi = self.maxiter.value()

        def job():
            return self.nd.iterate(max_iter=maxi, tol=0.02)

        self._worker = Worker(job)
        self._worker.done.connect(self._iter_done)
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _iter_done(self, res):
        ok, n = res
        for line in self.nd.log:
            self._log("  " + line)
        self.nd.log.clear()
        self._log(tr("converged") % n if ok else tr("not_converged") % 0.0)
        self._fill_table()
        self._busy(False)

    def _fail(self, msg):
        self._busy(False)
        self._log("ERROR: " + msg)
        QMessageBox.warning(self, tr("error"), msg[-1500:])

    def save_as(self):
        if not self.nd:
            return
        fn, _ = QFileDialog.getSaveFileName(self, tr("save_as"),
                                            "netlist_sized.scs")
        if fn:
            self.nd.save_netlist(fn)
            self._log("saved: " + fn)

    def push(self):
        if not self.nd:
            return
        skill = self.nd.skill_for_push()
        self._log(skill)
        cli = os.path.expanduser(
            "~/virtuoso-bridge-lite/.venv/bin/virtuoso-bridge")
        if not os.path.exists(cli):
            cli = "virtuoso-bridge"
        try:
            r = subprocess.run([cli, "eval", "--stdin"], input=skill,
                               capture_output=True, text=True, timeout=90)
            self._log(r.stdout[-1500:])
            if r.returncode == 0:
                self._log(tr("pushed"))
            else:
                self._log("ERROR: " + r.stderr[-800:])
        except Exception as e:
            self._log("ERROR: %s" % e)
