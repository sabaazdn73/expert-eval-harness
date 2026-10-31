# Expert Eval Harness

**Expert-written tasks, automatic grading, and a gate that decides which tasks are hard enough to keep.** A small, dependency-free Python harness for evaluating Claude models on professional tasks in structural engineering and finance.

Each task is a folder with the prompt, any input files, an answer key and a rubric written by a domain expert. The harness runs every task on several models, several times each, grades the answers, and reports how often each model gets it right.

> **Status: early (v0.1).** The pipeline runs end to end offline with mock models; the first runs on live models are next. All tasks are original and written for this repository.

## How it works

1. **Task.** `tasks/<id>/` holds `prompt.md`, optional input files (text, PDF, images), optional reference notes in `refs/`, and `task.json` with the answer key.
2. **Run.** Every task goes to every model `k` times through the Claude Messages API. The model ends its reply with a JSON block of final answers.
3. **Grade.** Two layers:
   - **Deterministic checks:** numbers within an expert-set tolerance, true/false findings, choices.
   - **LLM-as-judge:** a separate model scores each rubric item (for example "does not invent paragraph numbers") against the expert's notes.
   A trial passes only if every check and every rubric item passes.
4. **Measure.** Pass rate, **pass@k** (solved at least once in k tries) and **pass^k** (solved in all k tries, a reliability measure).
5. **Gate.**
   - `difficulty` mode keeps only tasks the models do not find easy, the way expert data teams select tasks for final runs.
   - `quality` mode blocks a release when a model's pass rate falls below a threshold, used as a CI deployment gate.

## Research question built in

`--with-refs` gives the model each task's reference notes. Running the same tasks with and without references measures whether up-to-date, citable sources make a smaller model more accurate, and whether they ever make a wrong answer more convincing.

## Quick start

```bash
# Offline self-test: no API key, no cost
python3 -m harness.run run --models mock-good mock-bad --k 2

# Live models (set the key in your own shell, never in a file)
export ANTHROPIC_API_KEY="..."
python3 -m harness.run run --models claude-haiku-5-5 claude-sonnet-5-5 --k 3
python3 -m harness.run run --models claude-haiku-5-5 --k 3 --with-refs

# Reports and gates
python3 -m harness.run report runs/<run_id>
python3 -m harness.run gate runs/<run_id> --mode difficulty --max-pass 0.5
python3 -m harness.run gate runs/<run_id> --mode quality --model claude-haiku-5-5 --min-pass 0.8
```

`--max-calls` (default 60) stops a run before it starts if it would make more model calls than you meant to pay for. Token use is printed after every run.

## Tasks in v0.1

| Task | Domain | What it tests |
|---|---|---|
| `fin-capitalised-interest` | Finance | Three statements that cannot balance once ASC 835-20 interest capitalisation is applied |
| `fin-ev-bridge-convertible` | Finance | EV bridge with a convertible already in the diluted shares and leases hidden in total borrowings |
| `fin-dcf-stub-gordon` | Finance | Mid-year DCF with a stub period and a Gordon terminal value |
| `fin-invented-standard` | Finance | A confident request built on an accounting amendment that does not exist |
| `str-beam-flexure-aci318` | Structural | RC beam flexure check that fails by under 3% |
| `str-load-combination-wind` | Structural | Governing compression and uplift with wind reversing the load |

## Adding a task

Copy a task folder, write the prompt, list the final answers in `answer_format`, and add `checks` (with tolerances) and `rubric` items. Put the full worked solution in `expert_notes`: the judge uses it as ground truth. Keep answer keys out of any public benchmark you want to stay uncontaminated.

## CI

`.github/workflows/eval.yml` runs the offline self-test on every push. From the Actions tab, **Run workflow** runs live models with the `ANTHROPIC_API_KEY` repository secret and fails the job if the quality gate is not met.

## License

MIT
