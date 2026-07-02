from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QComboBox,
                             QLineEdit, QPushButton, QLabel, QGroupBox,
                             QFormLayout, QMessageBox)

from ..i18n import tr
from .. import passives
from .common import parse_si, fmt_si, MplCanvas, Worker


class PassivesTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._worker = None
        pdk = ctx.pdk()

        # resistor
        rbox = QGroupBox(tr("resistor"))
        rf = QFormLayout(rbox)
        self.rtype = QComboBox()
        for name, d in pdk.res_devices.items():
            self.rtype.addItem("%s — %s" % (name, d.get("desc", "")), name)
        self.rw = QLineEdit("2")
        self.rl = QLineEdit("10")
        self.rtar = QLineEdit()
        self.rtar.setPlaceholderText("100k")
        self.rout = QLabel("—")
        self.rout.setStyleSheet("font-weight:bold; color:#b35c00")
        b_rm = QPushButton(tr("measure"))
        b_rm.clicked.connect(self.meas_r)
        b_rs = QPushButton(tr("solve_l"))
        b_rs.clicked.connect(self.solve_r)
        rf.addRow(tr("rtype"), self.rtype)
        rf.addRow("W [µm]", self.rw)
        rf.addRow("L [µm]", self.rl)
        rf.addRow(tr("target_r"), self.rtar)
        hb = QHBoxLayout()
        hb.addWidget(b_rm)
        hb.addWidget(b_rs)
        rf.addRow(hb)
        rf.addRow(self.rout)

        # mim
        mbox = QGroupBox(tr("mimcap"))
        mf = QFormLayout(mbox)
        self.mtype = QComboBox()
        for name, d in pdk.cap_devices.items():
            self.mtype.addItem("%s — %s" % (name, d.get("desc", "")), name)
        self.mw = QLineEdit("25")
        self.ml = QLineEdit("25")
        self.ctar = QLineEdit()
        self.ctar.setPlaceholderText("1p")
        self.mout = QLabel("—")
        self.mout.setStyleSheet("font-weight:bold; color:#b35c00")
        b_mm = QPushButton(tr("measure"))
        b_mm.clicked.connect(self.meas_c)
        b_ms = QPushButton(tr("solve_size"))
        b_ms.clicked.connect(self.solve_c)
        mf.addRow(tr("rtype"), self.mtype)
        mf.addRow("W [µm]", self.mw)
        mf.addRow("L [µm]", self.ml)
        mf.addRow(tr("target_c"), self.ctar)
        hb2 = QHBoxLayout()
        hb2.addWidget(b_mm)
        hb2.addWidget(b_ms)
        mf.addRow(hb2)
        mf.addRow(self.mout)

        # bjt
        bbox = QGroupBox(tr("bjt"))
        bf = QFormLayout(bbox)
        self.bmodel = QComboBox()
        for fam in pdk.bjt_models.values():
            self.bmodel.addItems(fam)
        self.bvce = QLineEdit("0.9")
        b_b = QPushButton(tr("sweep_vbe"))
        b_b.clicked.connect(self.sweep_bjt)
        bf.addRow(tr("model"), self.bmodel)
        bf.addRow("|VCE| [V]", self.bvce)
        bf.addRow(b_b)

        row = QHBoxLayout()
        row.addWidget(rbox)
        row.addWidget(mbox)
        row.addWidget(bbox)

        self.canvas = MplCanvas(width=8, height=4)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.canvas, 1)

    def _run(self, fn, *args, on_done=None):
        self._worker = Worker(fn, *args)
        self._worker.done.connect(on_done)
        self._worker.failed.connect(
            lambda m: QMessageBox.warning(self, tr("error"), m[-1200:]))
        self._worker.start()

    def meas_r(self):
        self._run(passives.measure_res, self.rtype.currentData(),
                  parse_si(self.rw.text()), parse_si(self.rl.text()),
                  self.ctx.corner_aux(),
                  on_done=lambda r: self.rout.setText("R = " + fmt_si(r, "Ω")))

    def solve_r(self):
        tgt = parse_si(self.rtar.text())
        if not tgt:
            return
        def done(res):
            l, r = res
            self.rl.setText("%.3f" % l)
            self.rout.setText("L = %.3f µm → R = %s" % (l, fmt_si(r, "Ω")))
        self._run(passives.solve_res_length, self.rtype.currentData(),
                  parse_si(self.rw.text()), tgt, self.ctx.corner_aux(),
                  on_done=done)

    def meas_c(self):
        self._run(passives.measure_mim, self.mtype.currentData(),
                  parse_si(self.mw.text()), parse_si(self.ml.text()),
                  self.ctx.corner_aux(),
                  on_done=lambda c: self.mout.setText("C = " + fmt_si(c, "F")))

    def solve_c(self):
        tgt = parse_si(self.ctar.text())
        if not tgt:
            return
        def done(res):
            s, c = res
            self.mw.setText("%.2f" % s)
            self.ml.setText("%.2f" % s)
            self.mout.setText("%.2f µm □ → C = %s" % (s, fmt_si(c, "F")))
        self._run(passives.solve_mim_size, self.mtype.currentData(), tgt,
                  self.ctx.corner_aux(), on_done=done)

    def sweep_bjt(self):
        def done(b):
            ax = self.canvas.ax
            ax.clear()
            ax2 = getattr(self, "_ax2", None)
            if ax2:
                ax2.remove()
            ax.semilogy(b["vbe"], b["ic"], label="|IC| [A]")
            self._ax2 = ax.twinx()
            self._ax2.plot(b["vbe"], b["beta"], "C1--", label="β")
            ax.set_xlabel("|VBE| [V]")
            ax.set_ylabel("|IC| [A]")
            self._ax2.set_ylabel("β")
            ax.grid(True, which="both", alpha=0.3)
            ax.set_title(self.bmodel.currentText(), fontsize=10)
            self.canvas.draw_idle()
        self._run(passives.bjt_sweep, self.bmodel.currentText(),
                  parse_si(self.bvce.text(), 0.9), self.ctx.corner_aux(),
                  on_done=done)
