"""Drift-Regeln fuer ADRs — **kanonische Quelle**.

Herkunft: dev-hub ``apps/adr_lifecycle/drift_rules.py`` (dev-hub#374 §6
Schritt 1, dev-hub#376), hierher gehoben mit achimdehnert/platform#3457
Schritt 1. Die Funktionen sind 1:1 uebernommen — gleiche Namen, Signaturen
und Rueckgabewerte —, damit dev-hub ``drift_rules.py`` auf einen Re-Export
dieses Moduls umstellen kann. Wer eine Regel aendert, aendert sie hier und
nur hier.

Einziger Unterschied zur Quelle: ``ADRStatus`` und ``DriftReason`` kamen dort
aus ``apps.adr_lifecycle.models`` (Django ``TextChoices``). Hier sind sie als
:class:`enum.StrEnum` ohne Django nachgebildet — gleiche Member, gleiche
Werte, ``.label`` wie bei ``TextChoices``. Weil ``StrEnum``-Member als ``str``
gleich *und* hash-gleich zu ihrem Wert sind, funktionieren die Regeln auch mit
reinen Strings oder dev-hubs ``TextChoices``-Membern als Eingabe.

Drei Klassen, drei Wirkungen (dev-hub#374 §2):

* **drift** — handeln: setzt ``review_needed``, erscheint in der Review-Liste.
* **wirkung** — vorausschauend: eigene Liste "bald pruefen" mit Faelligkeit.
* **form** — Qualitaet: Quote je Repo, kein Flag.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

__all__ = [
    "ADRStatus",
    "CONFIRMATION_HEADING_RE",
    "CONFIRMATION_PFLICHT_STATUSES",
    "DriftReason",
    "KLASSEN",
    "KLASSE_DRIFT",
    "KLASSE_FORM",
    "KLASSE_WIRKUNG",
    "REGEL_KLASSE",
    "REVIEW_VORLAUF_TAGE",
    "TAGE_JE_MONAT",
    "TERMINAL_STATUSES",
    "alle_gruende",
    "faelligkeit",
    "hat_confirmation_abschnitt",
    "ist_review_noetig",
    "leere_klassen",
    "pruefe_adr",
]


class ADRStatus(StrEnum):
    """ADR Status — Werte identisch zu dev-hub ``models.ADRStatus``."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"

    @property
    def label(self) -> str:
        """Anzeigename wie bei Django ``TextChoices``."""
        return _ADR_STATUS_LABELS[self]


class DriftReason(StrEnum):
    """Drift Reason — Werte identisch zu dev-hub ``models.DriftReason``."""

    NO_FRONTMATTER = "no_frontmatter"
    STATUS_UNKNOWN = "status_unknown"
    STALE_NO_UPDATE = "stale_no_update"
    SUPERSEDED_REF = "superseded_ref"
    MISSING_CONFIRMATION = "missing_confirmation"
    REVIEW_DUE = "review_due"
    PATH_NOT_FOUND = "path_not_found"
    DUPLICATE_TOPIC = "duplicate_topic"

    @property
    def label(self) -> str:
        """Anzeigename wie bei Django ``TextChoices``."""
        return _DRIFT_REASON_LABELS[self]


_ADR_STATUS_LABELS: dict[str, str] = {
    ADRStatus.DRAFT: "Draft",
    ADRStatus.PROPOSED: "Proposed",
    ADRStatus.ACCEPTED: "Accepted",
    ADRStatus.DEPRECATED: "Deprecated",
    ADRStatus.SUPERSEDED: "Superseded",
    ADRStatus.REJECTED: "Rejected",
}

_DRIFT_REASON_LABELS: dict[str, str] = {
    DriftReason.NO_FRONTMATTER: "Kein YAML-Frontmatter",
    DriftReason.STATUS_UNKNOWN: "Status unbekannt (?)",
    DriftReason.STALE_NO_UPDATE: "Kein Update seit > Schwellenwert",
    DriftReason.SUPERSEDED_REF: "Referenziert deprecated/superseded ADR",
    DriftReason.MISSING_CONFIRMATION: "Kein Confirmation-Abschnitt",
    DriftReason.REVIEW_DUE: "Prüftermin (review_by) fällig oder in ≤ 30 Tagen",
    DriftReason.PATH_NOT_FOUND: "Referenzierte Dateipfade existieren nicht",
    DriftReason.DUPLICATE_TOPIC: "Doppeltes Thema (anderes ADR supersedes)",
}

KLASSE_DRIFT = "drift"
KLASSE_WIRKUNG = "wirkung"
KLASSE_FORM = "form"
KLASSEN: tuple[str, ...] = (KLASSE_DRIFT, KLASSE_WIRKUNG, KLASSE_FORM)

# Welche Regel in welche Klasse faellt. Eine Regel ohne Eintrag hier ist ein
# Programmierfehler, kein stiller Default — siehe ``_klasse``.
REGEL_KLASSE: dict[str, str] = {
    DriftReason.NO_FRONTMATTER: KLASSE_DRIFT,
    DriftReason.STATUS_UNKNOWN: KLASSE_DRIFT,
    DriftReason.SUPERSEDED_REF: KLASSE_DRIFT,
    DriftReason.STALE_NO_UPDATE: KLASSE_WIRKUNG,
    DriftReason.REVIEW_DUE: KLASSE_WIRKUNG,
    DriftReason.MISSING_CONFIRMATION: KLASSE_FORM,
}

