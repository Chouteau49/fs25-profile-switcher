"""Dialog to show mod details: large icon, description, and status."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import CatalogEntry

# Allow the user to select + copy the text of a label (mouse and keyboard).
_SELECTABLE = (
    Qt.TextInteractionFlag.TextSelectableByMouse
    | Qt.TextInteractionFlag.TextSelectableByKeyboard
)


def _selectable(label: QLabel) -> QLabel:
    """Make a label's text selectable/copyable; return it for chaining."""
    label.setTextInteractionFlags(_SELECTABLE)
    return label


class ModDetailDialog(QDialog):
    def __init__(self, entry: CatalogEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(f"Détails du mod : {entry.display_title}")
        self.resize(600, 450)

        layout = QVBoxLayout(self)

        # Header: Icon + Basic Info
        header = QHBoxLayout()
        
        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(128, 128)
        self.icon_label.setScaledContents(True)
        self.icon_label.setStyleSheet("border: 1px solid #555; background: #111; border-radius: 8px;")
        if entry.icon_cache_path:
            pix = QPixmap(entry.icon_cache_path)
            if not pix.isNull():
                self.icon_label.setPixmap(pix)
        header.addWidget(self.icon_label)

        info_layout = QVBoxLayout()
        title_label = QLabel(entry.display_title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")
        info_layout.addWidget(_selectable(title_label))

        cat_text = entry.category + (f" · {entry.type}" if entry.type else "")
        info_layout.addWidget(_selectable(QLabel(f"<b>Catégorie :</b> {cat_text}")))
        info_layout.addWidget(_selectable(QLabel(f"<b>Version :</b> {entry.version}")))
        info_layout.addWidget(_selectable(QLabel(f"<b>Auteur :</b> {entry.author or 'Inconnu'}")))
        info_layout.addWidget(_selectable(QLabel(f"<b>Marque :</b> {entry.brand or 'N/A'}")))
        info_layout.addWidget(_selectable(QLabel(f"<b>Fichier :</b> {entry.filename}")))
        if entry.requires:
            dep_label = QLabel(f"<b>Dépendances :</b> {', '.join(entry.requires)}")
            dep_label.setWordWrap(True)
            info_layout.addWidget(_selectable(dep_label))
        info_layout.addStretch()
        header.addLayout(info_layout, 1)

        layout.addLayout(header)

        # Description Area
        layout.addWidget(QLabel("<b>Description :</b>"))
        
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.desc_label.setContentsMargins(10, 10, 10, 10)
        # Let the user select the description text to copy it.
        self.desc_label.setTextInteractionFlags(_SELECTABLE)
        
        # Priority to French, then English, then raw
        desc_text = entry.description_fr or entry.description_en or "Aucune description disponible."
        self.desc_label.setText(desc_text)
        
        scroll.setWidget(self.desc_label)
        layout.addWidget(scroll, 1)

        # Translation Note
        if not entry.description_fr and entry.description_en:
            note_layout = QHBoxLayout()
            note = QLabel("<i>Note : Description disponible uniquement en anglais.</i>")
            note.setStyleSheet("color: #888; font-size: 11px;")
            note_layout.addWidget(note)
            
            self.gtranslate_btn = QPushButton("🌐 Google Traduction", self)
            self.gtranslate_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
            self.gtranslate_btn.setToolTip(
                "Ouvre Google Traduction (EN → FR) dans le navigateur avec le texte "
                "pré-rempli. Le texte complet est aussi copié dans le presse-papier "
                "(à coller si la description est très longue)."
            )
            self.gtranslate_btn.clicked.connect(self._open_google_translate)
            note_layout.addWidget(self.gtranslate_btn)

            note_layout.addStretch()
            layout.addLayout(note_layout)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Fermer", self)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _open_google_translate(self) -> None:
        """Open Google Translate (EN→FR) in the browser, text pre-filled + copied."""
        from urllib.parse import quote

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices, QGuiApplication

        text = (self.entry.description_en or self.desc_label.text() or "").strip()
        if not text:
            return
        # Full text to the clipboard as a fallback for very long descriptions.
        QGuiApplication.clipboard().setText(text)
        # Google Translate accepts the text in the URL; cap it so the URL stays
        # within browser limits (the clipboard still holds the complete text).
        snippet = text[:1800]
        url = (
            "https://translate.google.com/?sl=auto&tl=fr&op=translate&text="
            + quote(snippet)
        )
        QDesktopServices.openUrl(QUrl(url))
