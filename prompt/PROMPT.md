# Missione

Sei l'agente di bootstrap del progetto **RAL experiment**. Lavori in modalità headless: nessun umano risponderà alle tue domande.

Obiettivo **unico** di questa esecuzione: produrre la documentazione di piano, il `CLAUDE.md` alla radice e un repository git inizializzato. **Non scrivere codice in `src/`**: lo scaffolding del codice è il task `WS05-T01`, riservato agli agenti esecutori successivi.

Non fare domande. Se manca un'informazione, scegli l'opzione più conservativa, registrala come ADR con stato `proposed` e tag `[DA-CONFERMARE]` in `docs/plan/03-decisions.md`, e prosegui.

---

# Fonti di verità (leggile per prime, ogni iterazione)

- `docs/source/analisi.md`: analisi del progetto (roadmap §9, terminologia §8.1, metriche §5, ecc.)
- `docs/source/review.md`: rilievi dei reviewer

Se una delle due manca: scrivi `docs/plan/BLOCKED.md` spiegando cosa manca, fai commit ed esci.

Precedenza: **fonti > questo prompt > tue inferenze**. Non inventare parametri PK/PD, numeri, sezioni, rilievi o workstream. Se questo prompt e la roadmap §9 divergono (nomi o numero dei workstream), vince §9 e registri la discrepanza in `03-decisions.md`.

---

# Protocollo di ogni iterazione (lo stato vive su disco, non nel contesto)

1. Se non esiste `.git`: `git init`, crea `.gitignore` (Python, `.venv/`, `data/raw/`, `outputs/`, `.claude/logs/`), primo commit.
2. Leggi `docs/plan/PROGRESS.md`. Se non esiste, crealo con la checklist delle fasi F0–F9 qui sotto.
3. Prendi la **prima fase non spuntata**, eseguila, verificala, spuntala in `PROGRESS.md` con una riga di note, poi commit: `plan(Fx): <sintesi>`.
4. Passa alla fase successiva. Committa dopo **ogni** fase: se il contesto si esaurisce, l'iterazione successiva riparte dal disco.
5. Quando tutte le fasi sono spuntate **e** la verifica F9 passa: crea `docs/plan/.PLAN_COMPLETE`, commit, termina.

Git: solo operazioni locali (`init`, `add`, `commit`, `status`, `diff`, `log`). Mai `push`, mai `remote`, nessun accesso di rete.

---

# Skill (plugin superpowers)

- Il design è **già approvato** (sezione seguente): non rieseguire `superpowers:brainstorming`.
- `superpowers:writing-plans`: usane lo standard per i task (passi piccoli, file esatti, test, criterio di done), adattato al layout multi-file descritto sotto invece di un file unico.
- `superpowers:dispatching-parallel-agents` (o `subagent-driven-development`) in F6: un subagent per workstream, **solo dopo** che F3 e F4 sono committate, passando a ciascuno il percorso di `01-conventions.md`, `02-interfaces.md`, il template dei task e le sezioni rilevanti delle fonti.
- `superpowers:verification-before-completion`: prima di spuntare ogni fase e prima del sentinel. Mostra l'output dei controlli, non affermare che passano.
- `superpowers:test-driven-development`: non si esegue ora, ma ogni task di codice va scritto perché l'agente esecutore la applichi (sezione "Test" compilata prima dei "Passi").

---

# Design approvato (opzione A: workstream con contratti di interfaccia condivisi)

Motivazione: la roadmap §9 prevede lavoro parallelo (fasi 4, 5 e 7). Le alternative scartate sono B (piano per sezioni del paper: mescola codice e scrittura, task difficili da assegnare) e C (file unico: troppo grande per il contesto di un agente con ~13 workstream e ~40 pw).

```
RAL experiment/
├── CLAUDE.md
├── tools/check_plan.py                 # verificatore del piano (F9), unico codice ammesso
├── docs/
│   ├── source/                         # fonti di verità (sola lettura)
│   ├── superpowers/specs/2026-09-29-ral-dev-plan-design.md
│   └── plan/
│       ├── PROGRESS.md
│       ├── 00-master-plan.md
│       ├── 01-conventions.md
│       ├── 02-interfaces.md
│       ├── 03-decisions.md
│       ├── 04-review-traceability.md
│       └── workstreams/WSxx-<slug>/README.md + tasks/Txx-<slug>.md
```

Workstream attesi (verifica e completa contro §9): WS00-admin (solo task umani), WS01-formalization, WS02-threat-fault-model, WS03-related-work, WS04-benchmark, WS05-monitor, WS06-(da §9), WS07-ros2-sim, WS08-experiments, WS09-figures, WS10-lab-demo, WS11-vignettes, WS12-(da §9), WS13-release.

Pacchetti del core (`src/ralmon/`, da creare in WS05-T01, **non ora**):
- `signals`: signal abstraction e segnali derivati (es. `bp_pre`, `c_d`)
- `spec`: template STL past-time, normalizzazione σ̃, priorità
- `monitor`: robustezza e generazione degli alert
- `conformal`: split e adaptive, calcolo di ρ
- `attribution`: regole gerarchiche con esito `UNDETERMINED`
- `benchmark`: PK/PD, processo di misura, iniezione C1/C2/C3, ground truth latente
- `baselines`: B1–B5
- `eval`: metriche di §5

