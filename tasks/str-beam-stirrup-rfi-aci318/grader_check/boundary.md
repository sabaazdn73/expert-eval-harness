Alex,

RFI-012 can't be accepted, and Jo's draft should not go out.

The contractor used f'c = 5,000 psi, but that is the column and joint concrete, which S-001 B2 places only inside the column outline. Beam B-3 is 4,000 psi (S-001 B1). Jo's draft checked the arithmetic but not the concrete strength against the general notes.

With 4,000 psi and #4 @ 10 in.: Vc = 2 x 63.25 x 16 x 27.5 = 55.66 kips, Vs = 0.40 x 60 x 27.5 / 10 = 66.0 kips, phi Vn = 0.75 x 121.66 = 91.24 kips < Vu = 94.0 kips. The proposal does not work.

**Response to send on RFI-012:** NOT ACCEPTED. Per S-001 B1 and B2, beam B-3 is 4,000 psi concrete; with it, #4 @ 10 in. gives phi Vn = 91.2 kips < Vu = 94.0 kips (ACI 318-19 Table 22.5.5.1(a), 22.5.8.5.3). Keep the end-zone stirrups at #4 @ 6 in. as scheduled on S-201.

```json
{"fc_beam_psi": 4000, "phiVn_proposed_kips": 91.24, "proposal_ok": false, "max_spacing_in": 6, "rfi_acceptable": false}
```
