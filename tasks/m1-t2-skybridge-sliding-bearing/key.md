# T2 - Skybridge sliding bearing at the L2 corbel, deferred submittal SB-7 review (answer key)

Job 26-210, RC Code Town Public Parking Structure, Salt Lake City. Submittal 05 12 00-07 (SB-7) Rev. 0, calculation TSF-2611 by Hollis Brandvold, P.E. (Tallgrass Steel Fabricators); junior draft review by Jamie Tran, EIT (No Exceptions Taken, 10/29/2026). The response has no files: the review, the numbers and the comments in the reply are what is graded.

## Basis (checked on the text, 2026-11-01)
- S-001: 2024 IBC as adopted by Utah, ASCE 7-22, AISC 360-22. Garage: building frame, special RC shear walls (Table 12.2-1 B4), R = 6, Omega0 = 2.5, Cd = 5, Ie = 1.0, SDC D, Type 1 torsional irregularity (cores C-1 and C-2 at lines 1-2, south of the center of mass).
- Office building (Kestrel & Moore letter, 10/06/2026): steel special moment frames (Table 12.2-1 C1), R = 8, Omega0 = 3, Cd = 5.5, Ie = 1.0, rigid diaphragms.
- ASCE 7-22 12.12.3, members spanning between structures: gravity connections and supports are designed for the maximum anticipated relative displacements, calculated using delta_MCE per 12.8.6, assuming the two structures move in opposite directions, with the absolute sum of the displacements.
- 12.8.6.4: delta_MCE = 1.5 R delta_e/Ie + delta_di (Eq. 12.8-17), at the location under consideration.
- 12.8.6.3: delta_DE = Cd delta_e/Ie + delta_di (Eq. 12.8-16); delta_e excludes the diaphragm deformation.
- 12.12.2, structural separation: delta_SS = sqrt(delta_DE1^2 + delta_DE2^2) (Eq. 12.12-2). This is the rule for the clear separation between buildings, not for a member that spans between them and sits on a bearing.
- 12.3.1.2: the decks are permitted to be idealized as rigid, but the model uses semi-rigid shell decks and Calc 40 Table 40.6A reports delta_di separately (S-001 seismic note 12).

## Facts from the inputs
- Bearing at CL skybridge, x = 126'-0", y = 256'-6" (S-401), on corbel C-1 at the north end of the east edge (grid G, lines 10-11), at the far end of the plan from the cores.
- Calc 40 Table 40.6, L2, case EX (5 percent eccentricity with Ax = 1.93): Ux = 0.040 in. at the SE corner (joint 7, y = 0), 0.200 in. at the NE corner (joint 77, y = 270 ft), 0.120 in. at the center of mass (joint 100). EY: Ux = 0.070 in. at the SE corner and -0.070 in. at the NE corner.
- Calc 40 Table 40.6A, L2, X: delta_di = 0.000 (SE), 0.051 (CM), 0.124 in. (NE).
- Office letter: elastic (not amplified) displacement at the bridge bearing E-W 0.32 in., N-S 0.29 in., computed with the model period (12.8.6.2) and including accidental torsion with Ax.
- Bearing (S-401 and TSF-2611): PTFE pad 6 in. along the bridge on a 16 in. stainless sheet, centered at setting, so 5.0 in. of travel each way; free to slide in all directions, no keeper bars or end stops; joint 7 in. Embed plate E1 is 1'-8" x 2'-8".
- TSF-2611: garage delta_e = 0.12 in. (Table 40.6 joint 100, the center of mass), Cd x 0.12 = 0.60 in.; office 0.32 in. used as is; SRSS per "ASCE 7-22 12.12.2" = 0.68 in.; plus thermal 0.36 in. (66 ft, 6.5e-6/F, 70 F) = 1.04 in. < 5.0 in. "OK (ratio 0.21)".

