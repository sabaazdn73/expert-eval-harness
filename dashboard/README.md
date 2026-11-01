# Task pipeline dashboard

A local workspace for building expert evaluation tasks with the method in
[Where the Human Belongs](../docs/where-the-human-belongs.md), and a read-only copy of it for a website.

Standard library only, like the harness. Nothing is uploaded anywhere: the server binds to `127.0.0.1`,
project records stay in a data folder outside this repository, and the public page shows only what
you export.

## Run it on your computer

```bash
cd expert-eval-harness
export ANTHROPIC_API_KEY="..."            # optional; only needed to start live model runs from the page
python3 dashboard/server.py --data ~/Documents/Codex/private-evals/dashboard
# open http://127.0.0.1:8765
```

The page shows whether a key is set in the shell that started the server. It never reads or displays the key.

## What it does

| Tab | Local workspace | Public copy |
| --- | --- | --- |
| Tasks | Every task as a strip of the nine stages; red where the human is needed; create a task | Same, read only |
| Task page | Design-basis sheet with signature, stage status, notes, human minutes and sign-off at each gate, accepted alternatives and lures, file uploads (inputs, prompt, key, golden files), the grader-package check, model runs and a run launcher, the decision log | Basis, stages, package check and run results |
| Pipeline | The nine stages: what AI does, what the human does, the output, the three human gates | Same |
| What the grader needs | Every part of a task package and the basis-of-design fields | Same |

Uploads go into the task folder itself: input files to `files/` (and into `task.json`), the prompt to
`prompt.md`, the key to `key.md` (and `key_file` in `task.json`), golden files to `golden/`.

Runs started from the page call `python -m harness.run run` with the task folder, the models and `k` you
choose and a `--max-calls` cap, and show the log live. Results appear on the task page from `runs/`.

## Human gates

Stages 1, 2 and 9 cannot be marked done without a signature. Stage 2 is the design basis: open the
official sources and read the amendments clause by clause for every provision the task uses before you sign.
Every other stage is done by AI and checked by the human at one decisive point, which the page names.

## The public page

```bash
python3 dashboard/server.py --data ~/Documents/Codex/private-evals/dashboard --export ~/path/to/site/eval
```

Only tasks you mark "Show this task on the public page" are exported, and only their progress, sign-off
dates, the package check and run pass rates (with `public_runs` you can choose which runs). The prompt,
answer key, traps, notes and file contents are never exported: a published task is a contaminated task.
Copy `web/index.html`, `web/app.js` and `web/style.css` next to the exported `data.json`; the same page then
runs read only.

## Project record

`<data>/projects/<id>.json`: `id`, `title`, `structure`, `domain`, `task_dir`, `public`, `public_summary`,
`basis` (the fields of the basis sheet, `signed_by`, `signed_at`), `stages` (`s1` to `s9`: `status`, `date`,
`note`, `minutes`, `signed_by`), `alternatives`, `lures`, `log`, and optionally `run_task_ids`, `golden_dir`
and `public_runs`.
