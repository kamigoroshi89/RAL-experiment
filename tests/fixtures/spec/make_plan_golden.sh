#!/bin/sh
# Regenerates the independent golden values of the plan-integrity tests (WS05-T03, tests 24 and 25).
#
# The canonical bytes below are written by hand (shell literals, keys sorted at every level, compact
# separators, UTF-8, integers as integers, floats as decimal text with a point) and the digest is computed
# by openssl, so neither the canonical form nor the HMAC comes from the code under test.
# Run from this directory: sh make_plan_golden.sh   (requires openssl; the outputs are committed).
set -eu
cd "$(dirname "$0")"

KEY='plan-golden-key-not-a-secret'
printf '%s' "$KEY" > plan_golden.key

# Plan A: two instances, one with anchor_ms null, floats written with a point, three schedule ticks.
printf '%s' '{"care_plan_id":"cp-fixture-001","instances":[{"anchor_ms":32400000,"instance_key":"range@32400000","param_values":{"bp_band_high":140.0,"bp_band_low":110.0},"template":"range"},{"anchor_ms":null,"instance_key":"resp@25200000","param_values":{"delta1":3600000.0,"delta2":10800000.0},"template":"resp"}],"pathway_template_id":"pt-hypertension-v1","patient_id":"p-0001","plan_version":3,"registry_version":"0.0.0","schedule":[25200000,32400000,75600000]}' > plan_a.canonical.json

# Plan B: non-ASCII text (written as UTF-8, not escaped), empty sequences, plan_version 0.
printf '%s' '{"care_plan_id":"cp-fixture-002","instances":[],"pathway_template_id":"pt-ü","patient_id":"pätient","plan_version":0,"registry_version":"0.0.0","schedule":[]}' > plan_b.canonical.json

# Plan C: mixed-case text, characters outside Latin-1 (CJK) and outside the BMP (an emoji), a float with a
# fractional part, keys that sort by code point (upper case before lower case).
printf '%s' '{"care_plan_id":"CP-Fixture-003","instances":[{"anchor_ms":null,"instance_key":"Range@Ünï","param_values":{"BP_Band_Low":110.5,"bp_Band_high":140.25},"template":"range"}],"pathway_template_id":"Pt-患者","patient_id":"Pätient-😀","plan_version":1,"registry_version":"0.0.0","schedule":[0]}' > plan_c.canonical.json

for plan in plan_a plan_b plan_c; do
    openssl dgst -sha256 -hmac "$KEY" -r "$plan.canonical.json" | cut -d' ' -f1 > "$plan.hmac_sha256"
done
