"""Défi sur une fenêtre de temps de jeu : « gagner X en 24 h de jeu ».

La fenêtre s'ouvre à un point de contrôle (activation du défi) et se mesure en heures de
jeu (``playTime``), pas en temps réel. Le gain se mesure sur une statistique cumulée.

Limite assumée : l'appli ne lit la sauvegarde qu'à la synchronisation. Si le joueur a
joué plus longtemps que la fenêtre entre deux lectures, le moment exact où la cible a
été atteinte est inconnu. On ne le devine pas : le résultat est alors « imprécis » (si la
cible est atteinte) ou « échoué » (si elle ne l'est pas, car le cumul ne baisse jamais).

Pur, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass

from .periods import Checkpoint, period_gain
from .regression import is_cumulative

ST_OPEN = "en_cours"
ST_WON = "reussi"
ST_LOST = "echoue"
ST_IMPRECISE = "imprecis"
ST_UNAVAILABLE = "indisponible"

PLAY_TIME = "playTime"


@dataclass(frozen=True)
class WindowChallenge:
    name: str
    stat: str  # statistique cumulée à gagner, ex. finance.missionIncome
    target: float
    hours: float = 24.0  # durée de la fenêtre, en heures de jeu
    # Au-delà de la fenêtre + cette marge, la sauvegarde a été lue trop tard pour dater.
    tolerance_hours: float = 1.0


@dataclass(frozen=True)
class WindowResult:
    state: str
    gain: float | None
    elapsed_hours: float | None
    progress: float
    message: str


def evaluate_window(challenge: WindowChallenge, start: Checkpoint, now: Checkpoint) -> WindowResult:
    if not is_cumulative(challenge.stat):
        return WindowResult(ST_UNAVAILABLE, None, None, 0.0,
                            "Statistique non cumulée : un gain sur une fenêtre n'a pas de sens.")
    elapsed = period_gain(start, now, PLAY_TIME)
    gain = period_gain(start, now, challenge.stat)
    if elapsed is None or gain is None:
        return WindowResult(ST_UNAVAILABLE, None, elapsed, 0.0,
                            "Statistique illisible ou baisse détectée : défi suspendu.")

    progress = max(0.0, min(gain / challenge.target, 1.0)) if challenge.target > 0 else 0.0
    reached = gain >= challenge.target
    closed_at = challenge.hours + challenge.tolerance_hours
    if elapsed > closed_at:
        if reached:
            return WindowResult(ST_IMPRECISE, gain, elapsed, 1.0,
                                "Fenêtre dépassée avant la lecture : la cible est atteinte, "
                                "mais le moment exact est inconnu.")
        # Le cumul ne baisse jamais : si la cible n'est pas atteinte à la fin, elle ne
        # l'a pas été pendant la fenêtre non plus.
        return WindowResult(ST_LOST, gain, elapsed, progress,
                            "Fenêtre de temps de jeu écoulée sans atteindre la cible.")
    if reached:
        return WindowResult(ST_WON, gain, elapsed, 1.0, "Cible atteinte dans la fenêtre.")
    return WindowResult(ST_OPEN, gain, elapsed, progress,
                        f"{elapsed:.1f} h sur {challenge.hours:g} h de jeu.")


FINAL_STATES = frozenset({ST_WON, ST_LOST, ST_IMPRECISE})


@dataclass
class ActiveWindow:
    """Un défi lancé : son point de départ et son état, mis à jour à chaque lecture.

    Un résultat final (réussi, échoué, imprécis) ne change plus, comme un objectif validé.
    """

    id: str
    challenge: WindowChallenge
    start: Checkpoint
    state: str = ST_OPEN
    message: str = ""

    @property
    def final(self) -> bool:
        return self.state in FINAL_STATES

    def refresh(self, now: Checkpoint) -> WindowResult | None:
        """Re-evaluate against the latest reading. A final result is never recomputed."""
        if self.final:
            return None
        result = evaluate_window(self.challenge, self.start, now)
        self.state = result.state
        self.message = result.message
        return result

    def to_dict(self) -> dict:
        ch = self.challenge
        return {
            "id": self.id,
            "challenge": {
                "name": ch.name,
                "stat": ch.stat,
                "target": ch.target,
                "hours": ch.hours,
                "tolerance": ch.tolerance_hours,
            },
            "start": self.start.to_dict(),
            "state": self.state,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActiveWindow:
        """Raises ValueError/TypeError/KeyError on a malformed entry (the caller skips it)."""
        raw = data["challenge"]
        challenge = WindowChallenge(
            name=str(raw["name"]),
            stat=str(raw["stat"]),
            target=float(raw["target"]),
            hours=float(raw.get("hours", 24.0)),
            tolerance_hours=float(raw.get("tolerance", 1.0)),
        )
        return cls(
            id=str(data["id"]),
            challenge=challenge,
            start=Checkpoint.from_dict(data.get("start", {})),
            state=str(data.get("state", ST_OPEN)),
            message=str(data.get("message", "")),
        )


def open_window(challenge: WindowChallenge, now: Checkpoint, window_id: str) -> ActiveWindow:
    """Start a challenge: its window opens at the checkpoint ``now``."""
    return ActiveWindow(id=window_id, challenge=challenge, start=now)


# Défis proposés au lancement (ajouter une entrée suffit).
WINDOW_PRESETS: tuple[WindowChallenge, ...] = (
    WindowChallenge("2 M€ de revenus de contrats en 24 h de jeu", "finance.missionIncome",
                    2_000_000.0),
)

STATE_LABELS_FR = {
    ST_OPEN: "En cours",
    ST_WON: "Réussi",
    ST_LOST: "Échoué",
    ST_IMPRECISE: "Imprécis",
    ST_UNAVAILABLE: "Indisponible",
}


def window_line(window: ActiveWindow) -> str:
    """One readable line for the dashboard: state, challenge name, and the reason."""
    label = STATE_LABELS_FR.get(window.state, window.state)
    head = f"{label} — {window.challenge.name}"
    return f"{head} : {window.message}" if window.message else head
