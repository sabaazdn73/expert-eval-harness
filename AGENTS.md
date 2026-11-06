# Working in this repository (for coding agents)

Python 3.10 or later, standard library only: there is nothing to install.

1. Check the wiring, offline and free:
   `python3 -m pytest -q tests` and `python3 -m harness.run run --models mock-good mock-bad --k 1`
2. Validate the tasks before any paid call: `python3 -m harness.run preflight --tasks "tasks/*"`
3. Live runs need the user's own keys, set in the user's shell and never written to a file: `ANTHROPIC_API_KEY` for
   Claude models; for Gemini, a Google Cloud project with Vertex AI (see "Gemini models" in README.md). Ask before a
   paid run; `--max-calls` and `--budget-*` stop a run that would cost more than intended.
4. Run a model on a task, then report:
   `python3 -m harness.run run --models claude-haiku-5-5 --k 2 --tasks "tasks/str-beam-stirrup-rfi-aci318"`
   `python3 -m harness.run report runs/<run_id>`
5. Check a grader against a key before trusting it: `python3 grader_check.py --judge claude-opus-5-5 --tasks "tasks/str-beam-stirrup-rfi-aci318"`
   (offline wiring test: `--judge mock-judge`). The reference answer must pass, the lure and boundary answers must fail.

Task format: `task.json` (files, items with points and required flags, max_score, pass_score, answer_format, checks),
`prompt.md`, `files/`, `key.md`, `grader_check/`. The complete example is `tasks/str-beam-stirrup-rfi-aci318`.

The shared local sandbox (`--sandbox local`) runs model code under macOS `sandbox-exec`. On Linux it refuses unless
`EEH_UNSAFE_SANDBOX=1` is set, which runs the code without network or file isolation: use it only in a throwaway
container. Tasks with `"code_execution": false`, such as the public sample, need no sandbox.

Results of the micro1 Eval Hackathon are in `docs/results.md`; its six tasks are described in `docs/hackathon-tasks.md`
and are not in this repository.
