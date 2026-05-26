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
        info_layout.addWidget(title_label)

        info_layout.addWidget(QLabel(f"<b>Version :</b> {entry.version}"))
        info_layout.addWidget(QLabel(f"<b>Auteur :</b> {entry.author or 'Inconnu'}"))
        info_layout.addWidget(QLabel(f"<b>Marque :</b> {entry.brand or 'N/A'}"))
        info_layout.addWidget(QLabel(f"<b>Fichier :</b> {entry.filename}"))
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
            
            self.translate_btn = QPushButton("Traduire (FR)", self)
            self.translate_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
            self.translate_btn.clicked.connect(self._on_translate)
            note_layout.addWidget(self.translate_btn)
            note_layout.addStretch()
            layout.addLayout(note_layout)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        close_btn = QPushButton("Fermer", self)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _on_translate(self) -> None:
        """Translate and inject the result into the ZIP file."""
        self.translate_btn.setEnabled(False)
        self.translate_btn.setText("Injection...")
        
        # Simple FS terms mapping for a 'smart' demo
        mapping = {
            "tractor": "tracteur",
            "capacity": "capacité",
            "weight": "poids",
            "brand": "marque",
            "price": "prix",
            "speed": "vitesse",
            "working width": "largeur de travail",
            "power": "puissance",
            "engine": "moteur",
            "configuration": "configuration",
            "color": "couleur",
            "tire": "pneu",
            "front loader": "chargeuse frontale",
            "attached": "attaché",
            "This mod": "Ce mod",
            "Added": "Ajouté",
            "Fixed": "Corrigé",
            "Improved": "Amélioré",
            "Updated": "Mis à jour",
        }
        
        current_text = self.desc_label.text()
        translated = current_text
        for en, fr in mapping.items():
            import re
            translated = re.sub(rf"\b{en}\b", fr, translated, flags=re.IGNORECASE)
        
        # Now try to inject into the ZIP
        from ..profiles.translator import inject_translation_to_zip
        from pathlib import Path
        
        zip_path = Path(self.entry.filename)
        # We need the full path. The CatalogEntry doesn't store the full dir, 
        # but the parent widget usually has access to the library path.
        # For now, let's assume we can resolve it via the Catalog if available.
        # But a safer way is to use the full path from the start.
        
        # Resolve full path from library
        library_dir = Path(self.entry.filename) # Fallback
        if hasattr(self.parent(), "model") and hasattr(self.parent().model, "catalog"):
            library_dir = self.parent().model.catalog.mods_dir / self.entry.filename

        try:
            success = inject_translation_to_zip(library_dir, translated)
            if success:
                self.desc_label.setText(translated + "\n\n(Traduction injectée dans le ZIP !)")
                self.translate_btn.setText("Injecté ✓")
                # Note: The UI won't show the <fr> tag until the next scan, 
                # but the ZIP is now modified!
            else:
                self.translate_btn.setText("Erreur injection")
                self.translate_btn.setEnabled(True)
        except Exception as e:
            self.translate_btn.setText("Erreur")
            print(f"Injection error: {e}")
