"""États des cartes de l'espace Diagnostic."""
from __future__ import annotations

from fsmods_gui import diagnostics as d
from fsmods_gui import navigation as nav


def test_one_card_per_diagnostic_view():
    keys = [t.key for t in d.TOOLS]
    assert keys == [f.key for f in nav.section(nav.SECTION_DIAGNOSTIC).features]


def test_log_status():
    assert d.log_status(None, None).text == "Aucun log de partie trouvé"
    assert d.log_status(0, 0) == d.Status(d.LEVEL_OK, "Dernière partie : aucun problème")
    s = d.log_status(2, 1)
    assert s.level == d.LEVEL_WARN
    assert s.text == "Dernière partie : 2 erreurs, 1 avertissement"
    assert d.log_status(0, 3).level == d.LEVEL_INFO


def test_duplicates_status():
    assert d.duplicates_status(None).text.startswith("Scan")
    assert d.duplicates_status(0).level == d.LEVEL_OK
    s = d.duplicates_status(4, 9)
    assert s.level == d.LEVEL_WARN and s.text == "4 groupes (9 fichiers)"
    assert d.duplicates_status(1, 2).text == "1 groupe (2 fichiers)"


def test_stats_status():
    assert d.stats_status(None, 0).text.startswith("Scan")
    assert d.stats_status(0, 0).text == "Bibliothèque vide"
    assert d.stats_status(10, 0).level == d.LEVEL_OK
    assert d.stats_status(812, 300).text == "300 mods sur 812 (37 %) ne servent à aucun profil"


def test_audit_status():
    assert d.audit_status(None).text.startswith("Choisis")
    assert d.audit_status("Montagne").text == "Profil : Montagne"
