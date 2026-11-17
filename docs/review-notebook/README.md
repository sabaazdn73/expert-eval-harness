# A Review Notebook for Civil Engineers to Evaluate Frontier Models

A structural engineering review, module by module, written for two readers: the engineer who wants the fundamentals back in hand, and the evaluator who needs to know where an AI model's structural reasoning can go wrong and how to check it.

Each module has the same parts:

- the idea, in plain words;
- a worked example with a figure, every number computed in a script, checked two ways and checked again by an independent reviewer;
- a practice problem with its answer;
- a trap to test on AI models;
- the check an AI review agent should run, computed by a tool rather than recalled.

Selected examples become tasks in this harness, with numerical checks, a rubric and the expert's notes, so the traps can be measured on Claude and Gemini models. The traps are hypotheses until those runs are done; results will be added with the model version and date.

Code clauses are pointers to check in the edition in force. No code text is reproduced.

## Modules

| # | Module | Status | Harness tasks |
|---|---|---|---|
| 1 | [Load path and static equilibrium](module-01-load-path.md) | Written, 31 sections with 34 figures | [`str-lp-*`](../../tasks/) (8) |
| 2 | [Loads and load combinations](module-02-loads.md) | Written, 28 sections with 28 figures (ASCE 7-22 and Eurocodes) | [`str-ld-*`](../../tasks/) (8) |
| 3 | Structural analysis | Planned | |
| 4 | Section behaviour | Planned | |
| 5 | Reinforced concrete design | Planned | |
| 6 | Stability | Planned | |
| 7 | Dynamics and seismic | Planned | |
| 8 | Foundations | Planned | |
| 9 | Steel basics | Planned | |

Also on the web: [tnega.app/notebook](https://www.tnega.app/notebook/).
