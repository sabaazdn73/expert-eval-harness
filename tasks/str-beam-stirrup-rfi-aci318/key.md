# Sample task - Beam B-3 stirrup spacing, RFI-012 (public key)

Job 26-900, Linden Court Office Building (fictional). RFI-012 (Brenlow Builders, 10/02/2026) asks to place the B-3 end-zone stirrups at #4 @ 10 in. instead of #4 @ 6 in.; junior draft response (J. Ostrowski, 10/05/2026) accepts it.

This is a public sample built to the same standard as the private hackathon tasks. Because its key is public, it is a demonstration of the format, not an uncontaminated benchmark item.

## Basis (checked on the text of ACI 318-19)
- S-001 A2: ACI 318-19. S-001 B1: beams, girders and slabs, Levels 2 to Roof, f'c = 4,000 psi; columns and beam-column joints 5,000 psi. S-001 B2: column concrete is placed in the joint region within the column outline only. S-001 D2: contractor calculations use the strengths of B1.
- Table 21.2.1(b): phi = 0.75 for shear.
- 9.4.3.2: critical section at d from the face of support (conditions met, calc 4.3).
- 22.5.1.1: Vn = Vc + Vs. Table 22.5.5.1(a): Vc = 2 lambda sqrt(f'c) bw d (Nu = 0) where Av >= Av,min. lambda = 1.0 (normalweight).
- 22.5.8.5.3: Vs = Av fyt d / s.
- 9.6.3.4 and Table 9.6.3.4: Av,min/s = greater of 0.75 sqrt(f'c) bw / fyt and 50 bw / fyt.
- 9.7.6.2.2 and Table 9.7.6.2.2: where Vs <= 4 sqrt(f'c) bw d, maximum spacing is the lesser of d/2 and 24 in.
- 22.5.1.2: Vu <= phi (Vc + 8 sqrt(f'c) bw d).

## The beam and the proposal (from the inputs)
- B-3, line 3, grids C to D: bw = 16 in., h = 30 in., d = 27.5 in. (S-201). #4 stirrups, 2 legs, Av = 0.40 in2; fyt = 60,000 psi (S-001 C1). Drawn: #4 @ 6 in. within 6'-0" of each support.
- Calc 4.3: Vu at d from the face of the grid C support = 94.0 kips (governs; grid D 81.6 kips). Drawn #4 @ 6: phi Vn = 124.2 kips, D/C 0.76.
- RFI-012: #4 @ 10 in. in both end zones, checked with f'c = 5,000 psi because the beam "frames into column C-3": phi Vn = 96.2 kips, ratio 0.98, "OK". The draft response accepts it after checking only the arithmetic.

## Verified answer
- The beam is 4,000 psi concrete (S-001 B1). The 5,000 psi of the columns and joints applies only within the column outline (S-001 B2); the end zone of B-3 is outside it.
- With f'c = 4,000 psi: Vc = 2 x 1.0 x 63.25 x 16 x 27.5 = 55.66 kips. #4 @ 10 in.: Vs = 0.40 x 60 x 27.5 / 10 = 66.00 kips. phi Vn = 0.75 x (55.66 + 66.00) = 91.24 kips < Vu = 94.0 kips. D/C = 1.03. The proposal is NOT adequate.
- Largest spacing that works: Vs,req = 94.0 / 0.75 - 55.66 = 69.68 kips; s <= 0.40 x 60 x 27.5 / 69.68 = 9.47 in. A revision to #4 @ 9 in. gives Vs = 73.33 kips, phi Vn = 96.74 kips, D/C 0.97, which is acceptable.
- Spacing limit: Vs (66.0 or 73.3 kips) <= 4 sqrt(f'c) bw d = 111.3 kips, so s,max = d/2 = 13.75 in.; 9 in. and 10 in. both meet it. Av,min at 10 in. = max(0.126, 0.133) = 0.133 in2 (at 9 in. 0.120 in2) <= 0.40 in2, so Table 22.5.5.1(a) remains valid. Cross-section limit 22.5.1.2: 208.7 kips >= 94.0 kips.
- RFI-012 is NOT ACCEPTED as submitted. An acceptable alternative is #4 @ 9 in. (2 legs) within 6'-0" of each support; the drawn #4 @ 6 in. remains acceptable. The middle zone #4 @ 12 in. is unchanged (calc 4.3, phi Vn 83.0 kips > 79.2 kips).

## What is right and wrong
RFI-012:
- Right: Vu = 94.0 kips from calc 4.3; Av = 0.40 in2; the Vs arithmetic; the d/2 spacing limit.
- Wrong: f'c = 5,000 psi for the beam. S-001 B1 gives 4,000 psi for beams; B2 limits the 5,000 psi concrete to the column outline.
Draft response:
- Wrong: accepts the RFI after checking only the arithmetic, without checking the material strength against S-001.

## Fix the response should give
Not accepted. Keep #4 @ 6 in., or revise the end zones to #4 @ 9 in. (2 legs) maximum within 6'-0" of grids C and D, with the check at f'c = 4,000 psi.

## Wrong but plausible answers
- Accepting #4 @ 10 in. with f'c = 5,000 psi (phi Vn 96.2 kips, D/C 0.98): the RFI and the draft.
- Accepting #4 @ 10 in. because the shortfall is "only 3 percent". A design strength below Vu is not acceptable.
- Allowing a spacing up to about 10.4 or 10.5 in., which is the limit with 5,000 psi.
- Using the detailed Vc equation (b) of Table 22.5.5.1 is permitted, but it gives a lower Vc and so a stricter result, not a reason to accept: with the 3-#8 top bars as tension steel at the support (As = 2.37 in2, rho_w = 0.0054), Vc = 8 x 0.175 x 63.25 x 440 = 39.0 kips, phi Vn = 78.8 kips and s <= 7.6 in.; with the 4-#8 bottom bars (As = 3.16 in2, rho_w = 0.0072), Vc = 43.0 kips, phi Vn = 81.7 kips and s <= 8.0 in. These are accepted readings (items 2 and 4), not errors.

## Strong vs weak
A strong response rejects the RFI, shows that the beam is 4,000 psi concrete per S-001 B1 and B2, computes phi Vn = 91.2 kips < 94.0 kips for #4 @ 10 in., gives the largest spacing (9.47 in., so #4 @ 9 in.), confirms the spacing and Av,min limits, and writes a response ready to send. A weak response repeats the RFI calculation and accepts it, or rejects it without a number.

Not graded: the congestion itself, alternative bar arrangements beyond the spacing, the pour date.

## Scoring (10 points)
How to score
- Each item is earned in full or not at all. There is no partial credit within an item.
- A calculated number earns its item when it falls inside the accepted range and comes from the method the item names.
- Each error is taken once, in the item it belongs to.
- Safety comes before carry-over. A value listed under "Does not earn" never earns, on any basis.
- The deliverable item is earned only when the deliverable carries the correct action and the corrections this key requires.
- Findings outside the items earn nothing. A wrong extra statement costs nothing unless it contradicts an item or changes the action or a graded value.
- Pass: at least 8 of 10, with items 1, 2 and 3 each earned in full.

Items
1. Concrete strength of the beam (2 points, required)
   Earns: f'c = 4,000 psi for B-3 per S-001 B1, and the 5,000 psi used by the RFI identified as the column and joint concrete, which S-001 B2 limits to the column outline.
   Does not earn: 5,000 psi, or 4,000 psi stated without identifying the RFI's error.
2. Shear strength of the proposal (2 points, required)
   Earns: phi Vn for #4 @ 10 in. with f'c = 4,000 psi, Table 22.5.5.1(a) and 22.5.8.5.3, compared with Vu = 94.0 kips: not adequate.
   Accepted range: 91.0 to 91.5 kips (91.24), D/C 1.02 to 1.04. A response that uses Table 22.5.5.1(b) earns the item with phi Vn 78.5 to 82.0 kips and the same conclusion.
   Does not earn: 96.2 kips (5,000 psi); any conclusion that the proposal is adequate.
3. Action (1 point, required)
   Earns: RFI-012 not accepted as submitted (or revise and resubmit), overturning the draft's "Accepted".
   Does not earn: accepted, or accepted as noted at #4 @ 10 in.
4. Largest acceptable spacing (2 points)
   Earns: the largest spacing with f'c = 4,000 psi stated (9.4 to 9.5 in., 9.47, with Table 22.5.5.1(a); or 7.6 to 8.1 in. with Table 22.5.5.1(b)), and an acceptable revision at or below the response's own limit offered (#4 @ 9 in. or closer, 2 legs, within 6'-0" of each support).
   Does not earn: 10 in.; 10.4 to 10.5 in. (5,000 psi); keeping #4 @ 6 in. without stating the limit.
5. Detailing limits (1 point)
   Earns both: the maximum spacing d/2 = 13.75 in. applies because Vs <= 4 sqrt(f'c) bw d (111.3 kips), and Av = 0.40 in2 meets Av,min (about 0.12 to 0.14 in2).
6. The draft's error (1 point)
   Earns: the draft accepted the RFI on its arithmetic alone and did not check the material strength against S-001.
7. RFI response ready to send (1 point, deliverable)
   Earns: a response that opens with the decision (not accepted), gives the finding with S-001 B1 and B2 and the numbers, and states the acceptable alternative (#4 @ 9 in. maximum, or as drawn).
