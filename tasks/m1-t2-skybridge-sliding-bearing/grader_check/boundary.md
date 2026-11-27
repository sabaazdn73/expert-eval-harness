Rafael,

I wouldn't sign the draft. SB-7 should go back **Revise and Resubmit**. No Exceptions Taken would release bearing plates that are too short for the movement this bearing has to take. The transmittal says plate fabrication is on hold pending our review, and it should stay that way.

**Basis**

The skybridge is a member spanning between two structures, carried on a sliding bearing at our corbel C-1. ASCE 7-22 12.12.3 requires its supports to be designed for the maximum relative displacement using delta_MCE (12.8.6), with the two structures assumed to move in opposite directions and the displacements added. TSF-2611 worked with design-level displacements, which is the Cd basis (delta_DE). That understates the movement the bearing has to take.

**Garage**

The bearing is at x = 126'-0", y = 256'-6" (S-401), near the NE corner of the plan, at the end away from the cores. The garage has a Type 1 torsional irregularity, so the east edge doesn't translate uniformly. The 0.12 in. used in TSF-2611 is the center-of-mass row (joint 100) of Calc 40 Table 40.6, not the displacement at the bearing. Draft comment 2 ("agrees with Table 40.6") repeats that mistake.

From Table 40.6, L2, case EX, Ux along the east edge runs from 0.040 in. (SE corner, joint 7) to 0.200 in. (NE corner, joint 77). At y = 256.5 ft:

- delta_e = 0.040 + 0.160 x 256.5/270 = **0.192 in.**
- delta_MCE = 1.5R delta_e/Ie = 1.5 x 6 x 0.192/1.0 = **1.73 in.** (Eq. 12.8-17, R = 6 building frame, special RC shear walls per S-001)

**Office building**

The Kestrel & Moore letter of 10/06/2026 gives 0.32 in. E-W at the bridge bearing and states that it is an elastic, unamplified value. TSF-2611 put the 0.32 in. into the movement as is, with no amplification at all.

- delta_MCE = 1.5 x 8 x 0.32/1.0 = **3.84 in.** (steel special moment frames, R = 8, Ie = 1.0)

**Movement and capacity**

- Seismic, opposite directions, absolute sum: 1.73 + 3.84 = **5.57 in.**
- Thermal from the calc: 0.36 in. (66 ft, 70 F)
- Required: 5.57 + 0.36 = **5.93 in.** each way, thermal included
- Available: (16 - 6)/2 = **5.0 in.** each way

5.93/5.0 = 1.19, so the bearing is **not adequate**. The detail has no keeper bars or end stops, so the pad would come off the end of the stainless sheet.

**Fix**

The stainless sheet along the bridge needs to be at least 6 + 2 x 5.93 = **17.9 in.**, call it 18 in., instead of 16 in. An equivalent arrangement giving at least 5.93 in. of travel each way would also work. They should check that the longer sheet still fits on embed plate E1 (1'-8") with the seal weld.

**Other items**

- The reaction (D 40 k, L 36 k, matching S-401 note 5) is fine.
- The pad pressure (0.90 ksi) is fine.
- The 5.0 in. travel geometry is fine.
- I have not rechecked the joint width or the transverse travel here, so draft comment 4 stands as the junior wrote it for now.
- Draft comment 1 (travel exceeds the movement, no keepers needed) is wrong given the numbers above.
- The No Exceptions Taken stamp has to change to Revise and Resubmit.

If you agree with the numbers, I'll turn this into the formal comment sheet for Tallgrass.

```json
{
  "required_bearing_movement_in": 5.93,
  "movement_capacity_in": 5.0,
  "bearing_ok": false,
  "joint_ok": true,
  "submittal_action": "revise and resubmit"
}
```
