# Benchmark trace fixtures (WS04-T01)

Golden files for `tests/benchmark/test_trace_io.py`. Every number is arithmetic and fixture-only: none is a clinical value, none is a parameter of any prior.

| File | Content |
|---|---|
| `observed_day_minimal.json` | `ObservedDay` of patient `p001`, day 0: 12 samples, 6 events (`days/p001/0.json` in a benchmark directory) |
| `truth_minimal.json` | latent day, two ground-truth events and both sidecars (`truth/p001/0.json`) |
| `manifest_minimal.json` | manifest listing the two files above with their sha256 (`manifest.json`) |

The files use the canonical form of `ralmon.benchmark.trace`: keys sorted, two-space indent, final newline, floats as `repr`, no timestamp or host field.

## Regeneration

Golden files change only through this command, run from the repository root, and the diff must be reviewed:

```
python -c "from tests.benchmark.test_trace_io import regenerate_fixtures; regenerate_fixtures()"
```

The objects are built in code by `fixture_day`, `fixture_latent`, `fixture_ground_truth` and `fixture_manifest` in the test module. The first version of these files was derived from the canonical rules by an independent throwaway script, not by the writer, so the golden test is not circular.
