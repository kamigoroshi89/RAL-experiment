---
id: WS00-T01
title: "Verify CFP: deadlines, page limit, prior-publication policy, commitment letter content"
workstream: WS00-admin
owner: human
status: done
depends_on: []
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §9 (0.1)", "analisi §7", "analisi §8.3", "analisi §8.4"]
interfaces: []
review_items: []
---
## Obiettivo

Read the call for papers (CFP) of the IEEE RA-L special issue and record, in one artefact, every rule that constrains the paper and the commitment letter: deadlines, page limit and whether references count, the policy on prior publication of a workshop paper (including whether the IJCAI-ECAI workshop proceedings are archival), the required content of the commitment letter, and whether authors and title can change later. The task is on the critical path (WS00-T02 and WS12-T02 depend on it) and prevents a desk reject (analisi §9 item 0.1). Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` with the nine fields listed in Done when.

## Contesto

- `docs/source/analisi.md` §9, row 0.1 (what to verify) and §7 (the six-page plan assumes the worst case, references included; this is a planning assumption, not a CFP fact).
- `docs/source/analisi.md` §8.3 and §8.4 (title options and the commitment-letter variant of the abstract, which shows what the letter is expected to contain).
- `docs/plan/00-master-plan.md` sections 3 (milestone M0), 6 (day-one order) and 7 (cut order if the schedule is too short).
- The workshop paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" (`Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` in the repository root), needed to answer the prior-publication questions.
- The current CFP of the RA-L special issue and the page of the workshop "Safe Robotics in the Era of Physical AI" at IJCAI-ECAI 2026. The human locates both and records their addresses in the artefact.

No dependency: this task is `ready` and starts on day one.

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (create)

## Test

Verification checks, run by a reviewer or by an agent reading the artefact:

1. The file exists and its first two lines are `completed_by: <name>` and `completed_on: <YYYY-MM-DD>`.
2. Exactly nine H2 headings named as in Done when are present and none has an empty body.
3. Every field has a `Source:` line (CFP section and address, or a message from the guest editors with its date), or the text `not stated in CFP` together with the date the question was sent and the answer status.
4. `## Deadlines` gives, for the commitment letter and for the full submission, a calendar date, a time and a time zone. It also states the number of weeks between `completed_on` and the full-submission deadline and compares it with the 14 to 16 weeks assumed in analisi §9.
5. `## Page limit` states the number of pages, an explicit yes or no on whether references count, and the policy on extra pages.
6. `## Prior publication policy` and `## Workshop proceedings archival status` are separate. The first answers what the CFP says about a paper previously presented at a workshop and what disclosure or difference statement it requires. The second states whether the IJCAI-ECAI workshop proceedings are archival, on what evidence, and how the workshop paper was actually published.
7. `## Commitment letter content` lists every item the CFP requires, in the CFP's own wording, including any length limit on the abstract.
8. `## Author and title changes` gives yes or no for authors, yes or no for title, and the last date each change is allowed.
9. No value is copied from analisi: "six pages" and "references included" appear only as the planning assumption they are, next to the value the CFP gives.

## Passi

1. Locate the RA-L special-issue CFP and the workshop page; write both addresses and the consultation date in `## Source`.
2. Read the CFP and fill `## Deadlines`, `## Page limit`, `## Commitment letter content` and `## Author and title changes` with the CFP's own wording. Where the CFP is silent, write `not stated in CFP`, send the question to the guest editors or editorial office, and record the date sent.
3. Fill `## Prior publication policy`: quote the CFP's rule on prior workshop publication, and record whether a statement of differences from the workshop paper is required. The introduction sentence on this point is planned in analisi §7 (row I) and is written in WS12-T03.
4. Fill `## Workshop proceedings archival status` from the workshop and IJCAI-ECAI pages: archival or not, how the paper was published, and the evidence (page or message). If it cannot be established, record the question sent and treat the workshop paper as archival for planning.
5. Fill `## Review mode and format`: single or double blind, anonymisation rules (the release snapshot in WS13-T03 and the check in WS12-T08 depend on it), paper template, whether supplementary material or a video is allowed (relevant to the fallback in WS10-T06), any rule on code or data release.
6. Fill `## Impact on plan`: compute the weeks available against the 14 to 16 weeks of analisi §9; list which of `00-master-plan.md` section 7 cuts would be needed if the gap is negative (the decision itself belongs to WS00-T02); list the downstream tasks affected: WS12-T02 (page budget), WS12-T03 (difference from the workshop paper), WS12-T01 (commitment-letter content), WS00-T03 (whether an author can be added), WS12-T08 and WS13-T03 (anonymisation).
7. Ask a co-author to read the artefact, then set `status: done` in this task file and tell the owner of WS00-T02 that it is unblocked.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` exits 0.
- `grep -cE '^## (Source|Deadlines|Page limit|Prior publication policy|Workshop proceedings archival status|Commitment letter content|Author and title changes|Review mode and format|Impact on plan)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` prints `9`.
- `grep -c '^completed_by: .\+' docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` prints `1`, and the same for `completed_on`.
- Inspection: no field body is empty, and every field satisfies check 3 above.

## Notes

### Status update (user attestation)

Marked `done` on 2026-09-30 at the user's explicit instruction ("le task umane iniziali sono tutte eseguite"). The artefact named in "Done when" (`docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md`) was not present in the repository at that time; the agent did not create or reconstruct it. Anything downstream that needs its content will stop and report.
