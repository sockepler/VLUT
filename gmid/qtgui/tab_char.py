from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QCheckBox,
                             QLineEdit, QPushButton, QLabel, QProgressBar,
                             QTableWidget, QTableWidgetItem, QSpinBox,
                             QGroupBox, QGridLayout, QMessageBox)

from ..i18n import tr
from ..char_mos import CharJob
from ..lut import available_luts, MosLUT
from .common import parse_si


class CharTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.job = None

        box = QGroupBox(tr("char_title"))
        grid = QGridLayout(box)
        self.checks = {}
        for i, (name, d) in enumerate(ctx.pdk().mos.items()):
            c = QCheckBox("%s (%s)" % (name, d.get("desc", "")))
            c.setChecked(i < 2)
            self.checks[name] = c
            grid.addWidget(c, i // 3, i % 3)

        opts = QHBoxLayout()
        self.temp = QLineEdit(str(ctx.pdk().default_temp))
        self.temp.setMaximumWidth(70)
        self.nproc = QSpinBox()
        self.nproc.setRange(1, 16)
        self.nproc.setValue(4)
        self.b_start = QPushButton(tr("start_char"))
        self.b_start.clicked.connect(self.start)
        opts.addWidget(QLabel(tr("temp")))
        opts.addWidget(self.temp)
        opts.addWidget(QLabel(tr("parallel")))
        opts.addWidget(self.nproc)
        opts.addWidget(self.b_start)
        opts.addStretch(1)

        self.bar = QProgressBar()
        self.status = QLabel("")
        self.luts = QTableWidget()
        self.luts.setColumnCount(2)
        self.luts.setHorizontalHeaderLabels([tr("device"), tr("existing_luts")])
        self.luts.horizontalHeader().setStretchLastSection(True)
        self.luts.verticalHeader().setVisible(False)

        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addLayout(opts)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addWidget(QLabel(tr("existing_luts")))
        lay.addWidget(self.luts, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.refresh_luts()

    def refresh_luts(self):
        avail = available_luts(self.ctx.pdk())
        devs = list(self.ctx.pdk().mos)
        self.luts.setRowCount(len(devs))
        for i, d in enumerate(devs):
            self.luts.setItem(i, 0, QTableWidgetItem(d))
            corners = ", ".join(sorted(avail.get(d, []))) or tr("no_lut")
            self.luts.setItem(i, 1, QTableWidgetItem(corners))

    def start(self):
        devs = [n for n, c in self.checks.items() if c.isChecked()]
        if not devs:
            return
        if self.job and self.job.progress()["state"] == "running":
            QMessageBox.information(self, tr("tab_char"), "already running")
            return
        self.job = CharJob(devs, corner=self.ctx.corner(),
                           temp=parse_si(self.temp.text(), 27.0),
                           nproc=self.nproc.value(), pdk=self.ctx.pdk())
        self.job.start()
        self.b_start.setEnabled(False)
        self.timer.start(1000)

    def poll(self):
        if not self.job:
            self.timer.stop()
            return
        p = self.job.progress()
        self.bar.setMaximum(p["total"])
        self.bar.setValue(p["done"])
        if p["state"] == "running":
            self.status.setText(tr("char_running") % (p["done"], p["total"]))
        else:
            self.timer.stop()
            self.b_start.setEnabled(True)
            if p["state"] == "finished":
                self.status.setText(tr("char_done"))
                MosLUT._cache.clear()
                self.refresh_luts()
            else:
                self.status.setText(p["state"] + ": " + p.get("message", ""))
