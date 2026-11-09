"""Icônes vectorielles (traits SVG) colorées selon le thème courant.

Pourquoi des SVG plutôt que des emojis : le rendu des emojis dépend de la police
du système (couleur, taille, alignement variables) et ne suit pas le thème. Ces
icônes au trait, dessinées sur une grille 24×24 dans l'esprit des jeux libres
Lucide / Fluent, prennent la couleur du texte du thème.

``bind(obj, name)`` pose l'icône sur un bouton ou une action et la mémorise :
:func:`fsmods_gui.widgets.theming.refresh_icons` la recolore au changement de thème.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QObject, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .. import theme

ICON_PROPERTY = "fsIcon"
ICON_ROLE_PROPERTY = "fsIconRole"

# Contenu SVG (dans un viewBox 0 0 24 24, trait = currentColor).
_SHAPES: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    "library": '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5"/>'
    '<path d="m3 16.5 9 4.5 9-4.5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/>'
    '<circle cx="12" cy="12" r="1"/>',
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "settings": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/>'
    '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
    'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    "download": '<path d="M12 3v11M7.5 9.5 12 14l4.5-4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14'
    'a1 1 0 0 0 1-1v-4"/>',
    "upload": '<path d="M12 14V3M7.5 7.5 12 3l4.5 4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14'
    'a1 1 0 0 0 1-1v-4"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5'
    'a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.7L20 8.5"/><path d="M20 3.5v5h-5"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "puzzle": '<path d="M5 8h3a2 2 0 1 1 4 0h3v3a2 2 0 1 1 0 4v4H5z"/>',
    "file-text": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "route": '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/>'
    '<path d="M8 19h8a3 3 0 0 0 0-6H8a3 3 0 0 1 0-6h8"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5.5 10a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3"/>'
    '<path d="M7 15h10"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M3 20h18"/>',
    "pencil": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
    "coins": '<circle cx="12" cy="12" r="9"/><path d="M15 9.5a3 3 0 0 0-3-1.5c-1.7 0-3 .9-3 2s1.3 1.8 3 2'
    ' 3 .9 3 2-1.3 2-3 2a3 3 0 0 1-3-1.5M12 6v2M12 16v2"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "map": '<path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "folder": '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "collection": '<rect x="3" y="4" width="18" height="6" rx="1.5"/><path d="M5 10v9a1 1 0 0 0 1 1h12'
    'a1 1 0 0 0 1-1v-9M10 14h4"/>',
    "link": '<path d="M9 7H6a3 3 0 0 0 0 6h3M15 7h3a3 3 0 0 1 0 6h-3M8 10h8"/>',
    "ban": '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
    '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "check-square": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "square": '<rect x="4" y="4" width="16" height="16" rx="3"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.5 0-1.2-1-1.6-1-2.5 0-.8.7-1.5 1.5-1.5H16'
    'a5 5 0 0 0 5-5c0-4.1-4-7.5-9-7.5z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/>'
    '<circle cx="15" cy="7.5" r="1"/>',
    "play": '<path d="M7 4.5v15l12.5-7.5z" fill="currentColor"/>',
    "box": '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
}

# Rôles de couleur : nom du jeton du thème utilisé pour le trait.
ROLE_TEXT = "text"
ROLE_MUTED = "muted"
ROLE_ON_ACCENT = "accent_text"
ROLE_ACCENT = "accent"


def names() -> list[str]:
    return sorted(_SHAPES)


def _svg(name: str, color: str, stroke: float) -> bytes:
    shape = _SHAPES[name].replace("currentColor", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{shape}</svg>'
    ).encode()


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, stroke: float) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, color, stroke)))
    scale = 2  # net sur les écrans à 150-200 %
    pix = QPixmap(size * scale, size * scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pix.setDevicePixelRatio(scale)
    return pix


def pixmap(name: str, color: str | None = None, size: int = 18, stroke: float = 1.9) -> QPixmap:
    if name not in _SHAPES:
        raise KeyError(name)
    return _pixmap(name, color or theme.current().text, size, stroke)


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Icône ``name`` ; couleur par défaut = texte du thème courant."""
    if name not in _SHAPES:
        raise KeyError(name)
    t = theme.current()
    result = QIcon()
    result.addPixmap(pixmap(name, color or t.text, size), QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, t.muted, size), QIcon.Mode.Disabled)
    return result


def bind(obj: QObject, name: str, role: str = ROLE_TEXT) -> None:
    """Pose l'icône sur ``obj`` (bouton, action…) et la recolore aux changements de thème."""
    obj.setProperty(ICON_PROPERTY, name)
    obj.setProperty(ICON_ROLE_PROPERTY, role)
    apply_bound(obj)


def apply_bound(obj: QObject) -> None:
    name = obj.property(ICON_PROPERTY)
    if not name:
        return
    role = obj.property(ICON_ROLE_PROPERTY) or ROLE_TEXT
    color = getattr(theme.current(), str(role), theme.current().text)
    obj.setIcon(icon(str(name), color))  # type: ignore[attr-defined]
