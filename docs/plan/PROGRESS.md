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
- [ ] **F8 CLAUDE.md**
- [ ] **F9 Verifica finale**

## Note