## Verified answer
- Garage delta_e at the bearing: rigid-body rotation along the east edge, 0.040 + 0.160 x 256.5/270 = 0.192 in. (0.200 in. at joint 77 is a conservative alternative). The calc's 0.12 in. is the center of mass, not the bearing location.
- Garage delta_di at the bearing: 0.124 x 256.5/270 = 0.118 in. (0.117 to 0.124 in. accepted).
- Garage delta_MCE = 1.5 x 6 x 0.192/1.0 + 0.118 = 1.85 in. (1.73 in. without delta_di).
- Office delta_MCE = 1.5 x 8 x 0.32/1.0 = 3.84 in.
- Required movement each way (12.12.3, absolute sum, opposite directions) = 1.85 + 3.84 = 5.69 in. (6.05 in. with the 0.36 in. thermal). Accepted 5.50 to 6.35 in.: without delta_di 5.55 to 5.57 in.; with 100 percent EX plus 30 percent EY at the bearing 5.84 in. (6.20 in. with thermal); with the joint 77 value about 5.8 in.; the joint 77 value with 100/30 and thermal about 6.31 in.
- Capacity 5.0 in. each way, so the bearing is NOT adequate: 5.69/5.0 = 1.14 (1.21 with thermal). The pad would run off the stainless sheet.
- Required stainless sheet length along the bridge = 6 + 2 x 5.69 = 17.4 in. (18.1 in. with thermal). Accepted 17.4 to 18.7 in.; a shorter sheet does not give the required travel. The length of embed plate E1 (1'-8") and the corbel edge control how long a sheet can be: with the bearing 12 in. from the SB-1 face, an 18 in. sheet reaches the end of E1 and leaves no room for the seal weld, so a longer E1 or another arrangement may be needed. A response that says E1 or the corbel limits the sheet length is not penalized.
- Joint: 7 in. against 6.05 in. with thermal, adequate.
- Action: REVISE AND RESUBMIT (REJECTED is also accepted). The draft's No Exceptions Taken would release bearing plates that are too short; fabrication of the plates is on hold pending this review.

## What is right and wrong
Calculation TSF-2611:
- Wrong: the combination rule. 12.12.2 (SRSS of delta_DE) is for building separation; a member spanning between structures is designed under 12.12.3 with delta_MCE and the absolute sum.
- Wrong: delta_DE with Cd instead of delta_MCE with 1.5R (factor 1.8 for the garage, 2.18 for the office).
- Wrong: the garage value at the center of mass instead of at the bearing, on a torsionally irregular structure; delta_di omitted.
- Wrong: the office elastic 0.32 in. used without any amplification.
- Right: the pad pressure (76 k on 84 in2 = 0.90 ksi), the reaction (D 40 k, L 36 k matches S-401 note 5), the 5.0 in. travel geometry, the thermal term.
Junior draft:
- Comment 1 (travel exceeds the movement, no keepers needed) is wrong.
- Comment 2 ("agrees with Table 40.6") is wrong: 0.12 in. is the center-of-mass row.
- Comment 3 (SRSS per 12.12.2 plus thermal is appropriate) is wrong.
- Comment 4: the joint conclusion is right (7 in. > 6.05 in.); the transverse travel is right but unsupported by numbers.
- Comment 5 (pad pressure and reaction) is right.
- No Exceptions Taken is wrong.

## Fix the comments should ask for
- Recalculate the movement under ASCE 7-22 12.12.3: delta_MCE (Eq. 12.8-17) for both structures, garage value at the bearing coordinates (Table 40.6 at x = 126 ft, y = 256.5 ft) plus delta_di from Table 40.6A, office elastic value times 1.5R/Ie, absolute sum, plus thermal.
- Provide at least about 5.7 in. (6.1 in. with thermal) of travel each way: a stainless sheet of at least about 18 in. along the bridge, or another bearing arrangement that gives the same travel, with the corbel and E1 checked for the bearing position at full travel.
- Resubmit; plate fabrication stays on hold.

## Wrong but plausible answers
- Amplifying with Cd (delta_DE) and adding the two buildings: about 3.2 to 3.5 in. with thermal, bearing OK. The location, the office Cd and delta_di can all be fixed and the bearing is still wrongly accepted, because 12.12.3 calls for delta_MCE.
- delta_MCE combined by SRSS: 4.26 in. (4.62 in. with thermal), bearing OK.
- The fabricator's lure fixed only (office times Cd) with SRSS at the center of mass: about 2.2 to 2.3 in., bearing OK.
- delta_MCE with the absolute sum but the garage taken at the center of mass: 4.92 to 5.04 in. without thermal, which passes against 5.0 in., and 5.28 to 5.40 in. with thermal, which fails; the location is wrong either way.
- R = 5 for the garage (special RC shear walls as a bearing wall system) put into Eq. 12.8-17 with the delta_e of the R = 6 model: 5.40 in., NG. S-001 states the building frame system with R = 6; and with R = 5 the forces, and so delta_e, rise by 6/5, so a consistent R = 5 gives the same 5.69 in.
- Calling the bearing adequate because the office delta_e "may be conservative" or because the movement can be halved.

## Strong vs weak
A strong response applies 12.12.3 to the bridge bearing, computes delta_MCE for both buildings at the bearing location with delta_di, adds them as opposite-direction movements, finds that 5.0 in. of travel is not enough, gives the required sheet length (about 17.4 to 18.1 in.), and returns the submittal for revision with comments that state each number and code section. A weak response corrects the visible errors (office Cd, center of mass, delta_di) and still accepts the bearing with delta_DE or SRSS.

Not graded: checks the response adds on the pad pressure, rotation, sole plate, friction on the corbel, transverse travel, the missing BDS-614 data sheet, the seal, the joint cover plate, or garage volume change. They earn no points and cost none, unless a wrong statement in them changes the action or one of the graded values.

## Scoring (12 points)
How to score
- Each item is earned in full or not at all. There is no partial credit within an item.
- A calculated number earns its item when it falls inside the accepted range given for that item and comes from the method the item names. The range is the criterion, not the single verified value. A number inside a range that is reached by a method listed under "Does not earn" earns nothing.
- Each error is taken once, in the item it belongs to. A later number that depends on an earlier graded quantity is judged on the response's own value of that quantity only where the item says "on the response's own value", and only when the later item's method is right. Otherwise the item's accepted range governs.
- Safety comes before carry-over. A value listed under "Does not earn" never earns, on any basis. A fix, a required dimension, a required movement or a required capacity never earns below the minimum the item states, whatever the response's own earlier value, because accepting it would release an unsafe detail. Where an item takes an error that another item also takes, the item says so and why.
- Deliverable items (the comments or the response ready to send) are earned only when the deliverable carries the correct action and the corrections this key requires. A well-written deliverable that sends the wrong decision earns nothing. This is deliberate and overrides the take-once rule for deliverable items: such a deliverable cannot be used, whatever else the response gets right.
- Findings outside the items earn nothing. A wrong extra statement costs nothing unless it contradicts an item or changes the action or a graded value.
- Pass: at least 9 of 12, with items 1, 2 and 3 each earned in full.

Items
1. Movement basis: delta_MCE for both structures (2 points, required)
   Earns: ASCE 7-22 12.12.3 with Eq. 12.8-17 (1.5R delta_e/Ie, plus delta_di where reported) for the garage and the office building.
   Accepted range (a center-of-mass value falls outside it; the location error is taken here and in items 2 and 4 deliberately, because it leads to an "adequate" bearing that would run off its plate): garage 1.71 to 2.05 in. at the bearing (1.73 without delta_di, 1.85 with it, up to about 2.0 with the joint 77 value or 100/30); office 3.84 in. R = 5 with delta_e scaled by 6/5 gives the same result and earns the item.
   Does not earn: a delta_DE (Cd) basis; R = 5 with the delta_e of the R = 6 model.
2. Combination and adequacy (2 points, required)
   Earns: the two delta_MCE values added as opposite-direction movements (absolute sum), and the 5.0 in. of travel found not adequate.
   Accepted range: required movement 5.50 to 6.35 in. each way (5.69 in.; 6.05 in. with the 0.36 in. thermal; 5.55 to 5.57 in. without delta_di; 5.84 in. with 100 percent EX plus 30 percent EY; about 5.8 in. with the joint 77 value).
   Does not earn: SRSS (4.26 in.); 5.40 in. from R = 5 with unscaled delta_e; the garage taken at the center of mass (4.92 to 5.04 in., or 5.28 to 5.40 in. with thermal).
3. Action (1 point, required)
   Earns: Revise and Resubmit (or Rejected), with the draft's No Exceptions Taken identified as wrong.
   Does not earn: Make Corrections Noted, or any action that lets the plates be fabricated as detailed.
4. Location of the garage displacement (1 point)
   Earns: the garage displacement taken at the bearing location because of the torsional response, not at the center of mass.
   Accepted range: 0.19 to 0.20 in. elastic (0.192 in. by rigid-body rotation along the east edge; 0.200 in. at joint 77).
   Does not earn: 0.12 in. at the center of mass.
5. Office displacement (1 point)
   Earns: the office building's 0.32 in. identified as an elastic, unamplified value that the calc used as is.
6. delta_di (1 point)
   Earns: delta_di at the bearing from Table 40.6A included in the garage displacement.
   Accepted range: 0.117 to 0.124 in.
7. Fix with a number (1 point)
   Earns: a stainless sheet length along the bridge, or another arrangement with enough travel each way.
   Accepted range: sheet 17.4 to 18.7 in. (17.4 in.; 18.1 in. with thermal), or another arrangement with at least 5.69 in. of travel each way (6.05 in. with thermal).
   Does not earn: a sheet shorter than 17.4 in. or travel below 5.69 in., whatever the response's own required movement.
8. Separation rule (1 point)
   Earns: the calc's SRSS per 12.12.2 identified as the building-separation rule, not the rule for a member spanning between structures, and draft comments 2 and 3 corrected.
9. Joint check (1 point)
   Earns: the 7 in. joint checked against the corrected movement and found adequate.
   Accepted range: the response's own required movement from item 2, within 5.50 to 6.35 in. (6.05 in. with thermal), against 7 in.
   Does not earn: a statement that the joint was not rechecked.
10. Review comments ready to send (1 point, deliverable)
   Earns: comments addressed to the delegated engineer that return the submittal Revise and Resubmit (or Rejected) and state each correction this key requires (delta_MCE at the bearing with delta_di, the absolute sum, the required movement, and the sheet length or the travel of the other arrangement), each with its number and code section.
   Does not earn: comments that keep No Exceptions Taken or accept the bearing; an offer to write comments; comments without numbers or code sections.
