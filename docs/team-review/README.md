# Team review on a public task: the skybridge sliding bearing

One trial of the harness's team review mode (`--team`, see [Team review](../../README.md#team-review---team) in the README) on
[`tasks/m1-t2-skybridge-sliding-bearing`](../../tasks/m1-t2-skybridge-sliding-bearing), one of my six micro1 Eval
Hackathon tasks. I made this task public after the hackathon so that the whole process can be read: the drawings, the
calculation under review, the draft review, the key, and here every message the agents exchanged.

- [Watch on YouTube](https://www.youtube.com/watch?v=srZwcUZGGEk) (4K, 2:22), or here as
  [`team-review-m1-t2.mp4`](team-review-m1-t2.mp4): the narrated screen recording of the run with the task drawings; English subtitles in [`team-review-m1-t2.en.srt`](team-review-m1-t2.en.srt)
- [`channel.html`](channel.html): the whole conversation as a chat page (download and open it in a browser)
- [`channel.json`](channel.json): the same conversation as data
- [`grade-2026-11-01-key.json`](grade-2026-11-01-key.json): the grader's item-by-item verdict

## The task

A pedestrian skybridge spans 66 ft between a parking garage (special RC shear walls, R = 6) and an office building
(steel special moment frames, R = 8) in Salt Lake City. At the garage end it rests on a sliding bearing: a 6 in. PTFE pad
on a 16 in. stainless steel sheet, 5.0 in. of travel each way (detail 4/S-401). The fabricator's delegated engineer
calculates 1.04 in. of movement and calls the bearing OK; the junior engineer's draft review stamps it No Exceptions
Taken. The engineer of record asks the model to check both before signing.

The governing check is ASCE 7-22 §12.12.3: a member spanning between structures is designed for δ<sub>MCE</sub>
(Eq. 12.8-17, 1.5R δe/Ie + δdi) of both structures moving in opposite directions, at the bearing. That gives
1.85 + 3.84 = 5.69 in., 6.05 in. with thermal: the bearing is short, and the pad would run off its stainless sheet.

## The run

```
python3 -m harness.run run --models claude-sonnet-5-5:1 --team --live --sandbox local --max-turns 40 \
  --team-agents 3 --budget-claude 5.5 --tasks "tasks/m1-t2-skybridge-sliding-bearing" --judge claude-opus-5-5
```

| | |
|---|---|
| Agents | 6: code basis, lead, three members (`seismic-demand`, `bearing-travel`, `review-corbel-draft`), checker, all Claude Sonnet 5.5 |
| Conversation | 10 posts, 12 questions between agents, no part sent back by the checker |
| Model calls | 10, each agent with its own local Python sandbox and the task files |
| Time | 6.3 minutes, 27 November 2026 |
| Estimated cost | $1.70 (Sonnet $1.61, grading by Claude Opus 5.5 $0.08) |
| Result | fail: 5 of 12, with required items 1 and 2 not earned |

The grade above was given with the 1 November draft of the key; the key in `tasks/` is the final version used for the
hackathon results. Items 1 and 2 (the δ<sub>MCE</sub> basis and the absolute sum) are required in both versions and
are not earned in either, so the trial fails with both.

## What happened

The team did most of the review well. It took the garage displacement at the bearing (0.19 in.) instead of the
center of mass (0.12 in.), added the diaphragm deformation, amplified the office building's elastic 0.32 in. that the
fabricator had used as is, used the absolute sum instead of SRSS, and returned the submittal: revise and resubmit.

It also found the right doubt, and then argued it away:

1. The lead's plan asked the agents to "check whether the 7-22 separation provision requires the MCE-level
   amplification".
2. `bearing-travel` showed what that would mean: "With δdi × Cd it is 5.32 in. (ratio 1.06), which exceeds 5.0 in."
3. In the next round `code-basis`, answering from memory, wrote: "I recall no 1.5 factor in the ASCE 7-16 separation or
   spanning-member clauses." At the same time `seismic-demand` wrote: "I withdraw the ×1.5 "MCE" case as a code
   requirement."
4. The checker followed: "I do not treat a 1.5 × MCE factor as a code requirement." The team's answer: 3.66 in. of
   movement, bearing OK.

## How it compares

| Claude Sonnet 5.5 on this task | Trials | Result |
|---|---|---|
| As a team (this run) | 1 | fail |
| Alone | 2 | 5 and 4 of 12, fail |
| Alone, with the code library as a look-up tool | 2 | 11 and 11 of 12, pass |

The solo results are from the hackathon runs ([results.md](../results.md)), with the same task, the final key and
the same grader.

## Reading it

This is one trial, so it shows a mechanism, not a rate. Every agent is the same model, so the team shares one blind
spot: here the 2016 edition recalled from memory instead of the 2022 text. The team caught every error that could be
found from the documents in the package, and missed the one that needed the current code text, which no agent had.
Alone, Sonnet passed this task only when it could look the text up. The next run to make is the team with
`--model-library`, to see whether the team adds anything once the governing text is in reach.
