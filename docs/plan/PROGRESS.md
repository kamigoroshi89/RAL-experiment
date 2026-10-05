# PROGRESS

Stato del bootstrap del piano. Una fase alla volta, commit dopo ciascuna (`plan(Fx): <sintesi>`).

- [x] **F0 Setup** — git init, .gitignore, PROGRESS.md; fonti copiate (non spostate) in docs/source/ (analisi.md = copia integrale; review.md = estratto verbatim di analisi §2, vedi ADR-012). Originali lasciati in radice.
- [x] **F1 Spec** — spec di design (opzione A, motivazione vs B/C, riferimenti alle fonti)
- [x] **F2 00-master-plan.md** — master plan: obiettivo, milestone M0-M5, percorso critico, stime da §9, cosa non tagliare, ordine di attacco
- [x] **F3 01-conventions.md** — conventions: layout repo/pacchetti, stile Python, TDD, git per task, glossario §8.1 vincolante
- [x] **F4 02-interfaces.md** — interfaces: 17 contratti versionati con firme Python (trace, PriorSource, template, verdict, alert, evidence, monitor, conformal, detector, metrics, ROS2, API pubblica)
- [x] **F5 03-decisions.md** — decisions: ADR-001..020 (6 richiesti + scelte autonome marcate [DA-CONFERMARE]: 011,012,013,014,015,016,017)
- [x] **F6 Workstream (in parallelo)** — 14 workstream (README + 103 task) scritti da 14 subagent in parallelo; riconciliati: dipendenze mancanti (ADR-023), 3 task umani aggiunti (WS00-T08..T10), gap dei contratti registrati (ADR-021), layout (ADR-022); check_plan OK
- [x] **F7 04-review-traceability.md** — tracciabilità: 31 rilievi (26 debolezze R1-R3 + AE-1..5) mappati a task, più 4 obiezioni residue di §10; nota: il file era già incluso nel commit F6; verificato da check_plan
- [x] **F8 CLAUDE.md** — CLAUDE.md (radice, 81 righe): scopo, mappa documenti, glossario, scelta del task, regole; verificato <200 righe; incluso nel commit F7
- [x] **F9 Verifica finale** — tools/check_plan.py scritto ed eseguito: OK su 103 task, 18 contratti, 31 rilievi; verificato con 9 mutazioni che i controlli falliscono quando devono

## Note

- Correzioni alle note sopra: F4 contiene 18 contratti (non 17); il log ADR arriva a ADR-023 (021-023 aggiunti in F6). I file 04-review-traceability.md, CLAUDE.md e tools/check_plan.py sono stati creati durante F6 e committati con i commit F6/F7.
- Discrepanze prompt/fonti registrate in `03-decisions.md`: ADR-012 (docs/source/review.md è un estratto di analisi §2), ADR-014 (collocazione dei punti §9 0.4/0.5 in WS12), ADR-015 (run-plan.sh fa cd in prompt/).
- Scelte autonome in attesa di conferma umana (tag [DA-CONFERMARE]): ADR-011, 012, 013, 014, 015, 016, 017, 021, 022, 023.
- Prossimo passo operativo: task `ready` con owner agent e percorso critico: WS05-T01 (scaffolding); task umani subito eseguibili: WS00-T01, T04, T05, T08, T09.

## Scope change 2026-10-05 (ADR-037)

- Per esplicita istruzione dell'utente, l'agente non scrive nulla del paper: WS12-T01..T08 passano a `owner: human` (file task e INDEX), `CLAUDE.md` ha la regola corrispondente. WS09 (figure e tabelle) resta da decidere quando WS08 produce risultati.
- Stato al cambio: 23 task su 103 completati (WS00 6, WS01 6, WS02 3, WS03 5, WS04 1, WS05 2); task umani aperti: WS00-T03, T06, T07, T10, WS03-T06, WS10, WS11, e (ora) WS12.
