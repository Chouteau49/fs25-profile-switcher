"""Embeddable dashboard panel: library statistics ("Carte des mods")."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog
from ..profiles.collection import Collection
from ..profiles.profile import Profile
from ..profiles.stats import LibraryStats, compute_stats, human_size


class StatsPanel(QWidget):
    def __init__(
        self,
        catalog: Catalog | None,
        profiles: list[Profile],
        collections: list[Collection],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        stats = compute_stats(catalog, profiles, collections)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._summary_box(stats))
        layout.addWidget(
            self._table_box(
                "Répartition par catégorie",
                ["Catégorie", "Nombre", "Taille"],
                [
                    (cat, str(n), human_size(stats.by_category_size.get(cat, 0)))
                    for cat, n in sorted(
                        stats.by_category.items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ],
            )
        )
        if stats.top_brands:
            layout.addWidget(
                self._table_box(
                    "Top marques",
                    ["Marque", "Nombre"],
                    [(b, str(n)) for b, n in stats.top_brands],
                )
            )
        if stats.mods_per_profile:
            layout.addWidget(
                self._table_box(
                    "Mods par profil (effectifs)",
                    ["Profil", "Mods"],
                    [(name, str(n)) for name, n in stats.mods_per_profile],
                )
            )
        if stats.mods_per_collection:
            layout.addWidget(
                self._table_box(
                    "Mods par collection",
                    ["Collection", "Mods"],
                    [(name, str(n)) for name, n in stats.mods_per_collection],
                )
            )
        if stats.orphan_files:
            layout.addWidget(
                self._table_box(
                    f"Mods orphelins — dans aucun profil ni collection ({len(stats.orphan_files)})",
                    ["Fichier"],
                    [(f,) for f in stats.orphan_files],
                )
            )
        if stats.parse_errors:
            layout.addWidget(
                self._table_box(
                    f"Erreurs de lecture ({len(stats.parse_errors)})",
                    ["Fichier"],
                    [(f,) for f in stats.parse_errors],
                )
            )
        layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll, 1)

    # ------------------------------------------------------------------ pieces

    def _summary_box(self, s: LibraryStats) -> QGroupBox:
        box = QGroupBox("Vue d'ensemble", self)
        grid = QGridLayout(box)
        cards = [
            ("Mods", str(s.total_mods)),
            ("Taille totale", human_size(s.total_size_bytes)),
            ("Cartes", str(s.maps)),
            ("Profils", str(s.profiles_count)),
            ("Collections", str(s.collections_count)),
            ("Groupes de doublons", f"{s.duplicate_groups} ({s.duplicate_files} fichiers)"),
            ("Orphelins", str(len(s.orphan_files))),
            ("Erreurs de lecture", str(len(s.parse_errors))),
        ]
        for i, (label, value) in enumerate(cards):
            cell = QVBoxLayout()
            val = QLabel(value)
            val.setStyleSheet("font-size: 18px; font-weight: 700;")
            cap = QLabel(label)
            cap.setStyleSheet("color: #888;")
            cell.addWidget(val)
            cell.addWidget(cap)
            wrap = QWidget()
            wrap.setLayout(cell)
            grid.addWidget(wrap, i // 4, i % 4)
        return box

    def _table_box(self, title: str, headers: list[str], rows: list[tuple]) -> QGroupBox:
        box = QGroupBox(title, self)
        layout = QVBoxLayout(box)
        table = QTableWidget(box)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        # Keep tables compact but scrollable inside the dialog.
        row_h = table.verticalHeader().defaultSectionSize()
        table.setMinimumHeight(min(len(rows) + 1, 8) * row_h + 30)
        layout.addWidget(table)
        return box
