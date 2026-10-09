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

## Decisioni del 2026-10-08 (sessione interattiva con gab)

- Documenti umani trascritti dalle risposte di gab e da ricerche documentate con fonti: `WS00-admin/outputs/WS00-T01.md` (CFP: nessun CFP pubblico, special issue in fase di proposta; RA-L 6 pagine riferimenti inclusi, double-anonymous), `WS00-T02.md` (ADR-001..003, 012..015, 017 confermate), `WS00-T05.md` (TIAGo, TIAGo Pro e Unitree R1 disponibili; robot su Humble), `WS00-T06.md` (nessun comitato etico: nessun partecipante umano), `WS00-T08.md` (preprint di Lindemann et al. 2023 in `data/raw/papers/`), `WS00-T09.md` (quattro dataset aperti, manifest `SHA256SUMS` verificati). Il `.gitignore` ignorava ogni cartella `outputs/`: ora solo `/outputs/` alla radice.
- ADR-042 (accettata): ROS 2 Humble con Gazebo Classic, Python 3.10 come minimo di `ralmon`; sostituisce ADR-011 e ADR-016. ADR-043 (accettata): il freeze M1 non attende più la revisione clinica (WS00-T07 diventa pre-submission), valori dei parametri proposti dalla letteratura nel nuovo task WS01-T09 e controllati da gab. ADR-028 e ADR-029 accettate. ADR-027 in attesa di una valutazione richiesta da gab.
- WS00-T04 torna `ready` (accreditamento PhysioNet non avviato, decisione rinviata) e WS04-T13 torna `blocked`. WS01-T08 (freeze M1) diventa `ready`.

## M1 formalization freeze (WS01-T08, 2026-10-08)

- M1 documents frozen (`docs/formal/README.md`: `FROZEN: yes`, `clinician_review: pending`, ADR-043); the M1 gate of `00-master-plan.md` (contract amendments decided by ADR, `02-interfaces.md` versions agreed) closes when the proposed contract-amending ADRs (ADR-045 to ADR-050 and those listed in `docs/formal/08-consistency-review.md` section 4.2) are decided by gab; open points OPF-1 to OPF-17 in `docs/formal/08-consistency-review.md` section 5.4.

## Paper posticipato in fondo (ADR-056, 2026-10-09)

- Per istruzione di gab, tutta la stesura del paper (WS12) viene per ultima: WS12-T01 e WS12-T02 passano da `ready` a `blocked`, con le nuove dipendenze WS08-T07, WS09-T05 e WS07-T07; T03..T08 seguono per transitività. La demo di laboratorio (WS10-T06) non è nel gate perché tagliabile.
- M0 si chiude con WS00-T01 e WS00-T02; il testo della lettera di impegno si scrive quando gli organizzatori lo chiedono (nessuna data nota, `WS00-T01.md`): per anticiparlo bastano togliere le tre dipendenze di WS12-T01.
