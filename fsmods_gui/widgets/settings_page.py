"""Paramètres et assistant de premier lancement : régler l'appli sans éditer de fichier.

Pourquoi : avant 0.16, ``config.yaml`` devait être créé et édité à la main, et
l'appli s'arrêtait au démarrage s'il manquait. La page **Paramètres** modifie les
dossiers, l'identifiant Steam et les cibles de sauvegarde ; l'**assistant**
s'ouvre au premier lancement (ou à la demande) et écrit la config.

La détection et la vérification « même disque » viennent de
:mod:`fsmods_gui.config_setup` ; ces widgets ne font que présenter et collecter.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config_setup as cs
from .. import theme
from . import icons


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class PathField(QWidget):
    """Champ de chemin avec bouton « Parcourir… »."""

    changed = Signal()

    def __init__(self, placeholder: str, dialog_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = dialog_title
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(lambda _text: self.changed.emit())
        browse = QPushButton("Parcourir…", self)
        icons.bind(browse, "folder")
        browse.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(browse)

    def _browse(self) -> None:
        start = self.edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, self._title, start)
        if chosen:
            self.edit.setText(str(Path(chosen)))

    def path(self) -> Path | None:
        text = self.edit.text().strip()
        return Path(text) if text else None

    def set_path(self, path: Path | None) -> None:
        self.edit.setText(str(path) if path else "")


class CheckLine(QWidget):
    """Pastille + texte : résultat d'une vérification (vert / orange)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.dot = QLabel(self)
        self.dot.setProperty("role", "dot")
        self.dot.setFixedSize(9, 9)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        lay.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.text, 1)

    def set_check(self, check: cs.Check) -> None:
        self.text.setText(check.text)
        self.dot.setProperty("level", "ok" if check.ok else "warn")
        _repolish(self.dot)


def _section(title: str, parent: QWidget) -> tuple[QWidget, QVBoxLayout]:
    box = QWidget(parent)
    box.setProperty("role", "card")
    box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    label = QLabel(title, box)
    label.setProperty("role", "card-title")
    lay.addWidget(label)
    return box, lay


