"""Error messages stay short whatever the size of the offending input.

An externally supplied string (a name, a unit, a tag, a path, a key) is quoted through the truncating
helper, so a megabyte of hostile text cannot become a megabyte of log line.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ralmon.spec import (
    CarePlan,
    HmacSha256PlanVerifier,
    RegistryEntry,
    TemplateInstance,
    load_registry,
    load_templates,
    normalise,
    rank_alerts,
    verify_plan,
)
from ralmon.spec.integrity import canonical_plan_bytes
from ralmon.spec.registry import as_duration_ms, as_priority

from .helpers import F0_PATH, STEP_MS, TEMPLATES_PATH, f0_doc, read_yaml, write_yaml

BIG = "x" * 1_000_000
HUGE_NAME = "n" * 200_000
MAX_MESSAGE = (
    4_000  # characters; the messages are a few hundred when the input is small
)


def message_of(call: Callable[[], Any]) -> str:
    try:
        call()
    except Exception as exc:  # noqa: BLE001 - any exception: only its message is measured
        return str(exc)
    pytest.fail("the call did not raise")


def assert_short(call: Callable[[], Any]) -> None:
    message = message_of(call)
    assert 0 < len(message) <= MAX_MESSAGE, len(message)


def library_doc() -> dict[str, Any]:
    doc = read_yaml(TEMPLATES_PATH)
    assert isinstance(doc, dict)
    return doc


def test_registry_lookups_quote_a_long_name_briefly(f0_registry: Any) -> None:
    assert_short(lambda: f0_registry.get(BIG))
    assert_short(lambda: f0_registry.bounds(BIG))
    assert_short(lambda: f0_registry.is_set(BIG))
    assert "x" * 20 in message_of(lambda: f0_registry.get(BIG))  # still says which name


def test_casts_quote_a_long_name_or_unit_briefly() -> None:
    entry = RegistryEntry(BIG, 1.5, "ms", "r", "s", None)
    assert_short(lambda: as_duration_ms(entry))
    assert_short(lambda: as_duration_ms(dataclasses.replace(entry, name="n", unit=BIG)))
    assert_short(lambda: as_priority(dataclasses.replace(entry, unit="1", value=0.0)))
    assert_short(lambda: as_priority(dataclasses.replace(entry, unit=BIG, value=1.0)))


def test_numeric_functions_and_ranking_quote_long_values_briefly() -> None:
    assert_short(lambda: normalise(BIG, 1.0))
    assert_short(lambda: normalise(1.0, BIG))
    assert_short(lambda: rank_alerts(BIG))  # type: ignore[arg-type]
    big_alert = SimpleNamespace(priority=BIG, sigma_norm=0.0, t_ms=1, instance_key="k")
    assert_short(lambda: rank_alerts([big_alert]))
    key_alert = SimpleNamespace(
        priority=1, sigma_norm=0.0, t_ms=1, instance_key=BIG.encode()
    )
    assert_short(lambda: rank_alerts([key_alert]))


def test_paths_are_quoted_briefly(tmp_path: Path) -> None:
    assert_short(lambda: load_registry(BIG))
    assert_short(lambda: load_registry(str(tmp_path / (BIG + ".yaml"))))
    assert_short(lambda: load_registry(BIG, step_ms=1))
    assert_short(lambda: load_templates(BIG, None))


def _registry_cases() -> list[tuple[str, Callable[[dict[str, Any]], None]]]:
    def duplicate(doc: dict[str, Any]) -> None:
        first = dict(doc["entries"][0], name=HUGE_NAME)
        doc["entries"].extend([first, dict(first)])

    def unknown_top(doc: dict[str, Any]) -> None:
        doc[HUGE_NAME] = 1

    def unknown_entry_key(doc: dict[str, Any]) -> None:
        doc["entries"][0][HUGE_NAME] = 1

    def window(doc: dict[str, Any]) -> None:
        doc["window_parameters"].append(HUGE_NAME)

    def term(doc: dict[str, Any]) -> None:
        doc["derived"][0]["formula"] = HUGE_NAME

    def derived_unit(doc: dict[str, Any]) -> None:
        doc["derived"][0]["name"] = HUGE_NAME
        doc["derived"][0]["unit"] = "mmHg"

    def required_by(doc: dict[str, Any]) -> None:
        doc["unset"].append(
            {
                "parameter": "pending",
                "unit": "ms",
                "required_by": [HUGE_NAME],
                "note": "n",
            }
        )

    def bounds(doc: dict[str, Any]) -> None:
        for side, value in (("lower", 9.0), ("upper", 1.0)):
            doc["entries"].append(
                {
                    "name": f"bound_{HUGE_NAME}_{side}",
                    "value": value,
                    "unit": "mmHg",
                    "rationale": "FIXTURE-ONLY row; illustrative, unverified",
                    "source_ref": "test",
                    "reviewed_by": None,
                }
            )

    def status(doc: dict[str, Any]) -> None:
        doc["review_status"] = HUGE_NAME

    def version(doc: dict[str, Any]) -> None:
        doc["registry_version"] = HUGE_NAME

    def override(doc: dict[str, Any]) -> None:
        doc["overrides"] = [
            {
                "name": HUGE_NAME,
                "min": 0.0,
                "max": 1.0,
                "rationale": "r",
                "source_ref": "s",
                "reviewed_by": None,
            }
        ]

    def unit(doc: dict[str, Any]) -> None:
        doc["entries"][0]["unit"] = HUGE_NAME

    def rationale(doc: dict[str, Any]) -> None:
        doc["entries"][0]["rationale"] = HUGE_NAME

    def value(doc: dict[str, Any]) -> None:
        doc["entries"][0]["value"] = HUGE_NAME

    def fixture_rows(doc: dict[str, Any]) -> None:
        for index in range(400):
            doc["entries"].append(
                {
                    "name": f"fixture_{'f' * 500}_{index}",
                    "value": 1.0,
                    "unit": "dose",
                    "rationale": "FIXTURE-ONLY row; illustrative, unverified",
                    "source_ref": "test",
                    "reviewed_by": None,
                }
            )

    cases = [
        duplicate,
        unknown_top,
        unknown_entry_key,
        window,
        term,
        derived_unit,
        required_by,
        bounds,
        status,
        version,
        override,
        unit,
        rationale,
        value,
        fixture_rows,
    ]
    return [(case.__name__, case) for case in cases]


@pytest.mark.parametrize(
    ("label", "mutate"),
    _registry_cases(),
    ids=[label for label, _ in _registry_cases()],
)
def test_registry_file_errors_quote_long_text_briefly(
    tmp_path: Path, label: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    doc = f0_doc()
    mutate(doc)
    path = write_yaml(tmp_path, doc)
    assert_short(
        lambda: load_registry(
            path, step_ms=STEP_MS, allow_fixture_only=label != "fixture_rows"
        )
    )


def test_a_long_yaml_tag_is_quoted_briefly(tmp_path: Path) -> None:
    text = F0_PATH.read_text(encoding="utf-8").replace(
        "pathology: hypertension", f"pathology: !{HUGE_NAME} x", 1
    )
    path = tmp_path / "tag.yaml"
    path.write_text(text, encoding="utf-8")
    assert_short(lambda: load_registry(path, allow_fixture_only=True))


def _template_cases() -> list[tuple[str, Callable[[dict[str, Any]], None]]]:
    def row_id(doc: dict[str, Any]) -> None:
        doc["templates"][0]["id"] = HUGE_NAME

    def second_id(doc: dict[str, Any]) -> None:
        doc["templates"][0]["id"] = HUGE_NAME
        doc["templates"][1]["id"] = HUGE_NAME

    def unknown_key(doc: dict[str, Any]) -> None:
        doc["templates"][0][HUGE_NAME] = 1

    def unknown_top(doc: dict[str, Any]) -> None:
        doc[HUGE_NAME] = 1

    def kind(doc: dict[str, Any]) -> None:
        doc["templates"][0]["kind"] = HUGE_NAME

    def unit(doc: dict[str, Any]) -> None:
        doc["templates"][0]["unit"] = HUGE_NAME

    def formula(doc: dict[str, Any]) -> None:
        doc["templates"][0]["formula_past_time"] = HUGE_NAME

    def signal(doc: dict[str, Any]) -> None:
        doc["templates"][0]["signals"].append(HUGE_NAME)

    def param(doc: dict[str, Any]) -> None:
        doc["templates"][0]["params"].append(HUGE_NAME)
        doc["templates"][0]["formula_past_time"] += " and " + HUGE_NAME

    def scale_param(doc: dict[str, Any]) -> None:
        doc["templates"][0]["scale_param"] = HUGE_NAME

    def obligation(doc: dict[str, Any]) -> None:
        doc["templates"][0]["creates_robot_obligation"] = HUGE_NAME

    def version(doc: dict[str, Any]) -> None:
        doc["library_version"] = HUGE_NAME

    def row(doc: dict[str, Any]) -> None:
        doc["templates"][0] = HUGE_NAME

    cases = [
        row_id,
        second_id,
        unknown_key,
        unknown_top,
        kind,
        unit,
        formula,
        signal,
        param,
        scale_param,
        obligation,
        version,
        row,
    ]
    return [(case.__name__, case) for case in cases]


@pytest.mark.parametrize(
    ("label", "mutate"),
    _template_cases(),
    ids=[label for label, _ in _template_cases()],
)
def test_template_file_errors_quote_long_text_briefly(
    tmp_path: Path,
    f0_registry: Any,
    label: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    doc = library_doc()
    mutate(doc)
    path = write_yaml(tmp_path, doc, "templates.yaml")
    assert_short(lambda: load_templates(path, f0_registry))


def _plan(**changes: Any) -> CarePlan:
    base = CarePlan("cp", "pt", "p", "0.0.0", (), (), 1, None)
    return dataclasses.replace(base, **changes)


def test_plan_errors_quote_long_values_briefly() -> None:
    verifier = HmacSha256PlanVerifier(b"key")
    assert_short(
        lambda: verify_plan(_plan(registry_version=BIG), None, registry_version="1.0.0")
    )
    assert_short(lambda: verify_plan(_plan(), None, registry_version=BIG))
    assert_short(lambda: verify_plan(_plan(signature=1), verifier))
    assert_short(lambda: canonical_plan_bytes(_plan(care_plan_id=BIG.encode())))
    assert_short(lambda: canonical_plan_bytes(_plan(instances=BIG)))
    assert_short(lambda: canonical_plan_bytes(_plan(schedule=BIG)))
    assert_short(lambda: canonical_plan_bytes(_plan(plan_version=BIG)))
    wrong = TemplateInstance("range", "k", {BIG: BIG}, 1)  # type: ignore[arg-type]
    assert_short(lambda: canonical_plan_bytes(_plan(instances=(wrong,))))
    assert_short(lambda: canonical_plan_bytes(_plan(instances=(BIG,))))  # type: ignore[arg-type]
    odd_type = type(BIG[:200_000], (), {})()
    assert_short(lambda: canonical_plan_bytes(_plan(care_plan_id=odd_type)))
    assert_short(lambda: verifier.verify(BIG, "0" * 64))  # type: ignore[arg-type]
    assert_short(lambda: HmacSha256PlanVerifier(odd_type))  # type: ignore[arg-type]
    assert_short(lambda: verify_plan(_plan(), None, require_signature=BIG))  # type: ignore[arg-type]
    assert_short(lambda: verify_plan(BIG, verifier))  # type: ignore[arg-type]


def test_a_huge_integer_in_a_message_cannot_break_the_message() -> None:
    """Python refuses to turn an integer of thousands of digits into text; the message must not need it."""
    huge = 10**5000
    alert = SimpleNamespace(priority=-huge, sigma_norm=0.0, t_ms=1, instance_key="k")
    with pytest.raises(ValueError, match="priority must be an integer >= 1"):
        rank_alerts([alert])
    with pytest.raises(ValueError, match="scale must be a positive"):
        normalise(1.0, -huge)
    with pytest.raises(Exception, match="step_ms"):
        load_registry(F0_PATH, step_ms=-huge, allow_fixture_only=True)
    with pytest.raises(Exception, match="registry_version"):
        verify_plan(_plan(registry_version="1"), None, registry_version=huge)  # type: ignore[arg-type]
