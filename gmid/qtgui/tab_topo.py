"""Built-in topology design tab (CS / 5T OTA / Miller) with verify."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QComboBox,
                             QLineEdit, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem, QMessageBox, QGridLayout,
                             QGroupBox, QSplitter, QPlainTextEdit)

from ..i18n import tr
from ..topologies import TOPOLOGIES
from ..verify import run_verification
from .common import parse_si, fmt_si, MplCanvas, Worker

DEFAULTS = {
    "vdd": "1.8", "gbw": "20M", "cl": "2p", "pm": "60", "vcm": "0.9",
    "gmid1": "15", "l1": "0.5", "gmid2": "12", "l2": "0.35",
    "gmid_in": "16", "l_in": "0.5", "gmid_ld": "10", "l_ld": "0.7",
    "gmid_tail": "10", "l_tail": "0.7",
}
TOPO_TR = {"cs": "topo_cs", "ota5t": "topo_ota5t", "miller": "topo_miller"}
DEVCOLS = ["", "Model", "W", "L", "ID", "gm", "gm/ID", "VGS", "Vdsat", "VDS"]


class TopoTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.design = None
        self.spec = None
        self.topo = None
        self._worker = None

        top = QHBoxLayout()
        self.tsel = QComboBox()
        for k in TOPOLOGIES:
            self.tsel.addItem(tr(TOPO_TR[k]), k)
        self.tsel.currentIndexChanged.connect(self._build_form)
        self.devn = QComboBox()
        self.devp = QComboBox()
        for name, d in ctx.pdk().mos.items():
            (self.devn if d["polarity"] == "n" else self.devp).addItem(name)
        self.b_design = QPushButton(tr("design"))
        self.b_design.clicked.connect(self.run_design)
        self.b_verify = QPushButton(tr("verify"))
        self.b_verify.clicked.connect(self.run_verify)
        self.b_verify.setEnabled(False)
        for w in [QLabel(tr("topology")), self.tsel, QLabel("NMOS"),
                  self.devn, QLabel("PMOS"), self.devp,
                  self.b_design, self.b_verify]:
            top.addWidget(w)
        top.addStretch(1)

        self.formbox = QGroupBox(tr("spec"))
        self.form = QGridLayout(self.formbox)
        self.edits = {}

        self.devtable = QTableWidget()
        self.mettable = QTableWidget()
        self.vertable = QTableWidget()
        for t in (self.devtable, self.mettable, self.vertable):
            t.verticalHeader().setVisible(False)
        self.netview = QPlainTextEdit()
        self.netview.setReadOnly(True)
        self.canvas = MplCanvas(width=6, height=4)

        left = QVBoxLayout()
        left.addWidget(QLabel(tr("devices_table")))
        left.addWidget(self.devtable, 2)
        left.addWidget(QLabel(tr("metrics")))
        left.addWidget(self.mettable, 2)
        lw = QWidget()
        lw.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel(tr("verified")))
        right.addWidget(self.vertable, 1)
        right.addWidget(self.canvas, 3)
        rw = QWidget()
        rw.setLayout(right)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(lw)
        split.addWidget(rw)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.formbox)
        lay.addWidget(split, 1)
        self._build_form()

    def _build_form(self):
        for i in reversed(range(self.form.count())):
            w = self.form.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.edits = {}
        topo = self.tsel.currentData()
        specs = TOPOLOGIES[topo]["specs"]
        for i, s in enumerate(specs):
            lab = QLabel(tr(s))
            e = QLineEdit(DEFAULTS.get(s, ""))
            e.setMaximumWidth(90)
            self.edits[s] = e
            self.form.addWidget(lab, i // 4 * 2, i % 4)
            self.form.addWidget(e, i // 4 * 2 + 1, i % 4)
        self.b_verify.setEnabled(False)

    def run_design(self):
        topo = self.tsel.currentData()
        spec = {}
        for k, e in self.edits.items():
            v = parse_si(e.text())
            if v is None:
                continue
            if k.startswith("l"):
                v *= 1e-6
            spec[k] = v
        spec["dev_n"] = self.devn.currentText()
        spec["dev_p"] = self.devp.currentText()
        try:
            self.design = TOPOLOGIES[topo]["fn"](spec, self.ctx.corner())
        except Exception as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        self.spec, self.topo = spec, topo
        self._fill_devices(self.design["devices"])
        self._fill_kv(self.mettable, self.design["metrics"])
        self.b_verify.setEnabled(True)

    def _fill_devices(self, devs):
        t = self.devtable
        t.setColumnCount(len(DEVCOLS))
        t.setHorizontalHeaderLabels(DEVCOLS)
        t.setRowCount(len(devs))
        for i, d in enumerate(devs):
            vals = [d["name"], d["model"], fmt_si(d["w"], "m"),
                    fmt_si(d["l"], "m"), fmt_si(d["id"], "A"),
                    fmt_si(d["gm"], "S"), "%.2f" % d["gmid"],
                    "%.3f" % d["vgs"], "%.3f" % d["vdsat"],
                    "%.3f" % d["vds"]]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()

    def _fill_kv(self, table, d):
        rows = [(k, v) for k, v in d.items() if v is not None]
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([tr("parameter"), tr("value")])
        table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(tr(k)))
            if k.endswith("_db") or k.endswith("_deg") or k.startswith("v"):
                txt = "%.2f" % v
            else:
                txt = fmt_si(v)
            table.setItem(i, 1, QTableWidgetItem(txt))
        table.resizeColumnsToContents()

    def run_verify(self):
        if not self.design:
            return
        self.b_verify.setEnabled(False)
        self._worker = Worker(run_verification, self.topo, self.design,
                              self.spec, self.ctx.corner())
        self._worker.done.connect(self._verify_done)
        self._worker.failed.connect(self._verify_fail)
        self._worker.start()

    def _verify_fail(self, msg):
        self.b_verify.setEnabled(True)
        QMessageBox.warning(self, tr("error"), msg[-1500:])

    def _verify_done(self, res):
        self.b_verify.setEnabled(True)
        self._fill_kv(self.vertable,
                      dict(a0_db=res["a0_db"], gbw_hz=res["gbw_hz"],
                           pm_deg=res["pm_deg"]))
        ax = self.canvas.ax
        ax.clear()
        b = res["bode"]
        ax.semilogx(b["freq"], b["mag_db"], label="|H| [dB]")
        ax2 = getattr(self, "_ax2", None)
        if ax2:
            ax2.remove()
        self._ax2 = ax.twinx()
        self._ax2.semilogx(b["freq"], b["phase_deg"], "C1--",
                           label="phase [°]")
        ax.set_xlabel("f [Hz]")
        ax.set_ylabel("|H| [dB]")
        self._ax2.set_ylabel("phase [°]")
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title("A0=%.1fdB  GBW=%s  PM=%.1f°"
                     % (res["a0_db"], fmt_si(res["gbw_hz"], "Hz"),
                        res["pm_deg"] or 0), fontsize=10)
        self.canvas.draw_idle()
