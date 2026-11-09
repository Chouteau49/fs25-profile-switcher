"""Cartes d'objectifs de la vue Objectifs (0.15)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from fsmods_gui.career import presentation as pr
from fsmods_gui.career.objectives import (
    RW_PENDING,
    ST_COMPLETED,
    ST_IN_PROGRESS,
    ST_LOCKED,
    Objective,
    Reward,
)
from fsmods_gui.widgets.objective_cards import ObjectiveCards


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def objectives() -> list[Objective]:
    return [
        Objective(id="ha", name="Posséder 100 ha", status=ST_IN_PROGRESS, progress=0.86),
        Objective(id="million", name="Premier million", status=ST_COMPLETED,
                  reward=Reward(money=100_000), reward_state=RW_PENDING, progress=1.0),
        Objective(id="200", name="Posséder 200 ha", status=ST_LOCKED, requires=["ha"]),
    ]


def build(cards: ObjectiveCards) -> None:
    cards.set_groups(
        pr.group_objectives(objectives()),
        lambda o: pr.subtitle(o, "Terres"),
        lambda o: "Posséder 100 ha" if o.requires else "",
    )


def test_cards_grouped_and_selectable(app):
    cards = ObjectiveCards()
    build(cards)
    assert set(cards._cards) == {"ha", "million", "200"}
    got: list[str] = []
    cards.selected.connect(got.append)
    cards.card("ha").clicked.emit("ha")
    assert got == ["ha"]
    assert cards.card("ha").property("selected") == "true"
    assert cards.card("million").property("selected") == "false"


def test_paid_checkbox_only_on_completed_money_rewards(app):
    cards = ObjectiveCards()
    build(cards)
    assert cards.card("ha").paid_box is None
    box = cards.card("million").paid_box
    assert box is not None and box.isEnabled() and not box.isChecked()
    toggled: list[tuple[str, bool]] = []
    cards.paid_toggled.connect(lambda oid, paid: toggled.append((oid, paid)))
    box.setChecked(True)
    assert toggled == [("million", True)]


def test_selection_survives_refill(app):
    cards = ObjectiveCards()
    build(cards)
    cards.select("ha")
    build(cards)
    assert cards.card("ha").property("selected") == "true"


def test_empty_state(app):
    cards = ObjectiveCards()
    cards.set_groups([], lambda o: "", lambda o: "")
    assert not cards.empty_label.isHidden()
