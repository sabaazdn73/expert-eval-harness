Alex,

RFI-012 should go back Not Accepted, and Jo's draft (Accepted) should not be issued. The arithmetic in the RFI is right, but it uses the wrong concrete strength for the beam.

**1. Concrete strength.** B-3 is a Level 2 beam, so f'c = 4,000 psi (S-001 B1). The contractor used 5,000 psi because the end zone frames into column C-3, but 5,000 psi is the column and beam-column joint concrete, and S-001 B2 places it only within the column outline. The B-3 end zone is outside the column, so the check has to use 4,000 psi (S-001 D2 also requires this).

**2. Shear check of the proposal, #4 @ 10 in. (2 legs), at d from the grid C face** (ACI 318-19, phi = 0.75 per Table 21.2.1):
- Vc = 2 lambda sqrt(f'c) bw d = 2 x 1.0 x 63.25 x 16 x 27.5 = 55.66 kips (Table 22.5.5.1(a), valid because Av >= Av,min).
- Vs = Av fyt d / s = 0.40 x 60 x 27.5 / 10 = 66.00 kips (22.5.8.5.3).
- phi Vn = 0.75 x (55.66 + 66.00) = 91.24 kips < Vu = 94.0 kips (calc 4.3). D/C = 1.03. Not adequate.

**3. Largest spacing that works.** Vs,req = 94.0 / 0.75 - 55.66 = 69.68 kips, so s <= 0.40 x 60 x 27.5 / 69.68 = 9.47 in. #4 @ 9 in. gives phi Vn = 96.74 kips, D/C 0.97. With 5,000 psi the limit would have been 10.46 in., which is why the RFI looked acceptable.

**4. Detailing limits.** Vs = 66 to 73 kips <= 4 sqrt(f'c) bw d = 111.3 kips, so the maximum spacing is d/2 = 13.75 in. (Table 9.7.6.2.2); 9 in. meets it. Av,min at 9 in. = max(0.75 sqrt(f'c) bw s / fyt, 50 bw s / fyt) = 0.120 in2 <= 0.40 in2 (Table 9.6.3.4).

**5. The draft.** It checked the RFI's arithmetic only and did not check the material strength against S-001, so it accepted a design strength below Vu.

**Response to send on RFI-012:**

RFI-012, Beam B-3 stirrup spacing: NOT ACCEPTED as submitted.

The calculation uses f'c = 5,000 psi. Per S-001 B1 and B2, beam B-3 is 4,000 psi concrete; the 5,000 psi column concrete is placed only within the column outline. With f'c = 4,000 psi, #4 stirrups @ 10 in. give phi Vn = 91.2 kips < Vu = 94.0 kips at d from the grid C face (ACI 318-19 Table 22.5.5.1(a), 22.5.8.5.3). The largest permitted spacing is 9.47 in.

Acceptable alternative: #4 stirrups (2 legs) @ 9 in. maximum within 6'-0" of grids C and D (phi Vn = 96.7 kips), first stirrup 2 in. from the face. The scheduled #4 @ 6 in. remains acceptable. The middle zone #4 @ 12 in. is unchanged. Resubmit the end-zone layout if a spacing other than these is proposed.

```json
{"fc_beam_psi": 4000, "phiVn_proposed_kips": 91.24, "proposal_ok": false, "max_spacing_in": 9.47, "rfi_acceptable": false}
```
