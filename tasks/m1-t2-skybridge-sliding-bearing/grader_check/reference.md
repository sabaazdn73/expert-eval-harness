Rafael,

SB-7 should go back **Revise and Resubmit**. The draft's No Exceptions Taken can't go out. Once the movement is computed the way ASCE 7-22 12.12.3 requires, the bearing needs about 6.0 in. of travel each way, and the 16 in. sheet only gives 5.0 in. Plate fabrication is on hold pending our review, and it should stay on hold.

**What 12.12.3 requires**

The skybridge spans between the garage and the office building and sits on a sliding bearing at our end. Under 12.12.3, the gravity supports of a member spanning between structures are designed for the maximum relative displacement using delta_MCE (12.8.6), with the two structures moving in opposite directions and the displacements added as an absolute sum.

TSF-2611 used delta_DE (Cd) and combined the two buildings by SRSS "per 12.12.2". That section, Eq. 12.12-2, is the rule for the clear separation between adjacent buildings. It is not the rule for a member that bears on both of them.

**Garage displacement at the bearing**

The bearing is at x = 126'-0", y = 256'-6" (S-401). That is at the north end of the east edge, about as far from cores C-1 and C-2 as you can get. The garage has a Type 1 torsional irregularity, so the displacement must be taken at the bearing, not at the center of mass.

- TSF-2611 used 0.12 in., which is the joint 100 (CM) row of Table 40.6, EX.
- Along the east edge, Ux goes from 0.040 in. at the SE corner (joint 7) to 0.200 in. at the NE corner (joint 77). At y = 256.5 ft: delta_e = 0.040 + 0.160 x 256.5/270 = **0.192 in.**
- delta_di from Table 40.6A: 0.124 x 256.5/270 = **0.118 in.** The calc left this out. The model has semi-rigid decks and reports it separately.
- Garage delta_MCE (Eq. 12.8-17) = 1.5R delta_e/Ie + delta_di = 1.5 x 6 x 0.192/1.0 + 0.118 = **1.85 in.**

**Office building**

The Kestrel & Moore letter states that 0.32 in. E-W is the elastic displacement, not amplified. TSF-2611 used it as is.

- Office delta_MCE = 1.5 x 8 x 0.32/1.0 = **3.84 in.** (R = 8, special moment frames, Ie = 1.0)

**Required movement**

- Seismic, absolute sum: 1.85 + 3.84 = **5.69 in.** each way
- Thermal: the calc's 0.36 in. (66 ft, 6.5e-6/F, 70 F) is fine.
- Total: 5.69 + 0.36 = **6.05 in.** each way, thermal included
- Capacity: (16 - 6)/2 = **5.0 in.** each way

6.05/5.0 = 1.21 (1.14 on seismic alone). The bearing is **not adequate**. With no keeper bars or end stops, the pad would run off the stainless sheet in the MCE.

The stainless sheet needs to be at least 6 + 2 x 6.05 = **18.1 in.** along the bridge (17.4 in. on seismic alone). E1 is 1'-8" long and the sheet is seal welded all around to it (S-401 note 7). The delegated engineer has to show that the longer sheet, the seal weld and the bearing at full travel fit on E1 and corbel C-1. E1 may need to get longer, or the bearing arrangement may need to change.

**Joint**

The 7 in. joint against 6.05 in. is still adequate.

**What's right in the calc**

- Reaction D = 40 k, L = 36 k, which matches S-401 note 5
- Pad pressure 76/84 = 0.90 ksi
- The 5.0 in. travel geometry
- Thermal term

**On the draft**

- Comment 1 (travel exceeds movement, no keepers): wrong.
- Comment 2 (agrees with Table 40.6): wrong. 0.12 in. is the CM row, not the bearing.
- Comment 3 (SRSS per 12.12.2 plus thermal): wrong. 12.12.3 governs, with delta_MCE and an absolute sum.
- Comment 4: the joint conclusion holds against the corrected 6.05 in.
- Comment 5 (pad and reaction): right.
- No Exceptions Taken: wrong.

**Comments to Hollis Brandvold, P.E. (Tallgrass), Revise and Resubmit**

1. Bearing movement is governed by ASCE 7-22 12.12.3 (member spanning between structures), not 12.12.2. Use delta_MCE per 12.8.6.4, Eq. 12.8-17, for both structures. Assume they move in opposite directions and take the absolute sum. SRSS of delta_DE is not acceptable.
2. Garage: take delta_e at the bearing (x = 126 ft, y = 256.5 ft) from Calc 40 Table 40.6, case EX. The structure is torsionally irregular, and the 0.12 in. used is the center-of-mass value. delta_e = 0.192 in. Add delta_di = 0.118 in. from Table 40.6A. delta_MCE = 1.5(6)(0.192) + 0.118 = 1.85 in.
3. Office building: 0.32 in. is elastic per the Kestrel & Moore letter of 10/06/2026. delta_MCE = 1.5(8)(0.32)/1.0 = 3.84 in.
4. Required movement = 1.85 + 3.84 + 0.36 (thermal) = 6.05 in. each way, which exceeds the 5.0 in. available. Revise the bearing to provide at least 6.05 in. of travel each way, for example a stainless sheet of at least 18.1 in. along the bridge with the 6 in. pad, or another arrangement giving the same travel.
5. Show that the revised sheet, its seal weld and the pad at full travel fit on embed plate E1 and corbel C-1. Revise E1 if needed.
6. The 7 in. joint is adequate for 6.05 in. Confirm the joint cover plate accommodates the same movement.
7. Pad pressure and reactions are acceptable as submitted.
8. Bearing plate fabrication remains on hold until the revised calculation is reviewed.

```json
{
  "required_bearing_movement_in": 6.05,
  "movement_capacity_in": 5.0,
  "bearing_ok": false,
  "joint_ok": true,
  "submittal_action": "revise and resubmit"
}
```
