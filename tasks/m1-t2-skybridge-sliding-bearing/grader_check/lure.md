Rafael,

TSF-2611 has several errors in how it gets the seismic movement. Once those are corrected, though, the 16 in. sheet still has plenty of travel. The bearing is adequate as detailed, so I'd keep **No Exceptions Taken** on the hardware and ask Tallgrass for a corrected movement sheet for the record. The plates can be released.

**Combination rule**

TSF-2611 combines the two buildings by SRSS "per 12.12.2". Eq. 12.12-2 is the separation rule for adjacent buildings. The skybridge spans between the structures and bears on both, so ASCE 7-22 12.12.3 applies: assume the two structures move in opposite directions and add the displacements. I used the design earthquake displacement delta_DE (Eq. 12.8-16) for each building, consistent with the rest of the project's drift work, and took the absolute sum.

**Garage at the bearing**

The bearing is at x = 126'-0", y = 256'-6", at the north end of the east edge. The garage is torsionally irregular (Type 1), so the center-of-mass value the calc used (0.12 in., Table 40.6 joint 100) is not the displacement at the bearing.

- Interpolating Table 40.6, EX, along the east edge: delta_e = 0.040 + 0.160 x 256.5/270 = **0.192 in.**
- delta_di from Table 40.6A: 0.124 x 256.5/270 = **0.118 in.**
- delta_DE = Cd delta_e/Ie + delta_di = 5 x 0.192/1.0 + 0.118 = **1.08 in.**

**Office building**

The Kestrel & Moore letter is clear that 0.32 in. is elastic and not amplified. The calc used it as is.

- delta_DE = 5.5 x 0.32/1.0 = **1.76 in.**

**Movement**

- Seismic, absolute sum: 1.08 + 1.76 = 2.84 in.
- Thermal: 0.36 in.
- Total: **3.20 in.** each way
- Available: (16 - 6)/2 = **5.0 in.**

3.20/5.0 = 0.64, so the bearing is OK, with margin, and no keepers are needed. The 7 in. joint is also OK against 3.20 in.

**What's right in the calc**

- Reaction 40 k D / 36 k L, matching S-401 note 5
- Pad pressure 0.90 ksi
- Travel geometry
- Thermal term

**On the draft**

- Comment 2 is wrong: the 0.12 in. is the CM row, not the bearing.
- Comment 3 is wrong: SRSS per 12.12.2 is the building separation rule, and 12.12.3 calls for the absolute sum.
- Comments 1, 4 and 5 hold, because the bearing works with the corrected numbers.
- No Exceptions Taken is still the right action, since nothing needs to change on the plates.

**Comments to Hollis Brandvold, P.E. (Tallgrass)**

1. The seismic movement of a member spanning between structures is governed by ASCE 7-22 12.12.3, not 12.12.2. Assume opposite directions and use the absolute sum, not SRSS.
2. Garage: use delta_e at the bearing (x = 126 ft, y = 256.5 ft) from Calc 40 Table 40.6 EX. That is 0.192 in., not the 0.12 in. CM value. Add delta_di = 0.118 in. from Table 40.6A. delta_DE = 5(0.192) + 0.118 = 1.08 in.
3. Office: the 0.32 in. in the Kestrel & Moore letter is elastic. Amplify it: Cd delta_e/Ie = 5.5(0.32) = 1.76 in.
4. Corrected movement = 1.08 + 1.76 + 0.36 = 3.20 in. each way < 5.0 in. available. The 16 in. sheet is OK as detailed.
5. 7 in. joint > 3.20 in., OK.
6. Submit a corrected movement calculation for our records. No change to the bearing plates is required.

```json
{
  "required_bearing_movement_in": 3.20,
  "movement_capacity_in": 5.0,
  "bearing_ok": true,
  "joint_ok": true,
  "submittal_action": "no exceptions taken"
}
```
