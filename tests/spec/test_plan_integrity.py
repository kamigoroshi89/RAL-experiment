"""Integrity of a distributed care plan (analisi §4.9 item 7, R1-W9): canonical bytes, HMAC-SHA256,
``verify_plan``. Tests 24 to 28 of WS05-T03 plus tamper tests for every field, signature-format edge
cases and robust inputs.

The expected digests come from ``tests/fixtures/spec/make_plan_golden.sh`` (``openssl dgst -sha256
-hmac``) and the expected canonical bytes are written by hand in that script, so neither the canonical
form nor the HMAC expectation is produced by the code under test.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from ralmon.spec import (
    CarePlan,
    HmacSha256PlanVerifier,
    PlanIntegrityError,
    PlanVerifier,
    TemplateId,
    TemplateInstance,
    verify_plan,
)
from ralmon.spec import integrity as integrity_module
from ralmon.spec.integrity import canonical_plan_bytes

from .helpers import FIXTURES

KEY = (FIXTURES / "plan_golden.key").read_bytes()
GOLDEN = {
    name: (
        (FIXTURES / f"{name}.canonical.json").read_bytes(),
        (FIXTURES / f"{name}.hmac_sha256").read_text(encoding="ascii").strip(),
    )
    for name in ("plan_a", "plan_b")
}


def plan_a(**changes: Any) -> CarePlan:
    base = CarePlan(
        care_plan_id="cp-fixture-001",
        pathway_template_id="pt-hypertension-v1",
        patient_id="p-0001",
        registry_version="0.0.0",
        instances=(
            TemplateInstance(
                TemplateId.RANGE,
                "range@32400000",
                {"bp_band_low": 110.0, "bp_band_high": 140.0},
                32_400_000,
            ),
            TemplateInstance(
                TemplateId.RESP,
                "resp@25200000",
                {"delta1": 3_600_000.0, "delta2": 10_800_000.0},
                None,
            ),
        ),
        schedule=(25_200_000, 32_400_000, 75_600_000),
        plan_version=3,
        signature=None,
    )
    return dataclasses.replace(base, **changes)


def plan_b() -> CarePlan:
    return CarePlan(
        care_plan_id="cp-fixture-002",
        pathway_template_id="pt-ü",
        patient_id="pätient",
        registry_version="0.0.0",
        instances=[],
        schedule=[],
        plan_version=0,
        signature=None,
    )


def signed(plan: CarePlan, verifier: HmacSha256PlanVerifier | None = None) -> CarePlan:
    verifier = verifier or HmacSha256PlanVerifier(KEY)
    return dataclasses.replace(plan, signature=verifier.sign(plan))


# --- test 24 -----------------------------------------------------------------------------


def test_canonical_bytes_ignore_signature_and_mapping_order() -> None:
    base = plan_a()
    other_signature = plan_a(signature="whatever")
    assert canonical_plan_bytes(base) == canonical_plan_bytes(other_signature)
    first, second = base.instances
    reordered = dataclasses.replace(
        first, param_values={"bp_band_high": 140.0, "bp_band_low": 110.0}
    )
    shuffled = plan_a(instances=(reordered, second))
    assert canonical_plan_bytes(shuffled) == canonical_plan_bytes(base)
    data = canonical_plan_bytes(base)
    assert isinstance(data, bytes)
    text = data.decode("utf-8")
    assert " " not in text.replace("pt-hypertension-v1", "")  # compact separators
    assert "\n" not in text
    parsed = json.loads(text)
    assert list(parsed) == sorted(parsed)  # sorted keys
    assert parsed["plan_version"] == 3 and isinstance(parsed["plan_version"], int)
    assert parsed["schedule"] == [25_200_000, 32_400_000, 75_600_000]
    assert "signature" not in parsed
    assert '"anchor_ms":32400000' in text  # integers as integers, no decimal point
    assert '"anchor_ms":null' in text
    assert '"bp_band_low":110.0' in text  # floats keep the point


def test_canonical_bytes_cover_every_field_except_the_signature() -> None:
    names = {f.name for f in dataclasses.fields(CarePlan)} - {"signature"}
    assert names == set(json.loads(canonical_plan_bytes(plan_a())))


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_canonical_bytes_equal_the_hand_written_golden(name: str) -> None:
    plan = plan_a() if name == "plan_a" else plan_b()
    assert canonical_plan_bytes(plan) == GOLDEN[name][0]


def test_canonical_bytes_are_utf8_and_not_escaped() -> None:
    data = canonical_plan_bytes(plan_b())
    assert "pätient".encode() in data and "pt-ü".encode() in data
    assert b"\\u" not in data


def test_the_order_of_sequences_is_part_of_the_content() -> None:
    base = plan_a()
    assert canonical_plan_bytes(
        plan_a(schedule=tuple(reversed(base.schedule)))
    ) != canonical_plan_bytes(base)
    assert canonical_plan_bytes(
        plan_a(instances=tuple(reversed(base.instances)))
    ) != canonical_plan_bytes(base)


def test_lists_and_tuples_have_one_canonical_form() -> None:
    base = plan_a()
    as_lists = plan_a(instances=list(base.instances), schedule=list(base.schedule))
    assert canonical_plan_bytes(as_lists) == canonical_plan_bytes(base)


def test_integral_floats_and_ints_in_param_values_have_one_form() -> None:
    """A parameter is a float by contract; ``2`` and ``2.0`` (a ROS message gives floats) sign alike."""
    first = TemplateInstance(TemplateId.COUNT, "count@0", {"dose_max_24h": 2}, None)
    second = TemplateInstance(TemplateId.COUNT, "count@0", {"dose_max_24h": 2.0}, None)
    assert canonical_plan_bytes(plan_a(instances=(first,))) == canonical_plan_bytes(
        plan_a(instances=(second,))
    )
    assert b'"dose_max_24h":2.0' in canonical_plan_bytes(plan_a(instances=(first,)))


def test_negative_zero_is_distinct_from_zero() -> None:
    """Documented: the canonical text is ``repr``-based, so -0.0 and 0.0 are two different contents."""
    zero = plan_a(
        instances=(TemplateInstance(TemplateId.COUNT, "c", {"x": 0.0}, None),)
    )
    minus = plan_a(
        instances=(TemplateInstance(TemplateId.COUNT, "c", {"x": -0.0}, None),)
    )
    assert canonical_plan_bytes(zero) != canonical_plan_bytes(minus)


def test_template_may_be_an_enum_member_or_its_value() -> None:
    member = plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {}, 1),))
    plain = plan_a(instances=(TemplateInstance("range", "k", {}, 1),))  # type: ignore[arg-type]
    assert canonical_plan_bytes(member) == canonical_plan_bytes(plain)


# --- test 25 -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_hmac_signature_matches_independent_golden(name: str) -> None:
    plan = plan_a() if name == "plan_a" else plan_b()
    expected_digest = GOLDEN[name][1]
    verifier = HmacSha256PlanVerifier(KEY)
    assert verifier.sign(plan) == expected_digest
    assert verifier.verify(GOLDEN[name][0], expected_digest) is True


def test_the_digest_is_lowercase_hex_of_sha256_and_depends_on_the_key() -> None:
    digest = HmacSha256PlanVerifier(KEY).sign(plan_a())
    assert len(digest) == 64 and digest == digest.lower()
    assert digest != HmacSha256PlanVerifier(KEY + b"x").sign(plan_a())
    sha512 = hmac.new(KEY, GOLDEN["plan_a"][0], hashlib.sha512).hexdigest()
    assert digest != sha512[:64]
    plain_sha = hashlib.sha256(GOLDEN["plan_a"][0]).hexdigest()
    assert digest != plain_sha  # a keyed MAC, not a bare hash


def test_sign_ignores_an_existing_signature() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    assert verifier.sign(plan_a(signature="old")) == verifier.sign(plan_a())


# --- test 26 -----------------------------------------------------------------------------


def _tamper_cases() -> dict[str, Callable[[CarePlan], CarePlan]]:
    def instance(index: int, **changes: Any) -> Callable[[CarePlan], CarePlan]:
        def apply(plan: CarePlan) -> CarePlan:
            instances = list(plan.instances)
            instances[index] = dataclasses.replace(instances[index], **changes)
            return dataclasses.replace(plan, instances=tuple(instances))

        return apply

    def replace(**changes: Any) -> Callable[[CarePlan], CarePlan]:
        return lambda plan: dataclasses.replace(plan, **changes)

    return {
        "care_plan_id": replace(care_plan_id="cp-fixture-001x"),
        "pathway_template_id": replace(pathway_template_id="pt-hypertension-v2"),
        "patient_id": replace(patient_id="p-0002"),
        "registry_version": replace(registry_version="0.0.1"),
        "plan_version": replace(plan_version=4),
        "plan_version rollback": replace(plan_version=2),
        "schedule tick changed": replace(schedule=(25_200_000, 32_400_001, 75_600_000)),
        "schedule tick added": replace(
            schedule=(25_200_000, 32_400_000, 75_600_000, 80_000_000)
        ),
        "schedule tick removed": replace(schedule=(25_200_000, 32_400_000)),
        "schedule reordered": replace(schedule=(32_400_000, 25_200_000, 75_600_000)),
        "schedule emptied": replace(schedule=()),
        "instances emptied": replace(instances=()),
        "instances reordered": lambda p: dataclasses.replace(
            p, instances=tuple(reversed(p.instances))
        ),
        "instances one removed": lambda p: dataclasses.replace(
            p, instances=p.instances[:1]
        ),
        "instances one duplicated": lambda p: dataclasses.replace(
            p, instances=(*p.instances, p.instances[0])
        ),
        "instance.template": instance(0, template=TemplateId.HOLD),
        "instance.instance_key": instance(0, instance_key="range@32400001"),
        "instance.param_values value": instance(
            0, param_values={"bp_band_low": 111.0, "bp_band_high": 140.0}
        ),
        "instance.param_values key renamed": instance(
            0, param_values={"bp_band_low": 110.0, "bp_band_hig": 140.0}
        ),
        "instance.param_values key added": instance(
            0, param_values={"bp_band_low": 110.0, "bp_band_high": 140.0, "x": 1.0}
        ),
        "instance.param_values key removed": instance(
            0, param_values={"bp_band_low": 110.0}
        ),
        "instance.param_values emptied": instance(0, param_values={}),
        "instance.anchor_ms": instance(0, anchor_ms=32_400_001),
        "instance.anchor_ms to None": instance(0, anchor_ms=None),
        "instance.anchor_ms from None": instance(1, anchor_ms=0),
        "instance.param_values tiny change": instance(
            0, param_values={"bp_band_low": 110.00000000000001, "bp_band_high": 140.0}
        ),
    }


TAMPER = _tamper_cases()


@pytest.mark.parametrize("label", sorted(TAMPER))
def test_verify_plan_rejects_tampered_field(label: str) -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    good = signed(plan_a(), verifier)
    verify_plan(good, verifier)  # the untampered plan passes
    tampered = TAMPER[label](good)  # the signature stays that of the original
    assert tampered.signature == good.signature
    assert tampered != good
    with pytest.raises(PlanIntegrityError):
        verify_plan(tampered, verifier)


def test_every_field_of_care_plan_is_tamper_tested() -> None:
    """Completeness: a field added to ``CarePlan`` or ``TemplateInstance`` without a tamper case fails here."""
    top = {label.split(" ")[0] for label in TAMPER if not label.startswith("instance.")}
    fields = {f.name for f in dataclasses.fields(CarePlan)} - {"signature"}
    assert top == fields
    inner = {
        label.split(".")[1].split(" ")[0]
        for label in TAMPER
        if label.startswith("instance.")
    }
    assert inner == {f.name for f in dataclasses.fields(TemplateInstance)}


def test_changing_the_signature_itself_fails() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    good = signed(plan_a(), verifier)
    flipped = good.signature[:-1] + ("0" if good.signature[-1] != "0" else "1")  # type: ignore[index]
    with pytest.raises(PlanIntegrityError):
        verify_plan(dataclasses.replace(good, signature=flipped), verifier)


def test_a_signature_from_another_key_fails() -> None:
    other = HmacSha256PlanVerifier(b"another key")
    forged = signed(plan_a(), other)
    with pytest.raises(PlanIntegrityError):
        verify_plan(forged, HmacSha256PlanVerifier(KEY))


def test_replaying_an_old_signed_plan_at_the_same_version_verifies() -> None:
    """Honest limit (docs/formal/07 OP-T07-12 (h)): the signature cannot see replay at an equal version;
    the monitor refuses a lower ``plan_version`` when it loads (WS05-T04)."""
    verifier = HmacSha256PlanVerifier(KEY)
    old = signed(plan_a(), verifier)
    verify_plan(old, verifier)
    verify_plan(dataclasses.replace(old), verifier)


def test_the_verifier_can_also_sign_so_it_is_not_an_author_check() -> None:
    """Honest limit: HMAC with a shared key means whoever verifies can forge (ADR-051)."""
    verifier = HmacSha256PlanVerifier(KEY)
    forged = signed(plan_a(plan_version=99), verifier)
    verify_plan(forged, verifier)


# --- test 27 -----------------------------------------------------------------------------


def test_verify_plan_rejects_registry_version_mismatch() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    good = signed(plan_a(registry_version="0.2.0"), verifier)
    verify_plan(good, verifier, registry_version="0.2.0")
    for other in ("0.2.1", "0.1.0", "1.2.0", "0.2", "0.2.0 ", ""):
        with pytest.raises(
            PlanIntegrityError, match="registry_version|registry version"
        ):
            verify_plan(good, verifier, registry_version=other)
    unsigned = plan_a(registry_version="0.2.0")
    with pytest.raises(PlanIntegrityError):
        verify_plan(unsigned, None, registry_version="0.3.0")
    verify_plan(unsigned, None, registry_version="0.2.0")


def test_the_registry_version_is_compared_even_when_the_signature_is_fine() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    good = signed(plan_a(), verifier)
    with pytest.raises(PlanIntegrityError):
        verify_plan(good, verifier, registry_version="9.9.9")
    verify_plan(good, verifier)  # no version given: not checked


@pytest.mark.parametrize("bad", [5, 5.0, b"0.0.0", ["0.0.0"], True, object()])
def test_a_registry_version_of_the_wrong_type_raises_plan_integrity_error(
    bad: Any,
) -> None:
    with pytest.raises(PlanIntegrityError):
        verify_plan(plan_a(), None, registry_version=bad)


# --- test 28 -----------------------------------------------------------------------------


def test_unsigned_plan_allowed_unless_required() -> None:
    unsigned = plan_a()
    verify_plan(unsigned, None)
    verify_plan(unsigned, None, require_signature=False)
    verify_plan(
        unsigned, HmacSha256PlanVerifier(KEY)
    )  # a verifier does not make a signature mandatory
    with pytest.raises(PlanIntegrityError, match="unsigned|signature"):
        verify_plan(unsigned, None, require_signature=True)
    with pytest.raises(PlanIntegrityError):
        verify_plan(unsigned, HmacSha256PlanVerifier(KEY), require_signature=True)


def test_a_signed_plan_with_no_verifier_is_never_silently_accepted() -> None:
    good = signed(plan_a())
    with pytest.raises(PlanIntegrityError, match="verifier"):
        verify_plan(good, None)
    with pytest.raises(PlanIntegrityError, match="verifier"):
        verify_plan(good, None, require_signature=False)
    with pytest.raises(PlanIntegrityError, match="verifier"):
        verify_plan(good, None, require_signature=True)


def test_verify_plan_accepts_a_signed_plan_with_the_right_verifier() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    assert (
        verify_plan(signed(plan_a(), verifier), verifier, require_signature=True)
        is None
    )
    assert (
        verify_plan(signed(plan_b(), verifier), verifier, registry_version="0.0.0")
        is None
    )


@pytest.mark.parametrize("flag", [None, 1, 0, "yes", [], "False"])
def test_require_signature_must_be_a_bool(flag: Any) -> None:
    with pytest.raises(PlanIntegrityError, match="require_signature"):
        verify_plan(plan_a(), None, require_signature=flag)


# --- signature format --------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.upper(),
        lambda s: s[:-1],
        lambda s: s + "0",
        lambda s: s[:-1] + "g",
        lambda s: " " + s,
        lambda s: s + "\n",
        lambda s: "0x" + s[2:],
        lambda s: "",
        lambda s: s[:32],
        lambda s: s.replace(s[0], "é", 1),
        lambda s: s[:-1] + "\udc80",
    ],
    ids=[
        "uppercase",
        "short",
        "long",
        "non-hex",
        "leading space",
        "trailing newline",
        "0x prefix",
        "empty",
        "half",
        "non-ascii",
        "surrogate",
    ],
)
def test_malformed_signature_strings_fail_verification_without_raising_type_errors(
    mutate: Callable[[str], str],
) -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    bad = mutate(digest)
    assert bad != digest
    assert verifier.verify(payload, bad) is False
    with pytest.raises(PlanIntegrityError):
        verify_plan(dataclasses.replace(plan_a(), signature=bad), verifier)


@pytest.mark.parametrize(
    "bad", [b"ab" * 32, bytearray(b"ab" * 32), 5, 5.5, ["ab"], {"a": 1}, True, object()]
)
def test_a_signature_of_the_wrong_type(bad: Any) -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    assert verifier.verify(GOLDEN["plan_a"][0], bad) is False
    with pytest.raises(PlanIntegrityError, match="signature"):
        verify_plan(dataclasses.replace(plan_a(), signature=bad), verifier)


def test_a_signature_in_bytes_form_is_not_converted() -> None:
    """bytes versus str: the hex digest is text; the bytes of the same digest do not verify."""
    verifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    assert verifier.verify(payload, digest.encode("ascii")) is False  # type: ignore[arg-type]


def test_an_uppercase_signature_is_not_accepted() -> None:
    """Decision: one canonical text form (lowercase), so a signature has no malleable twin."""
    verifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    assert digest != digest.upper()
    assert verifier.verify(payload, digest.upper()) is False


@pytest.mark.parametrize("payload", ["text", 5, 1.5, None, ["x"], object()])
def test_a_payload_that_is_not_bytes_raises_plan_integrity_error(payload: Any) -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    with pytest.raises(PlanIntegrityError, match="payload"):
        verifier.verify(payload, GOLDEN["plan_a"][1])


def test_verify_accepts_bytes_like_payloads() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    assert verifier.verify(bytearray(payload), digest) is True
    assert verifier.verify(b"", digest) is False
    assert verifier.verify(payload + b" ", digest) is False


def test_the_comparison_is_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, Any]] = []
    real = hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(integrity_module.hmac, "compare_digest", spy)
    verifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    assert verifier.verify(payload, digest) is True
    assert verifier.verify(payload, "0" * 64) is False
    assert len(calls) == 2
    for a, b in calls:
        assert type(a) is type(b) and len(a) == len(b) == 64


# --- keys --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        b"",
        bytearray(),
        "a string key",
        "",
        None,
        5,
        ["k"],
        object(),
        memoryview(b""),
        memoryview(b"key"),
    ],
    ids=lambda k: type(k).__name__ + ("0" if not k else ""),
)
def test_unusable_keys_are_refused_at_construction(key: Any) -> None:
    with pytest.raises(PlanIntegrityError, match="key"):
        HmacSha256PlanVerifier(key)


def test_keys_of_any_non_zero_length_work() -> None:
    plan = plan_a()
    for key in (
        b"k",
        b"k" * 31,
        b"k" * 32,
        b"k" * 33,
        b"k" * 64,
        b"k" * 65,
        b"\x00",
        bytes(range(256)) * 4,
    ):
        digest = HmacSha256PlanVerifier(key).sign(plan)
        assert (
            digest
            == hmac.new(key, canonical_plan_bytes(plan), hashlib.sha256).hexdigest()
        )
        assert HmacSha256PlanVerifier(key).verify(canonical_plan_bytes(plan), digest)


def test_a_bytearray_key_is_copied() -> None:
    key = bytearray(KEY)
    verifier = HmacSha256PlanVerifier(key)
    key[0] ^= 0xFF
    assert verifier.sign(plan_a()) == GOLDEN["plan_a"][1]


def test_the_key_is_not_in_the_repr_or_attributes_exposed_by_str() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    assert KEY.decode() not in repr(verifier)
    assert KEY.decode() not in str(verifier)


# --- the protocol ------------------------------------------------------------------------


def test_hmac_verifier_satisfies_the_plan_verifier_protocol() -> None:
    verifier: PlanVerifier = HmacSha256PlanVerifier(KEY)
    payload, digest = GOLDEN["plan_a"]
    assert verifier.verify(payload, digest) is True


def test_any_object_with_verify_can_be_a_verifier() -> None:
    class AlwaysYes:
        def verify(self, payload: bytes, signature: str) -> bool:
            return True

    verify_plan(plan_a(signature="anything"), AlwaysYes())


@pytest.mark.parametrize(
    "result", [None, 1, "yes", [], NotImplemented, 0, False], ids=lambda r: repr(r)
)
def test_only_a_true_bool_from_the_verifier_counts(result: Any) -> None:
    class Verifier:
        def verify(self, payload: bytes, signature: str) -> Any:
            return result

    with pytest.raises(PlanIntegrityError):
        verify_plan(plan_a(signature="anything"), Verifier())


def test_a_verifier_that_raises_is_reported_as_plan_integrity_error() -> None:
    class Exploding:
        def verify(self, payload: bytes, signature: str) -> bool:
            raise RuntimeError("boom")

    with pytest.raises(PlanIntegrityError, match="verifier"):
        verify_plan(plan_a(signature="anything"), Exploding())


@pytest.mark.parametrize(
    "bad", [5, "verifier", b"v", object(), True, [HmacSha256PlanVerifier(KEY)]]
)
def test_a_verifier_without_verify_is_refused(bad: Any) -> None:
    with pytest.raises(PlanIntegrityError, match="no verify method"):
        verify_plan(plan_a(signature="anything"), bad)


@pytest.mark.parametrize("bad", [5, 5.5, b"ab" * 32, ["ab"], True, object()])
def test_a_non_text_signature_never_reaches_a_permissive_verifier(bad: Any) -> None:
    class AlwaysYes:
        def verify(self, payload: bytes, signature: str) -> bool:
            return True

    with pytest.raises(PlanIntegrityError, match="must be a str"):
        verify_plan(plan_a(signature=bad), AlwaysYes())


# --- robust plan inputs ------------------------------------------------------------------

BAD_PLANS: list[tuple[str, Any]] = [
    ("None", None),
    ("a dict", {"care_plan_id": "x"}),
    ("a str", "plan"),
    ("a tuple", ("x",)),
    ("care_plan_id None", plan_a(care_plan_id=None)),
    ("care_plan_id int", plan_a(care_plan_id=5)),
    ("care_plan_id bytes", plan_a(care_plan_id=b"x")),
    ("care_plan_id surrogate", plan_a(care_plan_id="a\ud800b")),
    ("pathway_template_id None", plan_a(pathway_template_id=None)),
    ("patient_id list", plan_a(patient_id=["p"])),
    ("registry_version float", plan_a(registry_version=0.2)),
    ("plan_version float", plan_a(plan_version=3.0)),
    ("plan_version bool", plan_a(plan_version=True)),
    ("plan_version None", plan_a(plan_version=None)),
    ("plan_version str", plan_a(plan_version="3")),
    ("plan_version huge", plan_a(plan_version=10**5000)),
    ("plan_version beyond int64", plan_a(plan_version=2**63)),
    ("plan_version below int64", plan_a(plan_version=-(2**63) - 1)),
    ("schedule item beyond int64", plan_a(schedule=(2**63,))),
    (
        "anchor beyond int64",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {}, 2**63),)),
    ),
    ("schedule not a sequence", plan_a(schedule=5)),
    ("schedule a string", plan_a(schedule="123")),
    ("schedule bytes", plan_a(schedule=b"123")),
    ("schedule None", plan_a(schedule=None)),
    ("schedule a generator", plan_a(schedule=(i for i in range(3)))),
    ("schedule a set", plan_a(schedule={1, 2})),
    ("schedule float item", plan_a(schedule=(1.5,))),
    ("schedule integral float item", plan_a(schedule=(1.0,))),
    ("schedule bool item", plan_a(schedule=(True,))),
    ("schedule None item", plan_a(schedule=(None,))),
    ("schedule str item", plan_a(schedule=("1",))),
    ("instances not a sequence", plan_a(instances=5)),
    ("instances a string", plan_a(instances="x")),
    ("instances None", plan_a(instances=None)),
    ("instances a dict", plan_a(instances={})),
    ("instance is a dict", plan_a(instances=({"template": "range"},))),
    ("instance is None", plan_a(instances=(None,))),
    ("instance template None", plan_a(instances=(TemplateInstance(None, "k", {}, 1),))),  # type: ignore[arg-type]
    ("instance template int", plan_a(instances=(TemplateInstance(5, "k", {}, 1),))),  # type: ignore[arg-type]
    (
        "instance key None",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, None, {}, 1),)),
    ),  # type: ignore[arg-type]
    (
        "instance key bytes",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, b"k", {}, 1),)),
    ),  # type: ignore[arg-type]
    (
        "param_values None",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", None, 1),)),
    ),  # type: ignore[arg-type]
    (
        "param_values a list",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", [("a", 1.0)], 1),)),
    ),  # type: ignore[arg-type]
    (
        "param_values int key",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {1: 1.0}, 1),)),
    ),  # type: ignore[dict-item]
    (
        "param_values None key",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {None: 1.0}, 1),)),
    ),  # type: ignore[dict-item]
    (
        "param_values nan",
        plan_a(
            instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": math.nan}, 1),)
        ),
    ),
    (
        "param_values inf",
        plan_a(
            instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": math.inf}, 1),)
        ),
    ),
    (
        "param_values -inf",
        plan_a(
            instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": -math.inf}, 1),)
        ),
    ),
    (
        "param_values str",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": "1"}, 1),)),
    ),  # type: ignore[dict-item]
    (
        "param_values bool",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": True}, 1),)),
    ),
    (
        "param_values None value",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": None}, 1),)),
    ),  # type: ignore[dict-item]
    (
        "param_values huge int",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {"a": 10**400}, 1),)),
    ),
    (
        "anchor float",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {}, 1.5),)),
    ),  # type: ignore[arg-type]
    (
        "anchor bool",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {}, True),)),
    ),  # type: ignore[arg-type]
    (
        "anchor str",
        plan_a(instances=(TemplateInstance(TemplateId.RANGE, "k", {}, "1"),)),
    ),  # type: ignore[arg-type]
]


@pytest.mark.parametrize(("label", "bad"), BAD_PLANS, ids=[b[0] for b in BAD_PLANS])
def test_a_malformed_plan_raises_plan_integrity_error_never_a_raw_error(
    label: str, bad: Any
) -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    with pytest.raises(PlanIntegrityError):
        canonical_plan_bytes(bad)
    with pytest.raises(PlanIntegrityError):
        verifier.sign(bad)
    # a signed plan is serialised before it is checked; an unsigned plan has nothing to verify
    marked = (
        dataclasses.replace(bad, signature="0" * 64)
        if isinstance(bad, CarePlan)
        else bad
    )
    with pytest.raises(PlanIntegrityError):
        verify_plan(marked, verifier)


def test_a_generator_schedule_is_not_consumed_silently() -> None:
    """A one-shot iterable cannot be signed and verified twice: it is refused, not drained."""
    schedule = (i for i in range(3))
    with pytest.raises(PlanIntegrityError, match="schedule"):
        canonical_plan_bytes(plan_a(schedule=schedule))
    assert list(schedule) == [0, 1, 2]


def test_the_largest_valid_numbers_are_signed_exactly() -> None:
    """Integers are signed 64-bit (the back-end may not be Python); floats are any finite double."""
    top, bottom = 2**63 - 1, -(2**63)
    plan = plan_a(
        plan_version=top,
        schedule=(bottom, 0, top),
        instances=(
            TemplateInstance(
                TemplateId.RANGE,
                "k",
                {"a": 1.7976931348623157e308, "b": -1e-300, "c": 5e-324},
                top,
            ),
        ),
    )
    data = canonical_plan_bytes(plan)
    parsed = json.loads(data)
    assert parsed["plan_version"] == top and parsed["schedule"] == [bottom, 0, top]
    assert parsed["instances"][0]["param_values"] == {
        "a": 1.7976931348623157e308,
        "b": -1e-300,
        "c": 5e-324,
    }
    verifier = HmacSha256PlanVerifier(KEY)
    verify_plan(signed(plan, verifier), verifier)


def test_a_large_plan_is_signed_in_bounded_time() -> None:
    instances = tuple(
        TemplateInstance(TemplateId.RANGE, f"range@{i}", {"a": float(i), "b": 2.0}, i)
        for i in range(2000)
    )
    plan = plan_a(instances=instances, schedule=tuple(range(5000)))
    verifier = HmacSha256PlanVerifier(KEY)
    verify_plan(signed(plan, verifier), verifier)


def test_a_signature_can_be_verified_against_a_payload_built_elsewhere() -> None:
    """The backend and the monitor agree on the bytes: any producer of the golden bytes verifies."""
    verifier = HmacSha256PlanVerifier(KEY)
    plan = signed(plan_a(), verifier)
    assert plan.signature == GOLDEN["plan_a"][1]
    assert verifier.verify(GOLDEN["plan_a"][0], plan.signature) is True  # type: ignore[arg-type]


def test_canonical_bytes_are_deterministic_across_calls_and_copies() -> None:
    sequences: Sequence[bytes] = [canonical_plan_bytes(plan_a()) for _ in range(5)]
    assert len(set(sequences)) == 1