# Abgeschlossene Entscheidungen: dort handelt niemand mehr auf einen Befund
# (dev-hub#374 B3 — 9 superseded/deprecated ADRs standen wegen einer fehlenden
# Confirmation in der Review-Liste).
TERMINAL_STATUSES: frozenset[str] = frozenset({ADRStatus.DEPRECATED, ADRStatus.SUPERSEDED, ADRStatus.REJECTED})

# Nur fuer diese Status ist ein Confirmation-Abschnitt ueberhaupt gefordert.
CONFIRMATION_PFLICHT_STATUSES: frozenset[str] = frozenset({ADRStatus.ACCEPTED, ADRStatus.PROPOSED})

# ``## Confirmation``, ``### 8. Confirmation``, ``## Bestätigung``, ``## Nachweis``.
# Die eigene Vorlage (platform:docs/templates/adr-template.md) nummeriert die
# Ueberschrift — der alte Woertlich-Vergleich erkannte sie nicht (B2).
CONFIRMATION_HEADING_RE = re.compile(
    r"^#{2,3}\s*(\d+\.\s*)?(Confirmation|Bestätigung|Nachweis)\b",
    re.MULTILINE | re.IGNORECASE,
)

# Vorlauf fuer den Prueftermin: wie ein TUeV-Termin wird 30 Tage vorher
# gemeldet (dev-hub#374 OOTB-3).
REVIEW_VORLAUF_TAGE = 30

# Naeherung 30 Tage je Monat — gleiche Rechnung wie ``iil_adrfw.audit`` (audit_staleness).
TAGE_JE_MONAT = 30


def leere_klassen() -> dict[str, list[str]]:
    """``{"drift": [], "wirkung": [], "form": []}`` — die Form des Ergebnisses."""
    return {klasse: [] for klasse in KLASSEN}


def hat_confirmation_abschnitt(content: str) -> bool:
    """Traegt der Markdown-Text eine Confirmation-/Bestaetigungs-/Nachweis-Ueberschrift?"""
    return CONFIRMATION_HEADING_RE.search(content or "") is not None


def faelligkeit(
    *,
    review_by: date | None,
    updated_at: datetime | None,
    staleness_months: int,
) -> date | None:
    """Wann ein ADR zur Pruefung faellig ist.

    ``review_by`` aus dem Frontmatter gewinnt; ohne ihn gilt das letzte
    Aenderungsdatum plus ``staleness_months``. ``None``, wenn beides fehlt.
    """
    if review_by is not None:
        return review_by
    if updated_at is not None:
        return (updated_at + timedelta(days=TAGE_JE_MONAT * staleness_months)).date()
    return None


def pruefe_adr(
    *,
    status: str,
    content: str,
    related_adrs: list[Any] | None,
    status_map: dict[str, str],
    updated_at: datetime | None,
    review_by: date | None,
    staleness_months: int,
    heute: date,
) -> dict[str, list[str]]:
    """Alle Regeln auf ein ADR anwenden — reine Funktion, kein ORM.

    Rueckgabe ``{"drift": [...], "wirkung": [...], "form": [...]}`` mit
    ``DriftReason``-Werten. Abgeschlossene ADRs (``TERMINAL_STATUSES``)
    liefern leere Klassen.
    """
    klassen = leere_klassen()
    if status in TERMINAL_STATUSES:
        return klassen

    def melde(grund: str) -> None:
        klassen[_klasse(grund)].append(grund)

    # --- Drift: handeln -------------------------------------------------
    if not (content or "").strip().startswith("---"):
        melde(DriftReason.NO_FRONTMATTER)

    if not status or status == "?":
        melde(DriftReason.STATUS_UNKNOWN)

    for ref_id in related_adrs or []:
        if status_map.get(str(ref_id), "") in (ADRStatus.DEPRECATED, ADRStatus.SUPERSEDED):
            melde(DriftReason.SUPERSEDED_REF)
            break

    # --- Wirkung: vorausschauend ----------------------------------------
    # Ein gesetzter Prueftermin ersetzt das Alters-Signal vollstaendig
    # (OOTB-3); nur ohne ihn zaehlt das Datum der letzten Aenderung.
    if review_by is not None:
        if review_by <= heute + timedelta(days=REVIEW_VORLAUF_TAGE):
            melde(DriftReason.REVIEW_DUE)
    elif updated_at is not None:
        schwelle = heute - timedelta(days=TAGE_JE_MONAT * staleness_months)
        if updated_at.date() < schwelle:
            melde(DriftReason.STALE_NO_UPDATE)

    # --- Form: Qualitaet ------------------------------------------------
    if status in CONFIRMATION_PFLICHT_STATUSES and not hat_confirmation_abschnitt(content):
        melde(DriftReason.MISSING_CONFIRMATION)

    return klassen


def alle_gruende(klassen: dict[str, list[str]]) -> list[str]:
    """Flache Liste aller Gruende in Klassen-Reihenfolge (fuer ``drift_reasons``)."""
    return [grund for klasse in KLASSEN for grund in klassen.get(klasse, [])]


def ist_review_noetig(klassen: dict[str, list[str]]) -> bool:
    """``review_needed`` folgt allein aus der Drift-Klasse."""
    return bool(klassen.get(KLASSE_DRIFT))


def _klasse(grund: str) -> str:
    try:
        return REGEL_KLASSE[grund]
    except KeyError as fehler:
        raise ValueError(f"Regel {str(grund)!r} hat keine Klasse in REGEL_KLASSE") from fehler
