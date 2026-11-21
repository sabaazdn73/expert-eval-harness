# Evals after release: what this harness does, and what the review agent will need

Notes from Anthropic Academy, *Introduction to evals*, lesson 4: "Evals in production: CI, batch, and drift"
([academy.claude.com](https://academy.claude.com/courses/introduction-to-evals/evals-in-production)), checked against
this repository in November 2026.

The lesson protects a product prompt that is already in use: it must not get worse when someone edits it, and it must
not drift as real inputs change. This harness has a different main job, measuring how far models can be trusted on
expert tasks, but the same four steps apply to it, and they will apply in full to the Tnega review agent once it reviews
real drawings.

## The four steps, and where this repository stands

| Step in the lesson | In this repository |
|---|---|
| **1. Smoke eval on every pull request**: a small, fast subset of the suite, scored against a threshold, with the result on the pull request. | `eval.yml` runs the offline self-test (mock models, free) on every push and pull request: it tests the harness code, not a model. `grader-check.yml` runs on pull requests that change a task, the grader or the grading code: the grader must pass each task's reference answer and fail its lure and boundary answers (`grader_check.py --strict`). Here the thing to protect is the key and the grader, so that is the smoke test. |
| **2. Make the check required**, so a low score blocks the merge. | The checks fail the job; to block merging, add them as required status checks in the branch protection rule for `main` (repository Settings, Branches). The live quality gate (`gate --mode quality --min-pass 0.8`) runs only from the Actions tab, by hand, because it calls paid models. |
| **3. Run the full suite as one batch**, at half price, since nobody waits on it. | `--batch` (from v0.4) sends every plain Claude call of a run through the Message Batches API: the model answers of tasks without a tool loop, and the grading by graders without `--judge-tools`. Requests are matched by `custom_id`; a request that errored or expired is reported in its own trial, is not charged, and `--resume` runs it again. Tool loops (code execution, the code library, the local sandbox) need a reply on every turn, so they stay streamed. The cost estimate printed before a run already applies the discount. |
| **4. Grade a sample of live traffic every night**, alert on unusual drops, and turn each failure into a new case. | No live traffic yet. The parts are here: graders that score against an expert key, two grader families with agreement statistics, expert adjudication, and a library of documented failures that become tasks and traps. |

## Where this harness already goes further than the lesson

- **Graded against an expert key, not only a rubric.** The lesson's live-traffic judge has no expected answers; every
  task here has a verified answer key with scored items, some of them required.
- **Two graders from different model families**, their agreement (item level and Cohen's kappa), and the expert settling
  every disagreement. The lesson only says that people should still read some answers.
- **The key is tested before money is spent**: reference, lure and boundary answers with known scores.
- **Reliability, not one lucky answer**: several trials per task, with pass@k and pass^k.
- **A difficulty gate** that keeps only tasks the models do not find easy, which a product regression suite does not need.

## What the review agent will need when it is live

When the Tnega review agent starts reviewing real drawings, step 4 becomes the most important one:

1. **Sample.** Keep a few percent of real reviews (with the client's permission and without confidential details).
2. **Grade.** A grader scores each sampled review against a written rubric: the governing code and adopted edition named,
   every required check done, no invented clause, and the verdict supported by numbers. An engineer reads part of the
   sample every week, because the grader also needs checking.
3. **Alert on real drops.** Compare each night with the average of recent nights and alert only on a large drop (start
   with two standard deviations and tune it).
4. **Feed failures back.** Every review the grader or the engineer marks wrong gets an expert answer and becomes a new
   task in this harness, so the suite follows the drawings the agent actually sees.

The first human gate in [Where the Human Belongs](where-the-human-belongs.md), checking the project's jurisdiction and
adopted code edition, is also the first thing to check on live reviews: a new client in a new state is exactly the kind
of drift a fixed suite cannot see.
