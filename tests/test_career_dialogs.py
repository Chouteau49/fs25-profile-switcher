from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QLocale, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from fsmods_gui.widgets.career_dialogs import DecimalSpinBox, ParcelAreasDialog

ROWS = [("Ma ferme", pid, None) for pid in ("20", "22", "49")]


@pytest.fixture(scope="module", autouse=True)
def french_app():
    previous = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    app = QApplication.instance() or QApplication([])
    yield app
    QLocale.setDefault(previous)


def dialog(rows=ROWS, typed=None) -> ParcelAreasDialog:
    dlg = ParcelAreasDialog(rows, typed or {}, "Carte DLC.")
    dlg.show()
    QApplication.processEvents()
    return dlg


def type_in(dlg: ParcelAreasDialog, pid: str, text: str) -> None:
    edit = dlg._edits[pid]
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit, text)


def test_enter_moves_to_next_parcel_and_never_closes() -> None:
    dlg = dialog()
    type_in(dlg, "20", "2,05")
    QTest.keyClick(dlg._edits["20"], Qt.Key.Key_Return)
    QApplication.processEvents()
    assert dlg.isVisible()  # used to close and silently drop the other parcels
    assert dlg.focusWidget() is dlg._edits["22"]


def test_comma_dot_and_unit_are_all_read() -> None:
    dlg = dialog()
    type_in(dlg, "20", "2,05")
    type_in(dlg, "22", "1.95")  # used to become 195 ha with a French locale
    type_in(dlg, "49", "3,5 ha")
    assert dlg.typed_areas() == {"20": 2.05, "22": 1.95, "49": 3.5}


def test_blank_is_unknown_and_zero_is_a_real_value() -> None:
    dlg = dialog()
    type_in(dlg, "20", "2")
    type_in(dlg, "22", "0")
    assert dlg.typed_areas() == {"20": 2.0, "22": 0.0}
    assert "n° 49" in dlg.total_label.text()


def test_total_is_live_and_lists_what_is_missing() -> None:
    dlg = dialog(ROWS + [("Ma ferme", "7", 1.5)], {"20": 2.0})
    assert dlg._edits["20"].text() == "2"
    assert "3,5 ha" in dlg.total_label.text()  # 2 typed + 1.5 read on the map
    assert "n° 22, n° 49" in dlg.total_label.text()
    type_in(dlg, "22", "1")
    type_in(dlg, "49", "1")
    assert "5,5 ha" in dlg.total_label.text()
    assert "n° " not in dlg.total_label.text()


def test_unreadable_value_blocks_ok_instead_of_being_dropped() -> None:
    dlg = dialog()
    type_in(dlg, "20", "abc")
    assert not dlg.ok_button.isEnabled()
    assert "n° 20" in dlg.total_label.text()
    type_in(dlg, "20", "2")
    assert dlg.ok_button.isEnabled()


@pytest.mark.parametrize("text", ["1.95", "1,95"])
def test_decimal_spinbox_accepts_both_separators(text: str) -> None:
    spin = DecimalSpinBox()
    spin.setRange(0, 1000)
    spin.setDecimals(2)
    spin.show()
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, text)
    assert spin.value() == pytest.approx(1.95)
