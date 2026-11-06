Alex,

I've checked RFI-012 and Jo's draft and I agree with accepting it.

The end zone of B-3 frames into column C-3, so the contractor's use of f'c = 5,000 psi is reasonable. With #4 @ 10 in. (2 legs):
- Vc = 2 x 1.0 x sqrt(5,000) x 16 x 27.5 = 62.2 kips
- Vs = 0.40 x 60 x 27.5 / 10 = 66.0 kips
- phi Vn = 0.75 x (62.2 + 66.0) = 96.2 kips >= Vu = 94.0 kips, D/C 0.98.

Spacing limit: Vs <= 4 sqrt(f'c) bw d, so s,max = d/2 = 13.75 in.; 10 in. is fine, and Av = 0.40 in2 is well above Av,min. The largest spacing that works is about 10.4 in.

**Response to send on RFI-012:** ACCEPTED. Place the B-3 end-zone stirrups at #4 @ 10 in. (2 legs) within 6'-0" of grids C and D. All other requirements of S-201 remain.

```json
{"fc_beam_psi": 5000, "phiVn_proposed_kips": 96.2, "proposal_ok": true, "max_spacing_in": 10.46, "rfi_acceptable": true}
```
