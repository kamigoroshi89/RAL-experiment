# Public sources of the measurement process

Document of WS04-T06. Technical mapping only: it says which open-access dataset is meant to supply which signal of the observed trace, what a human with the data runs to produce the segment files that `ralmon.benchmark.segments` reads, and what is still to be verified. Validation in this project is technical and pre-clinical. No fact about a dataset below was written from memory or read from the network: every schema, sampling-rate, unit and licence statement is `unverified` until a human confirms it from the dataset page and records the confirmation in the table of the section Verification status. Agents never download data and `data/raw/` is never committed.

## Purpose

The benchmark generator (`docs/plan/workstreams/WS04-benchmark/README.md`, analisi section 5.1 item 2) takes the heart rate and the SpO2 of the observed trace from clean real segments, and the noise of the ECG path from real electrode and motion noise, instead of simulating them. Three kinds of segment are needed by `src/ralmon/benchmark/segments.py`:

| kind | role in the benchmark | consumer |
|---|---|---|
| `hr_clean` | the heart rate of a patient-day, `hr_ecg` samples and the level behind the cuff pulse `hr_pulse` | WS04-T06 (measurement process), WS04-T09 (latent assembly) |
| `spo2_clean` | the SpO2 of a patient-day, `spo2` samples | WS04-T06, WS04-T09 |
| `hr_error_ecg_noise` | a paired error trace (heart rate from the noisy ECG minus the heart rate from the clean ECG) for the C2 fault `ecg_noise` | WS04-T07 |

Heart rate and SpO2 are not coupled to the pressure model or to the drug (declared limitation of the generator). Fault-free ECG heart rate and SpO2 equal the clean segments. Until a human completes the extraction below there is no segment file: a build then needs `allow_no_segments=True`, produces no `hr_ecg`, `spo2` or `hr_pulse` sample, and records the segment source as `none` in the manifest. The test suite never needs the data: it uses inline fixture segments.

## Sources

One row per open-access source of the table "Public data sources" of the WS04 README. The licence and the redistribution terms are recorded by a human in `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (sections `## Open-access datasets` and `## Data handling constraints`) and are not copied here; that artefact was not present in the repository when this document was written, so the licence of every row is `unverified`. The download, the version and the checksum manifest of each dataset are the artefact of WS00-T09 (`docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md`, `data/raw/<dataset>/SHA256SUMS`), also absent when this document was written.

| source | role in the benchmark (from the README table) | segment kinds intended | licence and redistribution | signal names | sampling rates | units | record layout or labels |
|---|---|---|---|---|---|---|---|
| VitalDB | high-resolution intraoperative signals: noise and artefact modelling, clean heart rate and SpO2 segments | `hr_clean`, `spo2_clean` | unverified (see WS00-T04 rows) | unverified | unverified | unverified | unverified |
| BIDMC PPG and Respiration | PPG-derived signals, heart rate reference | `hr_clean` | unverified (see WS00-T04 rows) | unverified | unverified | unverified | unverified |
| MIT-BIH Arrhythmia Database | proposal of this document: clean ECG records whose heart rate is then corrupted by the noise of the noise database | `hr_clean`, base of `hr_error_ecg_noise` | unverified (see WS00-T04 rows) | unverified | unverified | unverified | unverified |
| MIT-BIH Noise Stress Test Database | real electrode and motion noise for realistic C2 faults on the ECG path | `hr_error_ecg_noise` | unverified (see WS00-T04 rows) | unverified | unverified | unverified | unverified |
| PhysioNet/CinC Challenge 2015 | labelled false alarms: sanity check of the alert load (WS04-T12), not a segment source | none | unverified (see WS00-T04 rows) | unverified | unverified | unverified | unverified |

Which dataset supplies which kind is a proposal of the plan (the README column "Role"); the human decides, after reading the dataset pages, whether a dataset really holds a usable signal for a kind, and records the decision in the section Verification status. The credentialed sources (MIMIC-IV, MIMIC-IV-ED, eICU-CRD) are not used by this document.

## Extraction procedure

What a human with the data runs. It uses the dataset's own tooling, the reader named on the dataset page, and none of it is run by an agent. Every number below that depends on a dataset (a rate, a unit, a signal name, a record id) is read from the dataset page by the human, not taken from this document.