def _row(caption: str, widget: QWidget, parent: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    label = QLabel(caption, parent)
    label.setProperty("role", "muted")
    label.setFixedWidth(190)
    row.addWidget(label)
    row.addWidget(widget, 1)
    return row


class SettingsPage(QWidget):
    save_requested = Signal(object)  # config_setup.GameSettings
    wizard_requested = Signal()
    theme_requested = Signal(str)
    open_config_dir_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game = "fs25"
        self._loaded: cs.GameSettings | None = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        title = QLabel("Paramètres", content)
        title.setProperty("role", "page-title")
        subtitle = QLabel("Fini le config.yaml à éditer à la main : tout se règle ici.", content)
        subtitle.setProperty("role", "muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        # ---- jeu et dossiers
        box, lay = _section("Jeu et dossiers", content)
        self.game_label = QLabel(content)
        lay.addLayout(_row("Jeu", self.game_label, box))
        self.mods_field = PathField("Dossier mods du jeu", "Dossier mods du jeu", box)
        self.mods_field.changed.connect(self._on_changed)
        lay.addLayout(_row("Dossier mods du jeu", self.mods_field, box))
        self.library_field = PathField("Ex. D:/FS25-Library", "Dossier de la bibliothèque", box)
        self.library_field.changed.connect(self._on_changed)
        lay.addLayout(_row("Bibliothèque", self.library_field, box))
        self.library_check = CheckLine(box)
        lay.addLayout(_row("", self.library_check, box))
        self.steam_edit = QLineEdit(box)
        self.steam_edit.setPlaceholderText("2300320 pour FS25")
        self.steam_edit.textChanged.connect(self._on_changed)
        lay.addLayout(_row("Application Steam", self.steam_edit, box))
        root.addWidget(box)

        # ---- sauvegarde de la config
        box, lay = _section("Sauvegarde de la configuration", content)
        note = QLabel(
            "Profils, collections et carrières uniquement, jamais les mods. Un miroir et "
            "10 instantanés ZIP par cible (Google Drive, NAS…).",
            box,
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.backup_list = QListWidget(box)
        self.backup_list.setMaximumHeight(110)
        lay.addWidget(self.backup_list)
        brow = QHBoxLayout()
        add_btn = QPushButton("Ajouter une cible…", box)
        icons.bind(add_btn, "plus")
        add_btn.clicked.connect(self._add_backup)
        self.remove_backup_btn = QPushButton("Retirer", box)
        icons.bind(self.remove_backup_btn, "trash")
        self.remove_backup_btn.clicked.connect(self._remove_backup)
        brow.addWidget(add_btn)
        brow.addWidget(self.remove_backup_btn)
        brow.addStretch(1)
        lay.addLayout(brow)
        root.addWidget(box)

        # ---- apparence
        box, lay = _section("Apparence", content)
        seg = QWidget(box)
        seg.setProperty("role", "segmented")
        seg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(3)
        self.theme_group = QButtonGroup(self)
        self._theme_modes = [theme.MODE_SYSTEM, theme.MODE_LIGHT, theme.MODE_DARK]
        for i, label in enumerate(("Comme Windows", "Clair", "Sombre")):
            btn = QPushButton(label, seg)
            btn.setCheckable(True)
            btn.setProperty("role", "segment")
            bold = btn.font()
            bold.setBold(True)
            btn.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(label) + 40)
            self.theme_group.addButton(btn, i)
            sl.addWidget(btn)
        self.theme_group.idClicked.connect(
            lambda i: self.theme_requested.emit(self._theme_modes[i])
        )
        trow = QHBoxLayout()
        trow.addWidget(seg)
        trow.addStretch(1)
        lay.addLayout(trow)
        root.addWidget(box)

        # ---- fichier de config + assistant
        box, lay = _section("Fichier de configuration", content)
        self.config_path_label = QLabel(box)
        self.config_path_label.setWordWrap(True)
        self.config_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.config_path_label)
        crow = QHBoxLayout()
        open_btn = QPushButton("Ouvrir le dossier", box)
        icons.bind(open_btn, "folder")
        open_btn.clicked.connect(self.open_config_dir_requested.emit)
        wizard_btn = QPushButton("Relancer l'assistant de démarrage", box)
        icons.bind(wizard_btn, "refresh")
        wizard_btn.clicked.connect(self.wizard_requested.emit)
        crow.addWidget(open_btn)
        crow.addWidget(wizard_btn)
        crow.addStretch(1)
        lay.addLayout(crow)
        root.addWidget(box)

        # ---- enregistrer
        actions = QHBoxLayout()
        self.status = QLabel(content)
        self.status.setProperty("role", "muted")
        self.revert_btn = QPushButton("Annuler les modifications", content)
        self.revert_btn.clicked.connect(self._revert)
        self.save_btn = QPushButton("Enregistrer", content)
        self.save_btn.setProperty("variant", "primary")
        icons.bind(self.save_btn, "check", icons.ROLE_ON_ACCENT)
        self.save_btn.clicked.connect(self._save)
        actions.addWidget(self.status, 1)
        actions.addWidget(self.revert_btn)
        actions.addWidget(self.save_btn)
        root.addLayout(actions)
        root.addStretch(1)

    # ------------------------------------------------------------------ data

    def set_settings(
        self, settings: cs.GameSettings, config_path: Path | None, theme_mode: str
    ) -> None:
        self._game = settings.game
        self._loaded = settings
        self.game_label.setText(f"{cs.GAME_TITLES.get(settings.game, settings.game)}")
        self.mods_field.set_path(settings.mods_dir)
        self.library_field.set_path(settings.library_dir)
        self.steam_edit.setText(str(settings.steam_app_id or ""))
        self.backup_list.clear()
        for path in settings.backup_dirs:
            self.backup_list.addItem(str(path))
        self.config_path_label.setText(str(config_path) if config_path else "(pas encore créé)")
        mode = theme.normalize_mode(theme_mode)
        self.theme_group.button(self._theme_modes.index(mode)).setChecked(True)
        self._on_changed()

    def current_settings(self) -> cs.GameSettings | None:
        mods, lib = self.mods_field.path(), self.library_field.path()
        if mods is None or lib is None:
            return None
        steam_text = self.steam_edit.text().strip()
        steam = int(steam_text) if steam_text.isdigit() else None
        backups = tuple(
            Path(self.backup_list.item(i).text()) for i in range(self.backup_list.count())
        )
        install = self._loaded.install_dir if self._loaded else None
        return cs.GameSettings(self._game, mods, lib, steam, backups, install)

    def is_dirty(self) -> bool:
        return self.current_settings() != self._loaded

    # ------------------------------------------------------------- internals

    def _on_changed(self) -> None:
        self.library_check.set_check(
            cs.library_check(self.mods_field.path(), self.library_field.path())
        )
        steam_text = self.steam_edit.text().strip()
        valid = self.current_settings() is not None and (not steam_text or steam_text.isdigit())
        dirty = self.is_dirty()
        self.save_btn.setEnabled(valid and dirty)
        self.revert_btn.setEnabled(dirty)
        if not valid:
            self.status.setText("Renseigne le dossier mods du jeu et la bibliothèque.")
        elif dirty:
            self.status.setText("Modifications non enregistrées.")
        else:
            self.status.setText("")

    def _add_backup(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Cible de sauvegarde", str(Path.home()))
        if chosen:
            self.backup_list.addItem(str(Path(chosen)))
            self._on_changed()

    def _remove_backup(self) -> None:
        row = self.backup_list.currentRow()
        if row >= 0:
            self.backup_list.takeItem(row)
            self._on_changed()

    def _revert(self) -> None:
        if self._loaded is not None:
            self.set_settings(
                self._loaded,
                Path(self.config_path_label.text()) if self.config_path_label.text() else None,
                theme.MODE_SYSTEM
                if self.theme_group.checkedId() < 0
                else self._theme_modes[self.theme_group.checkedId()],
            )

    def _save(self) -> None:
        settings = self.current_settings()
        if settings is not None:
            self.save_requested.emit(settings)


class FirstRunWizard(QDialog):
    """Trois étapes : jeu, dossiers, mods existants. Écrit la config à la fin."""

    def __init__(
        self,
        home: Path,
        program_files: list[Path],
        initial: cs.GameSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bienvenue dans FS25 Profile Switcher")
        self.setMinimumWidth(640)
        self._home = home
        self._program_files = program_files
        self._step = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        self.kicker = QLabel(self)
        self.kicker.setProperty("role", "section")
        self.title = QLabel(self)
        self.title.setProperty("role", "page-title")
        lay.addWidget(self.kicker)
        lay.addWidget(self.title)
        self.steps_bar = QHBoxLayout()
        self._step_labels: list[QLabel] = []
        for i, name in enumerate(("Jeu", "Dossiers", "Mods existants")):
            label = QLabel(f"{i + 1}. {name}", self)
            label.setProperty("role", "muted")
            self._step_labels.append(label)
            self.steps_bar.addWidget(label)
        self.steps_bar.addStretch(1)
        lay.addLayout(self.steps_bar)

        self.pages = QStackedWidget(self)
        # Les pages empilées sous-estiment la hauteur des textes sur plusieurs
        # lignes (le message « même disque » était coupé) : on réserve la place.
        self.pages.setMinimumHeight(280)
        lay.addWidget(self.pages, 1)

        # ---- étape 1 : jeu
        p1 = QWidget(self)
        l1 = QVBoxLayout(p1)
        intro = QLabel(
            "On règle l'appli en trois étapes, sans éditer de fichier. Tout reste "
            "modifiable ensuite dans Paramètres.",
            p1,
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        l1.addWidget(intro)
        self.game_group = QButtonGroup(self)
        self.game_buttons: dict[str, QRadioButton] = {}
        for i, game in enumerate(("fs25", "fs22")):
            found = cs.detect_install_dir(game, program_files) or cs.detect_mods_dir(game, home)
            radio = QRadioButton(
                f"{cs.GAME_TITLES[game]}  —  {'détecté' if found else 'non trouvé sur ce PC'}",
                p1,
            )
            self.game_group.addButton(radio, i)
            self.game_buttons[game] = radio
            l1.addWidget(radio)
        l1.addStretch(1)
        self.pages.addWidget(p1)

        # ---- étape 2 : dossiers
        p2 = QWidget(self)
        l2 = QVBoxLayout(p2)
        l2.addWidget(QLabel("Dossier mods du jeu", p2))
        self.mods_field = PathField("Dossier mods du jeu", "Dossier mods du jeu", p2)
        self.mods_field.changed.connect(self._update_checks)
        l2.addWidget(self.mods_field)
        self.mods_hint = QLabel(p2)
        self.mods_hint.setProperty("role", "muted")
        l2.addWidget(self.mods_hint)
        l2.addSpacing(6)
        l2.addWidget(QLabel("Dossier de la bibliothèque (tous tes mods, rangés une fois)", p2))
        self.library_field = PathField("Ex. D:/FS25-Library", "Dossier de la bibliothèque", p2)
        self.library_field.changed.connect(self._update_checks)
        l2.addWidget(self.library_field)
        self.library_check = CheckLine(p2)
        l2.addWidget(self.library_check)
        self.use_suggested_btn = QPushButton(p2)
        self.use_suggested_btn.clicked.connect(self._use_suggested)
        srow = QHBoxLayout()
        srow.addWidget(self.use_suggested_btn)
        srow.addStretch(1)
        l2.addLayout(srow)
        l2.addStretch(1)
        self.pages.addWidget(p2)

        # ---- étape 3 : mods existants
        p3 = QWidget(self)
        l3 = QVBoxLayout(p3)
        self.import_summary = QLabel(p3)
        self.import_summary.setWordWrap(True)
        l3.addWidget(self.import_summary)
        self.import_box = QCheckBox(
            "Les ajouter à la bibliothèque (rien n'est déplacé ni supprimé dans le jeu)", p3
        )
        self.profile_box = QCheckBox("Créer un premier profil « Partie actuelle » avec ces mods", p3)
        self.import_box.setChecked(True)
        self.profile_box.setChecked(True)
        self.import_box.toggled.connect(self.profile_box.setEnabled)
        l3.addWidget(self.import_box)
        l3.addWidget(self.profile_box)
        l3.addStretch(1)
        self.pages.addWidget(p3)

        # ---- boutons
        nav = QHBoxLayout()
        self.back_btn = QPushButton("Retour", self)
        self.back_btn.clicked.connect(lambda: self._go(self._step - 1))
        self.cancel_btn = QPushButton("Annuler", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.next_btn = QPushButton(self)
        self.next_btn.setProperty("variant", "primary")
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.cancel_btn)
        nav.addStretch(1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)

        game = initial.game if initial else ("fs25" if self._detected("fs25") or not
                                             self._detected("fs22") else "fs22")
        self.game_buttons[game].setChecked(True)
        if initial is not None:
            self.mods_field.set_path(initial.mods_dir)
            self.library_field.set_path(initial.library_dir)
        self._go(0)

    # ------------------------------------------------------------- helpers

    def _detected(self, game: str) -> bool:
        return bool(
            cs.detect_install_dir(game, self._program_files) or cs.detect_mods_dir(game, self._home)
        )

    def game(self) -> str:
        return "fs22" if self.game_buttons["fs22"].isChecked() else "fs25"

    def _prefill_folders(self) -> None:
        game = self.game()
        if self.mods_field.path() is None:
            detected = cs.detect_mods_dir(game, self._home)
            self.mods_field.set_path(detected)
        mods = self.mods_field.path()
        if self.library_field.path() is None and mods is not None:
            self.library_field.set_path(cs.suggested_library_dir(game, mods))
        self._update_checks()

    def _update_checks(self) -> None:
        mods = self.mods_field.path()
        self.mods_hint.setText(
            "Détecté automatiquement." if mods is not None and mods.parent.is_dir()
            else "Introuvable : choisis le dossier mods du jeu (Documents/My Games/…)."
        )
        check = cs.library_check(mods, self.library_field.path())
        self.library_check.set_check(check)
        suggestion = cs.suggested_library_dir(self.game(), mods) if mods else None
        show = suggestion is not None and not check.ok and self.library_field.path() != suggestion
        self.use_suggested_btn.setVisible(bool(show))
        if suggestion is not None:
            self.use_suggested_btn.setText(f"Utiliser {suggestion}")
        if self._step == 1:
            self.next_btn.setEnabled(mods is not None and self.library_field.path() is not None)
        self.adjustSize()  # le message peut passer sur deux lignes

    def _use_suggested(self) -> None:
        mods = self.mods_field.path()
        if mods is not None:
            self.library_field.set_path(cs.suggested_library_dir(self.game(), mods))

    def _prepare_import_step(self) -> None:
        mods, lib = self.mods_field.path(), self.library_field.path()
        plan = cs.initial_import_plan(mods, lib / "mods") if mods and lib else []
        self._plan_count = len(plan)
        if plan:
            self.import_summary.setText(
                f"<b>{len(plan)} mods</b> trouvés dans le dossier du jeu et absents de la "
                "bibliothèque."
            )
        else:
            self.import_summary.setText("Aucun mod à ajouter : la bibliothèque est prête.")
        self.import_box.setVisible(bool(plan))
        self.profile_box.setVisible(bool(plan))

    def _go(self, step: int) -> None:
        step = max(0, min(2, step))
        if step == 1:
            self._prefill_folders()
        if step == 2:
            self._prepare_import_step()
        self._step = step
        self.pages.setCurrentIndex(step)
        titles = ("Quel jeu veux-tu gérer ?", "Où ranger ta bibliothèque ?", "Tes mods actuels")
        self.kicker.setText(f"BIENVENUE · ÉTAPE {step + 1} SUR 3")
        self.title.setText(titles[step])
        for i, label in enumerate(self._step_labels):
            label.setProperty("role", "strong" if i == step else "muted")
            _repolish(label)
        self.back_btn.setEnabled(step > 0)
        self.next_btn.setText("Terminer" if step == 2 else "Continuer")
        self.next_btn.setEnabled(True)
        self._update_checks()

    def _next(self) -> None:
        if self._step < 2:
            self._go(self._step + 1)
        else:
            self.accept()

    # ------------------------------------------------------------------ result

    def settings(self) -> cs.GameSettings | None:
        mods, lib = self.mods_field.path(), self.library_field.path()
        if mods is None or lib is None:
            return None
        game = self.game()
        return cs.GameSettings(
            game, mods, lib, cs.STEAM_APP_IDS[game],
            install_dir=cs.detect_install_dir(game, self._program_files),
        )

    def import_requested(self) -> bool:
        return not self.import_box.isHidden() and self.import_box.isChecked()

    def profile_requested(self) -> bool:
        return self.import_requested() and self.profile_box.isChecked()
