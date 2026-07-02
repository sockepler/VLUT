"""Standalone desktop GUI for the gm/id design tool (EN/JA)."""
import sys

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QLabel,
                             QComboBox, QToolBar, QWidget, QSizePolicy)

from .. import pdk as pdkmod
from ..i18n import tr, set_lang, LANGS
from ..lut import MosLUT


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("gmid-tool", "gmid-tool")
        set_lang(self.settings.value("lang", "en"))
        pdkmod.get(self.settings.value("pdk", None) or None)
        self._build()

    # context accessors used by all tabs
    def pdk(self):
        return pdkmod.get()

    def corner(self):
        return self.corner_sel.currentText()

    def corner_aux(self):
        """aux device classes usually only have tt/ff/ss"""
        c = self.corner()
        return c if c in self.pdk().bjt_sections else "tt"

    def _build(self):
        self.setWindowTitle("%s — %s" % (tr("app_title"), self.pdk().title))
        if getattr(self, "_tb", None) is not None:
            self.removeToolBar(self._tb)
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        self._tb = tb

        tb.addWidget(QLabel(" %s: " % tr("pdk")))
        self.pdk_sel = QComboBox()
        for name, p in pdkmod.registry().items():
            self.pdk_sel.addItem(p.title, name)
        idx = self.pdk_sel.findData(self.pdk().name)
        if idx >= 0:
            self.pdk_sel.setCurrentIndex(idx)
        self.pdk_sel.currentIndexChanged.connect(self._pdk_changed)
        tb.addWidget(self.pdk_sel)

        tb.addWidget(QLabel("  %s: " % tr("corner")))
        self.corner_sel = QComboBox()
        self.corner_sel.addItems(self.pdk().mos_corners)
        tb.addWidget(self.corner_sel)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(QLabel("%s: " % tr("language")))
        self.lang_sel = QComboBox()
        self.lang_sel.addItem("English", "en")
        self.lang_sel.addItem("日本語", "ja")
        idx = self.lang_sel.findData(self.settings.value("lang", "en"))
        if idx >= 0:
            self.lang_sel.setCurrentIndex(idx)
        self.lang_sel.currentIndexChanged.connect(self._lang_changed)
        tb.addWidget(self.lang_sel)

        from .tab_curves import CurvesTab
        from .tab_query import QueryTab
        from .tab_netlist import NetlistTab
        from .tab_topo import TopoTab
        from .tab_passives import PassivesTab
        from .tab_char import CharTab

        self.tabs = QTabWidget()
        self.tabs.addTab(CurvesTab(self), tr("tab_curves"))
        self.tabs.addTab(QueryTab(self), tr("tab_query"))
        self.tabs.addTab(NetlistTab(self), tr("tab_netlist"))
        self.tabs.addTab(TopoTab(self), tr("tab_topo"))
        self.tabs.addTab(PassivesTab(self), tr("tab_passives"))
        self.tabs.addTab(CharTab(self), tr("tab_char"))
        self.setCentralWidget(self.tabs)
        self.resize(1280, 820)

    def _rebuild(self):
        cur = self.tabs.currentIndex()
        self._build()
        self.tabs.setCurrentIndex(cur)

    def _lang_changed(self):
        lang = self.lang_sel.currentData()
        set_lang(lang)
        self.settings.setValue("lang", lang)
        self._rebuild()

    def _pdk_changed(self):
        name = self.pdk_sel.currentData()
        pdkmod.get(name)
        MosLUT._cache.clear()
        self.settings.setValue("pdk", name)
        self._rebuild()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