Dati: parametri PK/PD e del paziente passano da un'interfaccia `PriorSource`. Implementazione iniziale `LiteraturePriorSource` (valori da letteratura); `MimicPriorSource` si aggiunge quando l'accesso a MIMIC è disponibile, senza toccare il resto.

Garanzie non negoziabili:
- ogni task cita le sezioni dell'analisi da cui deriva;
- ogni rilievo dei reviewer è tracciato fino a almeno un task;
- B5, A4 e la formalizzazione sono marcati `non_negotiable: true` e non compaiono mai in liste di tagli.

---

# Fasi (checklist di PROGRESS.md)

- [ ] **F0 Setup**: git init, `.gitignore`, `PROGRESS.md`, sposta nessun file sorgente.
- [ ] **F1 Spec**: `docs/superpowers/specs/2026-09-29-ral-dev-plan-design.md`, che trascrive il design approvato, la motivazione A vs B/C e i riferimenti alle fonti.
- [ ] **F2 `00-master-plan.md`**: obiettivo, milestone, percorso critico e fasi parallelizzabili, stime in pw per workstream (solo da §9), elenco "cosa non tagliare", ordine consigliato di attacco.
- [ ] **F3 `01-conventions.md`**: layout del repo e dei pacchetti, stile Python, testing (pytest, TDD, seed fissi, fixture deterministiche), git (un branch per task, convenzione dei commit), glossario vincolante da §8.1.
- [ ] **F4 `02-interfaces.md`**: ogni contratto con versione, workstream proprietario e consumatori. Minimo: schema delle tracce; template STL past-time; `Alert⟨τ, κ, σ̃, ρ, ξ⟩` con tipo, unità e semantica di ogni campo; `EvidenceVector`; `PriorSource`; firme pubbliche dei pacchetti. Firme Python (`dataclass`/`Protocol`) come blocchi di codice **dentro il markdown**. Regola: un contratto cambia solo tramite ADR.
- [ ] **F5 `03-decisions.md`**: ADR (contesto, decisione, alternative, conseguenze, stato) almeno per: scope; C3 → integrity; architettura distribuita; DISPENSE ≠ INTAKE; `PriorSource`; layout multi-file del piano. Più ogni scelta presa in autonomia, marcata `[DA-CONFERMARE]`.
- [ ] **F6 Workstream (in parallelo)**: per ogni workstream, `README.md` (obiettivo, input, output, dipendenze da altri WS e da contratti di `02`, criteri di accettazione, sezioni fonte) e `tasks/` con task nel template sotto. WS05-T01 è lo scaffolding di `src/ralmon/` con i pacchetti elencati. Al rientro dei subagent, controlla coerenza di id, dipendenze e riferimenti ai contratti.
- [ ] **F7 `04-review-traceability.md`**: tabella `rilievo | citazione breve o parafrasi | WS/task | come viene chiuso | stato`. Nessun rilievo orfano.
- [ ] **F8 `CLAUDE.md`** (radice, < 200 righe): scopo del progetto, mappa dei documenti, glossario breve con link a `01`, **come scegliere un task** (il primo con `status: ready`, `owner: agent`, dipendenze `done`, prima quelli su percorso critico), regole di lavoro (TDD, niente modifiche ai contratti senza ADR, aggiorna `status` del task e `PROGRESS` a fine lavoro, un task per branch).
- [ ] **F9 Verifica finale**: scrivi ed esegui `tools/check_plan.py` (sola libreria standard) che controlla quanto segue, e correggi finché passa.

Controlli di F9:
1. ogni cartella workstream ha `README.md` e almeno un task;
2. ogni task ha frontmatter completo e almeno una voce in `sources`;
3. ogni `depends_on` punta a id esistenti e il grafo è aciclico;
4. ogni rilievo di `review.md` compare in `04-review-traceability.md`;
5. ogni contratto di `02` è usato da almeno un task, e ogni ancora citata in `interfaces` esiste;
6. B5, A4 e i task di WS01 hanno `non_negotiable: true`;
7. zero occorrenze di `TODO`, `TBD`, `???`, `lorem` (i `[DA-CONFERMARE]` in `03` sono ammessi);
8. nessun file in `src/`.

---

# Template dei task

```markdown
---
id: WS05-T01
title: Scaffolding del pacchetto ralmon
workstream: WS05-monitor
owner: agent            # agent | human (WS00 e le parti fisiche di WS10 sono human)
status: ready           # ready | blocked | in_progress | done
depends_on: []
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §9", "analisi §8.1"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo
## Contesto (cosa leggere prima, max 5 link)
## File toccati
## Test (da scrivere PRIMA, con nomi dei test)
## Passi
## Done when (verificabile da comando)
```

Dimensione: un task sta in circa una giornata di lavoro di un agente e tocca al massimo ~5 file. Se è più grande, spezzalo.

---

# Criterio di arresto

Hai finito solo quando `python3 tools/check_plan.py` esce con codice 0, tutte le fasi di `PROGRESS.md` sono spuntate, l'ultimo commit è pulito (`git status` vuoto) e `docs/plan/.PLAN_COMPLETE` esiste. Non creare il sentinel in nessun altro caso.
