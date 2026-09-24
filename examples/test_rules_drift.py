"""Drift-Regeln je ADR — Klassen, Positiv-/Negativkontrollen (dev-hub#374 §2, §6 Schritt 1).

Portiert aus dev-hub ``apps/adr_lifecycle/tests/test_drift_check.py``
(achimdehnert/platform#3457 Schritt 1). Alle Tests auf den reinen Regeln sind
1:1 uebernommen; der ORM-Test ``test_should_map_model_onto_the_pure_rules``
(Bruecke ``ADR``-Modell -> ``run_drift_check``) bleibt in dev-hub, weil er
Django braucht.

Der alte Detektor verglich woertlich auf ``## Confirmation`` und erkannte damit
die eigene Vorlage (``## 8. Confirmation``) nicht; 374 von 406 Review-Eintraegen
waren allein dieser Stilbefund. Diese Tests halten fest, was ein Confirmation-
Abschnitt ist, in welche Klasse jeder Grund faellt und dass nur Drift ein
Review ausloest.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from iil_adrfw.rules import drift as drift_rules
from iil_adrfw.rules.drift import ADRStatus, DriftReason

FRONTMATTER = "---\nid: ADR-001\nstatus: accepted\n---\n"
HEUTE = date(2026, 9, 23)
JETZT = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _pruefe(**kw: Any) -> dict[str, list[str]]:
    args: dict[str, Any] = {
        "status": ADRStatus.ACCEPTED,
        "content": FRONTMATTER + "# T\n\n## 8. Confirmation\n\nBeleg\n",
        "related_adrs": [],
        "status_map": {},
        "updated_at": JETZT,
        "review_by": None,
        "staleness_months": 12,
        "heute": HEUTE,
    }
    args.update(kw)
    return drift_rules.pruefe_adr(**args)


@pytest.mark.parametrize(
    "heading",
    [
        "## Confirmation",
        "### Confirmation",
        "## 8. Confirmation",
        "##  8.  Confirmation",
        "### 7. Bestätigung",
        "## Nachweis",
        "## confirmation",
    ],
)
def test_should_recognize_numbered_and_german_confirmation_headings(heading):
    """Positivkontrolle: die eigene Vorlage nummeriert die Ueberschrift."""
    assert drift_rules.hat_confirmation_abschnitt(f"# Titel\n\n{heading}\n\nText\n")


@pytest.mark.parametrize(
    "content",
    [
        "# Titel\n\nText ohne Abschnitt\n",
        "# Confirmation\n",  # H1 ist der Titel, kein Abschnitt
        "#### Confirmation\n",  # zu tief
        "Wir warten auf Confirmation vom Kunden.\n",  # Fliesstext
        "## Confirmations-Flow\n",  # anderes Wort
        "",
    ],
)
def test_should_not_recognize_text_without_a_confirmation_heading(content):
    """Negativkontrolle: kein Abschnitt, kein Treffer."""
    assert not drift_rules.hat_confirmation_abschnitt(content)


def test_should_return_all_three_classes_even_when_empty():
    assert _pruefe() == {"drift": [], "wirkung": [], "form": []}


def test_should_put_missing_confirmation_in_form_class_only():
    """Form-Befund: bleibt sichtbar, loest aber kein Review aus."""
    klassen = _pruefe(content=FRONTMATTER + "# T\n\nText\n")

    assert klassen == {"drift": [], "wirkung": [], "form": [DriftReason.MISSING_CONFIRMATION]}
    assert drift_rules.ist_review_noetig(klassen) is False
    assert drift_rules.alle_gruende(klassen) == [DriftReason.MISSING_CONFIRMATION]


@pytest.mark.parametrize("status", [ADRStatus.DRAFT, ADRStatus.PROPOSED, ADRStatus.ACCEPTED])
def test_should_demand_confirmation_only_for_proposed_and_accepted(status):
    klassen = _pruefe(status=status, content=FRONTMATTER + "# T\n")

    erwartet = status in (ADRStatus.PROPOSED, ADRStatus.ACCEPTED)
    assert (DriftReason.MISSING_CONFIRMATION in klassen["form"]) is erwartet


@pytest.mark.parametrize("status", [ADRStatus.SUPERSEDED, ADRStatus.DEPRECATED, ADRStatus.REJECTED])
def test_should_never_flag_terminal_adrs(status):
    """Abgeschlossen heisst abgeschlossen — auch ohne Frontmatter, mit totem Verweis, ueberfaellig."""
    klassen = _pruefe(
        status=status,
        content="# Kein Frontmatter\n",
        related_adrs=["ADR-001"],
        status_map={"ADR-001": ADRStatus.SUPERSEDED},
        review_by=HEUTE - timedelta(days=100),
    )

    assert klassen == drift_rules.leere_klassen()


def test_should_classify_frontmatter_status_and_reference_as_drift():
    klassen = _pruefe(
        status="?",
        content="# T\n",
        related_adrs=["ADR-009"],
        status_map={"ADR-009": ADRStatus.DEPRECATED},
    )

    assert klassen["drift"] == [
        DriftReason.NO_FRONTMATTER,
        DriftReason.STATUS_UNKNOWN,
        DriftReason.SUPERSEDED_REF,
    ]
    assert drift_rules.ist_review_noetig(klassen) is True


def test_should_classify_staleness_as_wirkung_not_drift():
    klassen = _pruefe(updated_at=JETZT - timedelta(days=400))

    assert klassen["wirkung"] == [DriftReason.STALE_NO_UPDATE]
    assert klassen["drift"] == []
    assert drift_rules.ist_review_noetig(klassen) is False


def test_should_not_report_staleness_within_threshold():
    assert _pruefe(updated_at=JETZT - timedelta(days=300))["wirkung"] == []


@pytest.mark.parametrize(
    ("review_by", "erwartet"),
    [
        (HEUTE - timedelta(days=1), True),  # ueberfaellig
        (HEUTE, True),
        (HEUTE + timedelta(days=30), True),  # Vorlauf-Grenze
        (HEUTE + timedelta(days=31), False),
    ],
)
def test_should_report_review_due_thirty_days_ahead(review_by, erwartet):
    """OOTB-3: wie ein TUeV-Termin, 30 Tage vorher."""
    klassen = _pruefe(review_by=review_by)

    assert (DriftReason.REVIEW_DUE in klassen["wirkung"]) is erwartet


def test_should_let_review_by_replace_the_age_signal():
    """Ein gesetzter Prueftermin ersetzt updated_at vollstaendig — kein Doppelsignal."""
    klassen = _pruefe(updated_at=JETZT - timedelta(days=400), review_by=HEUTE + timedelta(days=90))

    assert klassen["wirkung"] == []


def test_should_compute_due_date_from_review_by_or_age():
    assert drift_rules.faelligkeit(review_by=HEUTE, updated_at=JETZT, staleness_months=12) == HEUTE
    assert drift_rules.faelligkeit(review_by=None, updated_at=JETZT, staleness_months=12) == HEUTE + timedelta(days=360)
    assert drift_rules.faelligkeit(review_by=None, updated_at=None, staleness_months=12) is None


def test_should_refuse_a_rule_without_class():
    """Jede Regel braucht eine Klasse — ein stiller Default waere die alte Vermischung."""
    with pytest.raises(ValueError, match="path_not_found"):
        drift_rules._klasse(DriftReason.PATH_NOT_FOUND)


# --- Nur hier: Vertrag der Django-freien Enum-Nachbildung --------------------


def test_should_keep_enum_values_identical_to_dev_hub_models():
    """Die Werte sind DB-Inhalt in dev-hub — eine Abweichung waere stiller Datenbruch."""
    assert [s.value for s in ADRStatus] == [
        "draft",
        "proposed",
        "accepted",
        "deprecated",
        "superseded",
        "rejected",
    ]
    assert [r.value for r in DriftReason] == [
        "no_frontmatter",
        "status_unknown",
        "stale_no_update",
        "superseded_ref",
        "missing_confirmation",
        "review_due",
        "path_not_found",
        "duplicate_topic",
    ]
    assert all(member.label for member in [*ADRStatus, *DriftReason])


def test_should_accept_plain_strings_as_status_and_reason():
    """Aufrufer ohne diese Enums (dev-hub ``TextChoices``, rohe DB-Werte) bekommen dasselbe Ergebnis."""
    klassen = _pruefe(
        status="accepted",
        content="# T\n",
        related_adrs=["ADR-009"],
        status_map={"ADR-009": "superseded"},
    )

    assert drift_rules.alle_gruende(klassen) == [
        "no_frontmatter",
        "superseded_ref",
        "missing_confirmation",
    ]
    assert (
        drift_rules.pruefe_adr(
            status="rejected",
            content="",
            related_adrs=None,
            status_map={},
            updated_at=None,
            review_by=None,
            staleness_months=12,
            heute=HEUTE,
        )
        == drift_rules.leere_klassen()
    )
