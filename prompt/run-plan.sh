#!/usr/bin/env bash
# Esegue Claude Code in loop finché il piano non è completo.
# Ogni iterazione parte con contesto pulito e riprende da docs/plan/PROGRESS.md.
set -uo pipefail
cd "$(dirname "$0")"

MAX_ITER=${MAX_ITER:-25}           # tetto di sicurezza
STALL_LIMIT=${STALL_LIMIT:-3}      # iterazioni consecutive senza nuovi commit
SLEEP_ON_ERROR=${SLEEP_ON_ERROR:-900}  # attesa (s) su errore/limite d'uso
LOG_DIR=.claude/logs
mkdir -p "$LOG_DIR"

commits() { git rev-list --count HEAD 2>/dev/null || echo 0; }
stall=0

for i in $(seq 1 "$MAX_ITER"); do
  [[ -f docs/plan/.PLAN_COMPLETE ]] && { echo "✅ Piano completato."; exit 0; }
  [[ -f docs/plan/BLOCKED.md ]]     && { echo "⛔ Bloccato: leggi docs/plan/BLOCKED.md"; exit 2; }

  before=$(commits)
  echo "== Iterazione $i — $(date -Is) =="
  claude -p "$(cat PROMPT.md)" \
    --output-format stream-json --verbose \
    > "$LOG_DIR/iter-$i.jsonl" 2>&1
  rc=$?
  after=$(commits)

  if (( rc != 0 )); then
    echo "claude è uscito con codice $rc: attendo ${SLEEP_ON_ERROR}s e riprovo"
    sleep "$SLEEP_ON_ERROR"
    continue
  fi

  if (( after == before )); then stall=$((stall + 1)); else stall=0; fi
  echo "Commit: $before → $after (stallo: $stall/$STALL_LIMIT)"
  (( stall >= STALL_LIMIT )) && { echo "⚠️ Nessun progresso: controlla $LOG_DIR"; exit 3; }
done

echo "⚠️ Raggiunto MAX_ITER=$MAX_ITER senza completamento"; exit 4
