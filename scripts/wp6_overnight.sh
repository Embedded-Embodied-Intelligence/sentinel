#!/usr/bin/env bash
# WP6c: the owner's overnight chain of the WP6 LLM runs (docs/reports/WP6c.md). Start it on a
# clean tree from the repository root, in tmux:
#
#   tmux new-session -s wp6 'bash scripts/wp6_overnight.sh 2>&1 | tee -a wp6_overnight.log; exec bash'
#
# Each step runs one study, then commits its run directory alone (a pathspec commit of
# results/wp6); the chain stops at the first non-zero exit and pushes after the last step.
# Resume from step N on a clean tree: bash scripts/wp6_overnight.sh N (a study stopped by a
# rate limit or by missing credits, exit status 3, resumes from the LLM cache). Print the
# steps without running them: bash scripts/wp6_overnight.sh --dry-run [N].
#
#   1-3  the RQ5 Ollama runs again, replayed from data/llm_cache/rq5 (no Ollama call; a cache
#        miss is an error)
#   4    RQ1 with both backends: Ollama replayed from the committed RQ1 Ollama run, OpenRouter
#   5-7  the RQ5 studies with both backends: Ollama replayed as in 1-3, OpenRouter
#   8    the RQ5 online check (OpenRouter)
set -euo pipefail

dry_run=0
if [[ ${1:-} == --dry-run ]]; then
  dry_run=1
  shift
fi
first=${1:-1}
cd "$(git rev-parse --show-toplevel)"
if (( !dry_run )) && [[ -n "$(git status --porcelain)" ]]; then
  echo "the working tree is not clean: commit or remove the changes first" >&2
  git status --short >&2
  exit 1
fi

rq1_ollama=results/wp6/20261023-084159-73dcf94e/llm_cache.jsonl.gz  # the committed RQ1 Ollama run
rq5_ollama=data/llm_cache/rq5/ollama.jsonl  # the answers of the three RQ5 Ollama runs

# step N MESSAGE STUDY CONFIG [OPTIONS...]: run the study unless N < first, then commit its run
# directory; the fixer hooks are skipped so that no hook rewrites generated results
# (CLAUDE.md invariant 2), while the large-file and secret checks still run.
step() {
  local n=$1 message=$2 study=$3 config=$4
  shift 4
  local command=(uv run python -m "sentinel.experiments.$study" --config "configs/$config.toml"
    --out results/wp6 "$@")
  if (( n < first )); then
    echo "step $n: skipped ($message)"
    return
  fi
  if (( dry_run )); then
    echo "step $n: $message"
    echo "  ${command[*]}"
    return
  fi
  echo "step $n: $message, started $(date -u +%FT%TZ)"
  echo "  ${command[*]}"
  "${command[@]}"
  git add -- results/wp6
  SKIP=end-of-file-fixer,trailing-whitespace git commit -q -m "WP6c: $message" -- results/wp6
  echo "step $n: committed $(git log -1 --format=%h), $(date -u +%FT%TZ)"
}

step 1 "RQ5 event study, Ollama (replay)" event_study wp6_rq5_events \
  --backend ollama --cache-mode replay
step 2 "RQ5 proposal study, Ollama (replay)" proposal_study wp6_rq5_proposals \
  --backend ollama --cache-mode replay
step 3 "RQ5 explanation study, Ollama (replay)" explanation_study wp6_rq5_explanations \
  --backend ollama --cache-mode replay
step 4 "RQ1 run, both backends (Ollama replayed, OpenRouter)" wbs_study wp6_rq1 \
  --replay "ollama=$rq1_ollama"
step 5 "RQ5 event study, both backends (Ollama replayed, OpenRouter)" event_study \
  wp6_rq5_events --replay "ollama=$rq5_ollama"
step 6 "RQ5 proposal study, both backends (Ollama replayed, OpenRouter)" proposal_study \
  wp6_rq5_proposals --replay "ollama=$rq5_ollama"
step 7 "RQ5 explanation study, both backends (Ollama replayed, OpenRouter)" explanation_study \
  wp6_rq5_explanations --replay "ollama=$rq5_ollama"
step 8 "RQ5 online check, OpenRouter" online_study wp6_rq5_online
if (( dry_run )); then
  echo "dry run: git push"
  exit 0
fi
git push
echo "done: every run committed and pushed, $(date -u +%FT%TZ)"
