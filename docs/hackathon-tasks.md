# The six hackathon tasks (task cards)

These are the six structural review tasks submitted to the micro1 Eval Hackathon in November 2026. Each card says what the model is given, what it is asked to do and how it is scored. The prompts, the expert answer keys and the traps are not published, so that the tasks can still be used to evaluate models. For a complete task you can open and run, with its files, prompt and key, see the public sample [`tasks/str-beam-stirrup-rfi-aci318`](../tasks/str-beam-stirrup-rfi-aci318), built to the same standard.

## What every task has in common

- **A real review situation.** A structural engineer of record has to sign off on a document from someone else: a supplier's calculation submittal, a deferred submittal, a contractor's RFI or a mixture submittal. A junior engineer has already written a draft review. The model is asked to review both before the engineer signs.
- **A full project package.** The model gets the documents an engineer would have: general notes (S-001), the relevant drawing sheets, sections of the engineer's calculation package, the document under review, the draft review, and where they matter letters, addenda, test data or the state code amendments. The projects are fictional: five tasks are on one public parking structure in Salt Lake City (2024 IBC as adopted by Utah, ASCE 7-22, ACI 318-19), and one is on a mixed-use tower with special shear walls.
- **The same request.** Say whether the document can be accepted, give the checks behind the decision with numbers and code references, and write the comments or response ready to send. A short JSON block at the end carries the key numbers for automatic checks.
- **A written expert key.** For each task the engineer writes the verified answer with the governing clauses and the source of every value, what is right and wrong in the document and in the draft, the fix, wrong but plausible answers, and scored items. Each item is earned in full or not at all; calculated numbers are scored by an accepted range; some items are required for a pass.
- **The same environment for every model.** Every trial runs in the same local sandbox with the task files under their real names and a Python tool, with the same turn limit (40). In a second run the models also got look-up tools for a library of the code editions the tasks cite.
- **Two graders.** Claude Opus 5.5 grades every answer item by item against the key; Gemini 4 Argon grades it again. Every disagreement goes to the expert. Before the paid run each key is tested on three answers written for the purpose: a reference answer (must pass with full marks), a lure answer that takes the trap (must fail), and a boundary answer one point below the pass line (must fail).

## The cards

| Task | Document under review | Inputs given to the model | Items (required) | Max / pass |
|---|---|---|---|---|
| Precast screen panel connections (`m1-t1`) | Precast supplier's connection calculation submittal, with the junior engineer's draft review | 5 PDFs: general notes S-001, precast panel sheet S-501, calc package section on seismic story displacements, the supplier's submittal, the draft review | 10 (5) | 13 / 10 |
| Skybridge sliding bearing (`m1-t2`) | Deferred submittal on the bearing movement of a pedestrian bridge between two buildings, with the draft review | 6 PDFs: S-001, skybridge sheet S-401, calc package section on the seismic analysis, the neighbouring building's seismic data letter, the deferred submittal, the draft review | 10 (3) | 12 / 9 |
| Concrete mixture submittals (`m1-t3`) | Three concrete mixture submittals and the cost of the decision, with the draft review | 9 PDFs: S-001, foundation plan S-101, three mixture submittals, cement mill certificates and aggregate data, the transmittal and supplier letter, the Utah code amendments, the draft review | 10 (4) | 14 / 11 |
| Core wall joint RFI (`m1-t4`) | Contractor's RFI on the dowels at a deck-to-core-wall joint, with the draft response | 5 PDFs: S-001, core wall details S-311, calc package section on diaphragm transfer, the RFI, the draft response | 7 (3) | 10 / 8 |
| Egress stair sliding seat (`m1-t6`) | Precast stair supplier's calculation submittal for a sliding seat, with the draft review | 5 PDFs: S-001, stair sheet S-504, calc package section with the lateral analysis output, the supplier's calculation, the draft review | 9 (3) | 12 / 9 |
| Special shear walls, Utah (`a01r3`) | A permit resubmittal of six special shear walls (drawings and lateral calc), with an email thread and an addendum | 7 PDFs and 5 CSV files: drawings S-001, S-201 and S-401, the lateral calc, the seismic design parameters report, the addendum, the email thread, two Utah code amendment sections, and ETABS output tables (story forces, pier forces, drifts, displacements, modal mass) | 10 (4) | 14 / 11 |

## What the items test

Across the six keys, every item belongs to one of these groups. The results by group are in figure 2 and figure 6 of [results.md](results.md).

- Computation on a given method
- Review action (overturning the draft where it is wrong)
- Utah amendment applied
- Current code edition
- Governing clause, not the neighbouring one
- Permitted relaxation recognised
- A check the draft did not raise
