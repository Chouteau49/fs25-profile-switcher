"""Thème visuel de l'application : couleurs clair / sombre et feuille de style Qt.

Pourquoi un module pur (sans import Qt) : les couleurs et la feuille de style sont
de simples chaînes. Les garder ici permet de tester les contrastes (lisibilité
WCAG) et la génération du QSS sans démarrer Qt ; ``widgets/theming.py`` se
charge ensuite de les appliquer à l'application.

Avant 0.10, chaque widget codait ses couleurs en dur (cartes sombres sur fenêtre
claire, titre blanc invisible en thème clair…). Désormais tout widget lit les
jetons du thème courant via :func:`current`.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

MODE_SYSTEM = "system"
MODE_LIGHT = "light"
MODE_DARK = "dark"
MODES = (MODE_SYSTEM, MODE_LIGHT, MODE_DARK)

# Police de Windows 11, puis replis raisonnables.
FONT_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Inter")


@dataclass(frozen=True)
class Tokens:
    """Jetons de couleur d'un thème (valeurs ``#RRGGBB``)."""

    name: str
    bg: str  # fond de la fenêtre
    side: str  # barre latérale, barres d'outils / d'état
    surface: str  # cartes, champs
    surface2: str  # surfaces secondaires (pastilles, zones creuses)
    border: str
    border_strong: str
    text: str
    muted: str  # texte secondaire (doit rester lisible : ≥ 4,5:1)
    accent: str
    accent_text: str  # texte posé sur ``accent``
    accent_soft: str
    accent_soft_text: str
    amber: str
    amber_soft: str
    amber_text: str
    red: str
    red_soft: str
    red_text: str
    blue: str
    blue_soft: str
    blue_text: str
    track: str  # fond des barres de progression, grilles de graphiques

    def as_dict(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


LIGHT = Tokens(
    name=MODE_LIGHT,
    bg="#F3F4F0",
    side="#EBEDE7",
    surface="#FFFFFF",
    surface2="#F6F7F3",
    border="#DCE0D6",
    border_strong="#C2C8BA",
    text="#1A1E19",
    muted="#535D4F",
    accent="#2E7A3A",
    accent_text="#FFFFFF",
    accent_soft="#E3EFE2",
    accent_soft_text="#1F5A29",
    amber="#9A5B00",
    amber_soft="#FBEFD9",
    amber_text="#7A4700",
    red="#B3261E",
    red_soft="#FBE6E3",
    red_text="#8C1D17",
    blue="#1D5FD1",
    blue_soft="#E4ECFB",
    blue_text="#174BA6",
    track="#E4E8DF",
)

DARK = Tokens(
    name=MODE_DARK,
    bg="#111410",
    side="#161A15",
    surface="#1B201A",
    surface2="#232922",
    border="#30382E",
    border_strong="#4A5446",
    text="#E6EBE3",
    muted="#A3AD9E",
    accent="#6CC27A",
    accent_text="#0D1A0F",
    accent_soft="#1E3321",
    accent_soft_text="#A6DDAE",
    amber="#E8B25A",
    amber_soft="#33280F",
    amber_text="#F0C77E",
    red="#F08A80",
    red_soft="#3B1C19",
    red_text="#F5A79F",
    blue="#8AB4FF",
    blue_soft="#1A2740",
    blue_text="#A9C7FF",
    track="#2C3429",
)

_current: Tokens = LIGHT


def current() -> Tokens:
    """Jetons du thème actuellement appliqué (clair tant que rien n'est appliqué)."""
    return _current


def set_current(tokens: Tokens) -> None:
    global _current
    _current = tokens


def normalize_mode(mode: object) -> str:
    """Mode lu dans les réglages : toute valeur inconnue retombe sur « système »."""
    return mode if isinstance(mode, str) and mode in MODES else MODE_SYSTEM


def resolve(mode: str, system_is_dark: bool) -> Tokens:
    """Jetons à utiliser pour un mode choisi par l'utilisateur."""
    mode = normalize_mode(mode)
    if mode == MODE_DARK or (mode == MODE_SYSTEM and system_is_dark):
        return DARK
    return LIGHT


# ------------------------------------------------------------------ contraste


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fg: str, bg: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs (1 à 21)."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# Paires texte / fond réellement utilisées par l'interface.
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("text", "bg"),
    ("text", "surface"),
    ("text", "side"),
    ("muted", "bg"),
    ("muted", "surface"),
    ("muted", "side"),
    ("accent_text", "accent"),
    ("accent_soft_text", "accent_soft"),
    ("amber_text", "amber_soft"),
    ("red_text", "red_soft"),
    ("blue_text", "blue_soft"),
)


# ------------------------------------------------------------------- cartes


@dataclass(frozen=True)
class CardStyle:
    bg: str
    border: str
    title: str
    subtitle: str


def card_style(
    t: Tokens,
    *,
    selected: bool = False,
    hovered: bool = False,
    missing: bool = False,
    inherited: bool = False,
) -> CardStyle:
    """Couleurs d'une carte de mod (galerie de la bibliothèque ou d'un profil)."""
    if selected:
        return CardStyle(t.accent_soft, t.accent, t.accent_soft_text, t.accent_soft_text)
    if missing:
        return CardStyle(t.red_soft, t.red, t.red_text, t.red_text)
    if inherited:
        border = t.blue if hovered else t.blue_soft
        return CardStyle(t.surface, border, t.text, t.muted)
    return CardStyle(
        t.surface2 if hovered else t.surface,
        t.border_strong if hovered else t.border,
        t.text,
        t.muted,
    )


LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"


def level_colors(t: Tokens, level: str) -> tuple[str, str]:
    """Fond et texte d'une ligne de tableau selon sa gravité (OK / à vérifier / erreur).

    Les deux couleurs viennent du même thème, donc restent lisibles en clair
    comme en sombre (avant 0.10 : fonds pastel fixes, texte forcé en foncé).
    """
    if level == LEVEL_OK:
        return t.accent_soft, t.accent_soft_text
    if level == LEVEL_WARN:
        return t.amber_soft, t.amber_text
    return t.red_soft, t.red_text


# ------------------------------------------------------------- feuille de style


def build_stylesheet(t: Tokens) -> str:
    """Feuille de style Qt de toute l'application pour un jeu de jetons.

    Les widgets ne posent plus de couleur eux-mêmes : ils prennent un rôle via une
    propriété dynamique (``role="muted"``, ``role="card"``, ``variant="primary"``…)
    que cette feuille habille.
    """
    return f"""
QWidget {{
    color: {t.text};
}}
QMainWindow, QDialog {{
    background: {t.bg};
}}
QToolTip {{
    background: {t.surface}; color: {t.text};
    border: 1px solid {t.border_strong}; padding: 4px 6px;
}}
QToolBar {{
    background: {t.side}; border: 0; border-bottom: 1px solid {t.border};
    spacing: 4px; padding: 4px 8px;
}}
QToolBar QToolButton {{
    padding: 5px 9px; border-radius: 7px; border: 1px solid transparent;
}}
QToolBar QToolButton:hover {{
    background: {t.surface}; border-color: {t.border};
}}
QStatusBar {{
    background: {t.side}; border-top: 1px solid {t.border}; color: {t.muted};
}}
QStatusBar QLabel {{ color: {t.muted}; }}
QSplitter::handle {{ background: {t.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}

QPushButton, QToolButton {{
    background: {t.surface}; color: {t.text};
    border: 1px solid {t.border_strong}; border-radius: 8px;
    padding: 6px 12px; min-height: 20px;
}}
QPushButton:hover, QToolButton:hover {{
    background: {t.surface2}; border-color: {t.muted};
}}
QPushButton:pressed, QToolButton:pressed {{ background: {t.track}; }}
QPushButton:disabled, QToolButton:disabled {{
    color: {t.muted}; background: {t.surface2}; border-color: {t.border};
}}
QToolButton:checked {{
    background: {t.accent_soft}; color: {t.accent_soft_text}; border-color: {t.accent};
}}
QPushButton[variant="primary"] {{
    background: {t.accent}; color: {t.accent_text}; border: 0;
    font-weight: 600; padding: 8px 18px;
}}
QPushButton[variant="primary"]:hover {{ background: {t.accent_soft_text}; }}
QPushButton[variant="primary"]:disabled {{
    background: {t.track}; color: {t.muted};
}}
QPushButton[variant="ghost"] {{
    background: transparent; border: 0; color: {t.muted};
}}
QPushButton[variant="ghost"]:hover {{ background: {t.surface2}; color: {t.text}; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.surface}; color: {t.text};
    border: 1px solid {t.border_strong}; border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: {t.accent}; selection-color: {t.accent_text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {t.accent};
}}
QComboBox QAbstractItemView {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
    selection-background-color: {t.accent_soft}; selection-color: {t.accent_soft_text};
}}

QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget {{
    background: {t.surface}; alternate-background-color: {t.surface2};
    border: 1px solid {t.border}; border-radius: 10px;
    selection-background-color: {t.accent_soft}; selection-color: {t.accent_soft_text};
    gridline-color: {t.border};
}}
QListWidget::item, QListView::item {{ padding: 4px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {t.surface2}; }}
QListWidget::item:selected {{
    background: {t.accent_soft}; color: {t.accent_soft_text};
}}
QHeaderView::section {{
    background: {t.surface2}; color: {t.muted};
    border: 0; border-bottom: 1px solid {t.border}; padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {t.surface2}; border: 0; }}

QTabWidget::pane {{ border: 0; border-top: 1px solid {t.border}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {t.muted};
    padding: 8px 12px; border: 0; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {t.text}; }}
QTabBar::tab:selected {{
    color: {t.text}; border-bottom: 2px solid {t.accent}; font-weight: 600;
}}

QGroupBox {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
    margin-top: 14px; padding: 12px 10px 10px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 4px;
    color: {t.text}; font-weight: 600;
}}
QProgressBar {{
    background: {t.track}; border: 0; border-radius: 5px; height: 10px;
    text-align: center; color: {t.text};
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 5px; }}

QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: {t.border_strong}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.accent_soft_text}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}

QLabel[role="muted"] {{ color: {t.muted}; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 700; }}
QLabel[role="section"] {{
    color: {t.muted}; font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QLabel[role="success"] {{ color: {t.accent_soft_text}; }}
QLabel[role="error"] {{ color: {t.red_text}; }}
QLabel[role="card"] {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px;
    padding: 8px 10px;
}}
QLabel[role="thumb"] {{
    background: {t.surface2}; border: 1px solid {t.border}; border-radius: 8px;
}}
QLabel[role="kpi"] {{ font-size: 20px; font-weight: 700; }}
"""