1. Check the downloads: in each `data/raw/<dataset>/`, run `sha256sum -c SHA256SUMS` and stop on any failure.
2. Choose the extraction rule for each kind and write it in a short plain-text note kept next to the index (not committed): the record or case ids used, the interval of each segment, the criterion by which a segment is "clean" (for example no annotated artefact, no signal-quality flag raised, no missing values), and the tool and its version.
3. `hr_clean`: with the dataset's reader, take a heart-rate signal over a clean interval (a reference heart rate where the dataset provides one, otherwise a rate computed from the clean signal by a method named in the note). Resample or aggregate to a regular period with the dataset's tooling, and keep that period as `sample_period_ms`. Remove nothing silently: a segment with a gap is cut at the gap, not interpolated.
4. `spo2_clean`: the same for the SpO2 signal of a dataset that records it, over a clean interval.
5. `hr_error_ecg_noise`: a paired trace. Take a clean ECG record and the matching noisy version (the clean record with noise from the noise database added; which tooling does this and at which mixing levels is to be confirmed by the human from the dataset page, and stays `unverified` until then); compute the heart rate of both with the same detector and period; the segment values are the noisy rate minus the clean rate (the error). If the tooling also yields a signal quality index for the noisy interval, write it as `quality` in `[0, 1]`.
6. Write each segment in the format of the next section under `data/raw/segments/<kind>/<segment_id>.json`, compute the sha256 of the file, and add its entry to `data/raw/segments/index.json` with the dataset name, the record id, the unit as printed on the dataset page, the licence name as printed on the dataset page and the sha256.
7. Verify with the library, from the repository root, and fix every error it reports:

   ```
   python - <<'EOF'
   from ralmon.benchmark.segments import SegmentIndex, SegmentLibrary
   index = SegmentIndex.from_file("data/raw/segments/index.json")
   library = SegmentLibrary("data/raw/segments", index)
   print(library.descriptor)
   EOF
   ```

8. Do not commit, copy to a hosted service or redistribute any segment: `data/raw/` is gitignored, and the terms of each dataset are recorded in the WS00-T04 artefact.

## Segment file format

Defined by `src/ralmon/benchmark/segments.py` (module docstring); this section restates it for the human who writes the files.

`index.json`: `{"schema_version": "0.1.0", "segments": [<entry>, ...]}` with at most 10 000 entries and a file size of at most 4 MiB. An entry has exactly these keys, all mandatory:

| key | meaning |
|---|---|
| `segment_id` | unique identifier of the segment, a non-empty string |
| `dataset` | name of the source dataset (provenance) |
| `record_id` | record or case identifier inside the dataset (provenance) |
| `kind` | `hr_clean`, `spo2_clean` or `hr_error_ecg_noise` |
| `sample_period_ms` | integer period between samples, in milliseconds; one value per kind |
| `n_samples` | number of samples of the file, an integer from 1 to 500 000 |
| `unit` | unit label of the values (for the record; the generator does not convert) |
| `path` | path relative to the segment root, with no `..`, no absolute form, no backslash |
| `sha256` | 64 lowercase hexadecimal digits of the segment file |
| `licence` | licence name of the source dataset (provenance) |

An entry that lacks `licence`, `dataset`, `record_id` or `sha256`, a file whose hash differs from the index, a path that leaves the segment root (also through a symbolic link), a file larger than 8 MiB, or a value that is not a finite number is refused with `SegmentIndexError`.

Segment file: `{"values": [numbers], "quality": [numbers in [0, 1]]}`. `quality` is optional and has the length of `values`; `values` has `n_samples` entries; `NaN` and `Infinity` are not valid JSON numbers here.

The generator picks, for each patient-day and kind, one segment long enough to cover the day (at a drawn offset), or joins whole segments and counts the joins; a join is a discontinuity that the validation report discloses (`join_count` in the manifest settings). The segment ids used are recorded per day.

## Verification status

Every row is `unverified` until a human fills the last two columns from the dataset page. Nothing in the sections above is a verified fact.

Marker convention, for the human who verifies. Confirm a fact from the dataset page, then (1) fill `verified_by` and `verified_on` of its row below and change its `status` to `verified`; (2) in the table of the section Sources, replace the word `unverified` in each fact cell that the confirmation covers by the confirmed fact followed by the marker `(verified_by: <name>)`. A fact cell of the Sources table holds either `unverified` (it may continue with a pointer such as `see WS00-T04 rows`) or a fact carrying the marker `verified_by:`; any other content is an error that the structural test of the repository (`tests/benchmark/test_measurement.py`) refuses. The test counts no `unverified`: the number of `unverified` marks of this document is only checked by the grep of the task's Done-when, at the time the task is closed.

| item | status | verified_by | verified_on |
|---|---|---|---|
| VitalDB: licence and redistribution terms | unverified | | |
| VitalDB: names, sampling rates and units of the heart-rate and SpO2 signals | unverified | | |
| BIDMC PPG and Respiration: licence and redistribution terms | unverified | | |
| BIDMC PPG and Respiration: content, heart-rate reference, sampling rate and unit | unverified | | |
| MIT-BIH Arrhythmia Database: licence and redistribution terms | unverified | | |
| MIT-BIH Arrhythmia Database: record layout, sampling rate and annotation definitions | unverified | | |
| MIT-BIH Noise Stress Test Database: licence and redistribution terms | unverified | | |
| MIT-BIH Noise Stress Test Database: noise records, signal-to-noise ratios and record layout | unverified | | |
| PhysioNet/CinC Challenge 2015: licence, label definitions and record layout | unverified | | |
| Mapping of each dataset to the segment kinds of this document | unverified | | |
| Segment extraction rule of the human (clean criterion, tools, versions) | unverified | | |
