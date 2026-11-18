"""Module 3, Structural analysis: every worked-example and practice number.

Hand methods are checked against frame2d (direct stiffness method) wherever a model can be built.
Run: python3 module-03-calc.py (needs frame2d.py in the same folder)  (prints every value; R holds them for the figures).
"""
import math
import numpy as np
from frame2d import Frame, rect

R = {}


def put(k, v, nd=2):
    R[k] = round(float(v), nd)
    return R[k]


# ---------------------------------------------------------------- shared data (Modules 1 and 2)
FC = 30.0                                  # MPa
E = 4700 * math.sqrt(FC) * 1000            # kN/m2, 19.2.2.1(b) in SI form: 25,743 MPa
put('E MPa', E / 1000, 0)
GIRDER = rect(0.40, 0.60)                  # A, Ig
COL = rect(0.50, 0.50)
BEAM = rect(0.30, 0.45)
H = 3.75                                   # storey height, m
SPAN = 9.0
WD, WL = 29.50, 11.52                      # factored dead and live, kN/m (Module 2, 2.7)
WU = WD + WL
put('wu', WU, 3)
F_COL, F_BEAM = 0.70, 0.35                 # Table 6.6.3.1.1(a)
CA, CI = COL[0], COL[1]
GA, GI = GIRDER[0], GIRDER[1]
put('Ig girder', GI, 6); put('Ig col', CI, 6)


def kc(Ic=CI * F_COL, h=H):
    return 4 * E * Ic / h


def kb(Ib=GI * F_BEAM, L=SPAN):
    return 4 * E * Ib / L


# ================================================================ Part A. Building the model
# 3.1 Supports: pinned, fixed and the real joint (one-bay subframe, columns above and below)
M_ss = WU * SPAN ** 2 / 8
FEM = WU * SPAN ** 2 / 12
put('3.1 pinned mid', M_ss); put('3.1 fixed end', FEM); put('3.1 fixed mid', M_ss - FEM)
# hand, symmetric: beam stiffness 2EI/L (both ends rotate equally and opposite)
kcols = 2 * kc()
kb_sym = 2 * E * GI * F_BEAM / SPAN
M_end_hand = FEM * kcols / (kcols + kb_sym)
put('3.1 real end hand', M_end_hand); put('3.1 real mid hand', M_ss - M_end_hand)
put('3.1 restraint ratio', kcols / (kcols + kb_sym), 3)


def one_bay(col_above=True, col_below=True, w=WU, fc=F_COL, fb=F_BEAM, release=False):
    f = Frame()
    a = f.node(0, 0); b = f.node(SPAN, 0)
    eb = f.elem(a, b, E, GA, GI * fb, rel_i=release, rel_j=release)
    f.udl(eb, -w)
    for n, x in ((a, 0.0), (b, SPAN)):
        if col_below:
            d = f.node(x, -H); f.elem(d, n, E, CA, CI * fc); f.support(d, 0, 0, 0)
        if col_above:
            u = f.node(x, H); f.elem(n, u, E, CA, CI * fc); f.support(u, 0, 0, 0)
    f.solve()
    return f, eb


f31, e31 = one_bay()
put('3.1 real end model', -f31.M_at(e31, 0)); put('3.1 real mid model', f31.M_at(e31, SPAN / 2))
# practice: roof, column below only
kroof = kc()
M_roof = FEM * kroof / (kroof + kb_sym)
put('3.1 practice roof end hand', M_roof); put('3.1 practice roof mid', M_ss - M_roof)
fr, er = one_bay(col_above=False)
put('3.1 practice roof end model', -fr.M_at(er, 0))

# 3.2 Cracked stiffness for analysis: one-bay portal, fixed bases, 100 kN at beam level
def portal(P=100.0, fc=F_COL, fb=F_BEAM, colsec=COL, base_fixed=True, rel=False, L=SPAN, h=H, gir=GIRDER):
    f = Frame()
    a = f.node(0, 0); b = f.node(0, h); c = f.node(L, h); d = f.node(L, 0)
    c1 = f.elem(a, b, E, colsec[0], colsec[1] * fc)
    bm = f.elem(b, c, E, gir[0], gir[1] * fb, rel_i=rel, rel_j=rel)
    c2 = f.elem(d, c, E, colsec[0], colsec[1] * fc)
    if base_fixed:
        f.support(a, 0, 0, 0); f.support(d, 0, 0, 0)
    else:
        f.support(a, 0, 0); f.support(d, 0, 0)
    f.load(b, fx=P)
    f.solve()
    return f, (a, b, c, d), (c1, bm, c2)


cases = {'Ig': (1.0, 1.0), 'ACI factored': (0.70, 0.35), 'EN 1998 half': (0.5, 0.5), 'ACI service': (0.98, 0.49)}
drift = {}
for k, (fc_, fb_) in cases.items():
    f, nd, el = portal(fc=fc_, fb=fb_)
    drift[k] = f.disp(nd[1])[0] * 1000
    put(f'3.2 drift {k} mm', drift[k], 3)
    put(f'3.2 base moment {k}', abs(f.end_forces(el[0])[2]))   # moment at base of left column
    put(f'3.2 top moment {k}', abs(f.end_forces(el[0])[5]))
for k in cases:
    put(f'3.2 ratio {k}', drift[k] / drift['Ig'], 3)
# hand: rigid beam would give P h^3 / (24 E Ic)
put('3.2 rigid beam Ig mm', 100 * H ** 3 / (24 * E * CI) * 1000, 3)
put('3.2 rigid beam ACI mm', 100 * H ** 3 / (24 * E * CI * 0.70) * 1000, 3)
put('3.2 practice service/factored', drift['ACI service'] / drift['ACI factored'], 4)

# 3.3 Face moments and rigid joint zones: two spans of 9 m on knife edges, 500 mm column at B
VB = 0.625 * WU * SPAN
MB_cl = WU * SPAN ** 2 / 8
c2 = 0.25
M_face = MB_cl - VB * c2 + WU * c2 ** 2 / 2
put('3.3 MB centreline', MB_cl); put('3.3 VB', VB); put('3.3 M face', M_face)
put('3.3 face reduction pct', (1 - M_face / MB_cl) * 100, 1)
F_sup = 2 * VB
put('3.3 EN dM', F_sup * 0.5 / 8); put('3.3 EN reduced', MB_cl - F_sup * 0.5 / 8)
put('3.3 EN 0.65 FEM', 0.65 * FEM)


def two_span(rigid=0.0, w=WU, I=GI * F_BEAM, settle=0.0, L=SPAN):
    f = Frame()
    a = f.node(0, 0)
    if rigid > 0:
        b1 = f.node(L - rigid, 0); b = f.node(L, 0); b2 = f.node(L + rigid, 0)
        c = f.node(2 * L, 0)
        e1 = f.elem(a, b1, E, GA, I); r1 = f.elem(b1, b, E, GA * 1e3, I * 1e4)
        r2 = f.elem(b, b2, E, GA * 1e3, I * 1e4); e2 = f.elem(b2, c, E, GA, I)
        for e in (e1, r1, r2, e2):
            f.udl(e, -w)
    else:
        b = f.node(L, 0); c = f.node(2 * L, 0)
        e1 = f.elem(a, b, E, GA, I); e2 = f.elem(b, c, E, GA, I)
        f.udl(e1, -w); f.udl(e2, -w)
    f.support(a, 0, 0); f.support(b, None, -settle); f.support(c, None, 0)
    f.solve()
    return f, e1


f33, e33 = two_span()
put('3.3 MB model', -f33.M_at(e33, SPAN)); put('3.3 face model', -f33.M_at(e33, SPAN - c2))
f33r, e33r = two_span(rigid=c2)
put('3.3 face rigid zone', -f33r.M_at(e33r, SPAN - c2))
put('3.3 RA cl', f33.reac(0, 1)); put('3.3 RA rigid', f33r.reac(0, 1))
# practice: 800 mm column
c2p = 0.40
put('3.3 practice face', MB_cl - VB * c2p + WU * c2p ** 2 / 2)
put('3.3 practice EN dM', F_sup * 0.8 / 8)

# 3.4 Effective flange width (secondary beam 300 x 450, slab 200, beams at 3 m, span 9 m, girders 400)
hf, bw, s, Lspan = 0.20, 0.30, 3.0, 9.0
sw = s - bw
ln = Lspan - 0.40
aci_side = min(8 * hf, sw / 2, ln / 8)
put('3.4 ACI each side', aci_side, 3); put('3.4 ACI bf', bw + 2 * aci_side, 3)
bi = sw / 2


def en_beff(l0, bi=bi, sides=2):
    beffi = min(0.2 * bi + 0.1 * l0, 0.2 * l0, bi)
    return beffi, bw + sides * beffi


for name, l0 in (('interior span', 0.7 * Lspan), ('end span', 0.85 * Lspan), ('support', 0.15 * 2 * Lspan)):
    bi_, bt = en_beff(l0)
    put(f'3.4 EN l0 {name}', l0, 3); put(f'3.4 EN beff,i {name}', bi_, 3); put(f'3.4 EN beff {name}', bt, 3)


def I_tee(bf, h=0.45, bw=bw, hf=hf):
    A1, A2 = bf * hf, bw * (h - hf)
    y1, y2 = h - hf / 2, (h - hf) / 2
    yb = (A1 * y1 + A2 * y2) / (A1 + A2)
    I = bf * hf ** 3 / 12 + A1 * (y1 - yb) ** 2 + bw * (h - hf) ** 3 / 12 + A2 * (y2 - yb) ** 2
    return I, yb


I_rect = BEAM[1]
I_T, yb_T = I_tee(bw + 2 * aci_side)
I_T_en, _ = I_tee(en_beff(0.7 * Lspan)[1])
put('3.4 I rect', I_rect * 1e6, 1); put('3.4 I T ACI', I_T * 1e6, 1); put('3.4 I T EN', I_T_en * 1e6, 1)
put('3.4 ratio ACI', I_T / I_rect, 3); put('3.4 ratio EN', I_T_en / I_rect, 3)
put('3.4 yb ACI', yb_T, 3)
# trap: full spacing as flange
I_T_full, _ = I_tee(s)
put('3.4 ratio full spacing', I_T_full / I_rect, 3)
# practice: edge beam (one side)
aci_one = min(6 * hf, sw / 2, ln / 12)
put('3.4 practice ACI one side', aci_one, 3); put('3.4 practice ACI bf', bw + aci_one, 3)
put('3.4 practice EN bf', en_beff(0.7 * Lspan, sides=1)[1], 3)

# 3.5 Interior column moment from live load on one side (subframe, ACI 6.3.1.2, 6.4.1)
M_unb = WL * SPAN ** 2 / 12
put('3.5 unbalanced', M_unb)
kcol, kbm = kc(), kb()
put('3.5 kc/E', kcol / E * 1e3, 4); put('3.5 kb/E', kbm / E * 1e3, 4)
M_col_hand = M_unb * kcol / (2 * kcol + 2 * kbm)
put('3.5 column moment hand', M_col_hand)


def interior_joint(col_above=True, wl_left=WL, wl_right=0.0):
    f = Frame()
    j = f.node(0, 0); l = f.node(-SPAN, 0); r = f.node(SPAN, 0)
    el = f.elem(l, j, E, GA, GI * F_BEAM); er = f.elem(j, r, E, GA, GI * F_BEAM)
    f.udl(el, -(WD + wl_left)); f.udl(er, -(WD + wl_right))
    f.support(l, 0, 0, 0); f.support(r, 0, 0, 0)
    d = f.node(0, -H); cb = f.elem(d, j, E, CA, CI * F_COL); f.support(d, 0, 0, 0)
    ca = None
    if col_above:
        u = f.node(0, H); ca = f.elem(j, u, E, CA, CI * F_COL); f.support(u, 0, 0, 0)
    f.solve()
    return f, cb, ca


f35, cb35, ca35 = interior_joint()
put('3.5 column below model', f35.end_forces(cb35)[5])   # moment at top of column below (at joint)
put('3.5 column above model', abs(f35.end_forces(ca35)[2]))
put('3.5 practice roof hand', M_unb * kcol / (kcol + 2 * kbm))
f35r, cb35r, _ = interior_joint(col_above=False)
put('3.5 practice roof model', f35r.end_forces(cb35r)[5])
# trap: column designed for axial only
put('3.5 trap axial only', 0.0)
put('3.5 beam end loaded', -f35.M_at(0, SPAN)); put('3.5 beam end unloaded', -f35.M_at(1, 0))

# ================================================================ Part B. Continuous beams
# 3.6 Moment distribution: spans 8, 10, 8 m, 40 kN/m, pinned ends, constant EI
w36 = 40.0
L1, L2 = 8.0, 10.0
FEM_BA = w36 * L1 ** 2 / 8          # propped: far end pinned
FEM_BC = w36 * L2 ** 2 / 12
k_BA, k_BC = 3 / L1, 4 / L2
DF_BA, DF_BC = k_BA / (k_BA + k_BC), k_BC / (k_BA + k_BC)
put('3.6 FEM BA', FEM_BA); put('3.6 FEM BC', FEM_BC)
put('3.6 DF BA', DF_BA, 4); put('3.6 DF BC', DF_BC, 4)
# Hardy Cross table (clockwise-positive member-end moments), joints B and C
m = {'BA': FEM_BA, 'BC': -FEM_BC, 'CB': FEM_BC, 'CD': -FEM_BA}
rows = [dict(m)]
for it in range(8):
    for J, (left, right), (dl, dr) in (('B', ('BA', 'BC'), (DF_BA, DF_BC)), ('C', ('CB', 'CD'), (DF_BC, DF_BA))):
        unb = m[left] + m[right]
        d1, d2 = -unb * dl, -unb * dr
        m[left] += d1; m[right] += d2
        # carry over half to the far end of the 10 m span only (end spans are pinned at the far end)
        if J == 'B':
            m['CB'] += d2 / 2
        else:
            m['BC'] += d1 / 2
    rows.append(dict(m))
R['3.6 cross rows'] = [{k: round(v, 2) for k, v in r.items()} for r in rows[:4]]
MB_cross = m['BA']
put('3.6 MB cross', MB_cross)
# symmetric shortcut: middle span stiffness 2EI/L
DF_sym = k_BA / (k_BA + 2 / L2)
MB_sym = FEM_BA - DF_sym * (FEM_BA - FEM_BC)
put('3.6 DF sym', DF_sym, 4); put('3.6 MB sym', MB_sym)


def three_span(L1=L1, L2=L2, w=(w36, w36, w36), EI=E * GI):
    f = Frame()
    xs = [0, L1, L1 + L2, 2 * L1 + L2]
    n = [f.node(x, 0) for x in xs]
    es = [f.elem(n[i], n[i + 1], E, GA, EI / E) for i in range(3)]
    for e, wi in zip(es, w):
        f.udl(e, -wi)
    f.support(n[0], 0, 0)
    for k in n[1:]:
        f.support(k, None, 0)
    f.solve()
    return f, es


f36, es36 = three_span()
put('3.6 MB model', -f36.M_at(es36[0], L1))
RA = w36 * L1 / 2 - MB_sym / L1
put('3.6 RA', RA); put('3.6 end span max', RA ** 2 / (2 * w36)); put('3.6 end span max x', RA / w36, 3)
put('3.6 mid span max', w36 * L2 ** 2 / 8 - MB_sym)
put('3.6 end span max model', f36.M_extremes(es36[0])[0]); put('3.6 mid span max model', f36.M_extremes(es36[1])[0])
# practice: middle span 12 m
L2p = 12.0
FEM_BCp = w36 * L2p ** 2 / 12
DF_symp = k_BA / (k_BA + 2 / L2p)
MBp = FEM_BA - DF_symp * (FEM_BA - FEM_BCp)
put('3.6 practice DF', DF_symp, 4); put('3.6 practice MB', MBp)
fp, ep = three_span(L2=L2p)
put('3.6 practice MB model', -fp.M_at(ep[0], L1))
put('3.6 practice mid span max', w36 * L2p ** 2 / 8 - MBp)
# trap: fixed-end moments taken as final
put('3.6 trap FEM as final', FEM_BC)
ft = Frame(); nt = [ft.node(x, 0) for x in (0, L1, L1 + L2, 2 * L1 + L2)]
et = [ft.elem(nt[i], nt[i + 1], E, GA, GI) for i in range(3)]
for e in et:
    ft.udl(e, -w36)
ft.support(nt[0], 0, 0, 0); ft.support(nt[1], None, 0); ft.support(nt[2], None, 0); ft.support(nt[3], 0, 0, 0); ft.solve()
put('3.6 trap fixed ends MB', -ft.M_at(et[0], L1)); put('3.6 trap fixed ends MA', -ft.M_at(et[0], 0))
put('3.6 trap fixed ends span', ft.M_extremes(et[0])[0])

# 3.7 ACI approximate coefficients against a subframe analysis with pattern loading
lnc = SPAN - 0.50
wl2 = WU * lnc ** 2
coef = {'ext neg (column) /16': wl2 / 16, 'end span pos /14': wl2 / 14, 'first int neg /10': wl2 / 10,
        'int span pos /16': wl2 / 16, 'other supports /11': wl2 / 11}
for k, v in coef.items():
    put('3.7 coef ' + k, v)
put('3.7 shear first int', 1.15 * WU * lnc / 2); put('3.7 shear other', WU * lnc / 2)
put('3.7 L/D', (WL / 1.6) / (WD / 1.2), 3)
NS = 4


def subframe(loaded, nspan=NS, wd=WD, wl=WL):
    f = Frame()
    xs = [i * SPAN for i in range(nspan + 1)]
    n = [f.node(x, 0) for x in xs]
    es = []
    for i in range(nspan):
        e = f.elem(n[i], n[i + 1], E, GA, GI * F_BEAM)
        f.udl(e, -(wd + (wl if loaded[i] else 0.0)))
        es.append(e)
    for k, x in zip(n, xs):
        d = f.node(x, -H); f.elem(d, k, E, CA, CI * F_COL); f.support(d, 0, 0, 0)
        u = f.node(x, H); f.elem(k, u, E, CA, CI * F_COL); f.support(u, 0, 0, 0)
    f.solve()
    return f, es


patterns = []
for mask in range(1, 2 ** NS):
    patterns.append([bool(mask >> i & 1) for i in range(NS)])
env = {'ext neg': 0, 'end pos': 0, 'first int neg': 0, 'int pos': 0, 'second int neg': 0}
for p in patterns:
    f, es = subframe(p)
    env['ext neg'] = max(env['ext neg'], -f.M_at(es[0], 0.25))
    env['end pos'] = max(env['end pos'], f.M_extremes(es[0])[0])
    env['first int neg'] = max(env['first int neg'], -f.M_at(es[0], SPAN - 0.25), -f.M_at(es[1], 0.25))
    env['int pos'] = max(env['int pos'], f.M_extremes(es[1])[0])
    env['second int neg'] = max(env['second int neg'], -f.M_at(es[1], SPAN - 0.25), -f.M_at(es[2], 0.25))
for k, v in env.items():
    put('3.7 analysis ' + k, v)
pairs = [('ext neg', 'ext neg (column) /16'), ('end pos', 'end span pos /14'), ('first int neg', 'first int neg /10'),
         ('int pos', 'int span pos /16'), ('second int neg', 'other supports /11')]
for a_, c_ in pairs:
    put('3.7 ratio ' + a_, coef[c_] / env[a_], 3)
# all spans loaded only (no pattern)
fall, esall = subframe([True] * NS)
put('3.7 all-loaded end pos', fall.M_extremes(esall[0])[0])


def subframe_gross(loaded):
    """The same subframe with gross sections for every member (3.7: the exterior coefficient check)."""
    f = Frame(); xs_ = [i * SPAN for i in range(NS + 1)]; n = [f.node(x, 0) for x in xs_]; es = []
    for i in range(NS):
        e = f.elem(n[i], n[i + 1], E, GA, GI); f.udl(e, -(WD + (WL if loaded[i] else 0.0))); es.append(e)
    for k, x in zip(n, xs_):
        d = f.node(x, -H); f.elem(d, k, E, CA, CI); f.support(d, 0, 0, 0)
        u = f.node(x, H); f.elem(k, u, E, CA, CI); f.support(u, 0, 0, 0)
    f.solve(); return f, es


env_g = 0
for p in patterns:
    fg_, eg_ = subframe_gross(p); env_g = max(env_g, -fg_.M_at(eg_[0], 0.25))
put('3.7 gross ext envelope', env_g)
put('3.7 col/beam stiffness ratio', 2 * kc() / kb(), 2)
put('3.7 all-loaded first int neg', -fall.M_at(esall[0], SPAN - 0.25))
# practice: two spans -> first interior /9
put('3.7 practice two-span /9', wl2 / 9)
env2 = 0
for p in ([True, True], [True, False], [False, True]):
    f, es = subframe(p, nspan=2)
    env2 = max(env2, -f.M_at(es[0], SPAN - 0.25))
put('3.7 practice two-span analysis', env2)

# 3.8 Moment redistribution (3.6 beam; section at B: 400 x 600, d = 540, f'c 30, fy 420)
b8, d8, fy = 400.0, 540.0, 420.0
fc_psi = FC * 145.0377
beta1 = 0.85 - 0.05 * (fc_psi - 4000) / 1000
put('3.8 beta1', beta1, 4)


def eps_t(As):
    a = As * fy / (0.85 * FC * b8)
    c = a / beta1
    return a, c, 0.003 * (d8 - c) / c


As1 = 4 * math.pi * 25 ** 2 / 4
a1, c1, et1 = eps_t(As1)
put('3.8 As', As1, 0); put('3.8 a', a1, 1); put('3.8 c', c1, 1); put('3.8 eps_t', et1, 5)
pct_aci = min(1000 * et1, 20.0)
put('3.8 ACI pct', pct_aci, 2)
MB_red = MB_sym * (1 - pct_aci / 100)
put('3.8 MB reduced', MB_red)
RA_r = w36 * L1 / 2 - MB_red / L1
put('3.8 end span max after', RA_r ** 2 / (2 * w36)); put('3.8 mid span after', w36 * L2 ** 2 / 8 - MB_red)
xu_d = 0.18
delta_en = max(0.44 + 1.25 * xu_d, 0.70)
put('3.8 EN delta', delta_en, 3); put('3.8 EN pct', (1 - delta_en) * 100, 1)
put('3.8 c/d', c1 / d8, 3)
# practice: 6 bars 25 mm
As2 = 6 * math.pi * 25 ** 2 / 4
a2, c2_, et2 = eps_t(As2)
put('3.8 practice As', As2, 0); put('3.8 practice c', c2_, 1); put('3.8 practice eps_t', et2, 5)
put('3.8 practice ACI pct', min(1000 * et2, 20.0) if et2 >= 0.0075 else 0.0, 2)
put('3.8 practice EN delta', max(0.44 + 1.25 * 0.27, 0.7), 4)
put('3.8 practice EN pct', (1 - max(0.44 + 1.25 * 0.27, 0.7)) * 100, 2)
# trap: redistributing ACI 6.5 coefficient moments
put('3.8 trap coef first int', coef['first int neg /10'])

# 3.9 Influence lines and moving loads: crane runway girder, two spans of 9 m, two wheels
P9, s9 = 112.5, 3.6           # wheel load with vertical impact (Module 2, 2.21, class D) and spacing (assumed)


def runway(loads):
    f = Frame()
    a = f.node(0, 0); b = f.node(SPAN, 0); c = f.node(2 * SPAN, 0)
    e1 = f.elem(a, b, E, GA, GI); e2 = f.elem(b, c, E, GA, GI)
    for P, x in loads:
        if 0 <= x < SPAN:
            f.point(e1, -P, x)
        elif SPAN <= x <= 2 * SPAN:
            f.point(e2, -P, x - SPAN)
    f.support(a, 0, 0); f.support(b, None, 0); f.support(c, None, 0)
    f.solve()
    return f, e1, e2


xs = np.linspace(0.0, 2 * SPAN, 721)
IL_RB, IL_MB, IL_M1 = [], [], []
for x in xs:
    f, e1, e2 = runway([(1.0, x)])
    IL_RB.append(f.reac(1, 1)); IL_MB.append(f.M_at(e1, SPAN)); IL_M1.append(f.M_at(e1, 0.4 * SPAN))
IL_RB, IL_MB, IL_M1 = map(np.array, (IL_RB, IL_MB, IL_M1))
R['3.9 IL'] = dict(x=xs[::12].round(3).tolist(), RB=IL_RB[::12].round(4).tolist(), MB=IL_MB[::12].round(4).tolist(),
                   M1=IL_M1[::12].round(4).tolist())
put('3.9 IL MB min', IL_MB.min(), 4); put('3.9 IL MB min x', xs[IL_MB.argmin()], 2)
# closed form for MB under a unit load at x in span 1: -x(L^2 - x^2)/(4L^2)
xm = SPAN / math.sqrt(3)
put('3.9 IL MB min closed', -xm * (SPAN ** 2 - xm ** 2) / (4 * SPAN ** 2), 4); put('3.9 IL MB min x closed', xm, 3)


def scan(fn, spacing):
    best = (-1e9, None)
    for x in np.linspace(-spacing, 2 * SPAN, 2 * int(2 * SPAN / 0.025) + 1):
        loads = [(P9, x), (P9, x + spacing)]
        loads = [(P, xx) for P, xx in loads if 0 <= xx <= 2 * SPAN]
        if not loads:
            continue
        v = fn(loads)
        if v > best[0]:
            best = (v, x)
    return best


def RB_of(loads):
    f, e1, e2 = runway(loads); return f.reac(1, 1)


def MBneg_of(loads):
    f, e1, e2 = runway(loads); return -f.M_at(e1, SPAN)


# influence-line superposition is exact (linear): use it for speed
def il_val(arr, x):
    return np.interp(x, xs, arr)


def best_two(arr, spacing, sign=1):
    best = (-1e9, None)
    for x in np.linspace(-spacing, 2 * SPAN, 4001):
        v = 0
        for xx in (x, x + spacing):
            if 0 <= xx <= 2 * SPAN:
                v += sign * P9 * il_val(arr, xx)
        if v > best[0]:
            best = (v, x)
    return best


RBmax, xRB = best_two(IL_RB, s9)
MBneg, xMB = best_two(IL_MB, s9, sign=-1)
M1pos, xM1 = best_two(IL_M1, s9)
put('3.9 RB max', RBmax); put('3.9 RB max first wheel', xRB, 2)
put('3.9 MB max neg', MBneg); put('3.9 MB first wheel', xMB, 2)
put('3.9 M1 max pos', M1pos); put('3.9 M1 first wheel', xM1, 2)
# check with the model at the found positions
f, e1, e2 = runway([(P9, xRB), (P9, xRB + s9)])
put('3.9 RB check', f.reac(1, 1))
# simple-span assumption for the reaction (wheels straddling B): each span simply supported
put('3.9 RB simple spans', P9 * (1 - (s9 / 2) / SPAN) * 2)
# practice: spacing 4.5 m
put('3.9 practice RB', best_two(IL_RB, 4.5)[0]); put('3.9 practice MB', best_two(IL_MB, 4.5, -1)[0])
put('3.9 practice MB first wheel', best_two(IL_MB, 4.5, -1)[1])
put('3.9 practice MB one span', max(sum(P9 * -il_val(IL_MB, xx) for xx in (x, x + 4.5)) for x in np.linspace(0, 4.5, 2001)))

# 3.10 Support settlement: two spans of 9 m, middle support settles 15 mm
D10 = 0.015
for name, I in (('gross', GI), ('cracked', GI * F_BEAM)):
    put(f'3.10 MB {name} hand', 3 * E * I * D10 / SPAN ** 2)
    f, e1 = two_span(w=0.0, I=I, settle=D10)
    put(f'3.10 MB {name} model', f.M_at(e1, SPAN))
    put(f'3.10 RB change {name}', 6 * E * I * D10 / SPAN ** 3)
put('3.10 gravity MB', MB_cl)
put('3.10 ratio cracked', R['3.10 MB cracked hand'] / MB_cl * 100, 1)
put('3.10 ratio gross', R['3.10 MB gross hand'] / MB_cl * 100, 1)
put('3.10 practice 25 mm cracked', 3 * E * GI * F_BEAM * 0.025 / SPAN ** 2)
# combined (gravity hogging at B reduced by settlement, sagging in spans increased)
f, e1 = two_span(settle=D10)
put('3.10 combined MB', -f.M_at(e1, SPAN)); put('3.10 combined span max', f.M_extremes(e1)[0])
f0, e0 = two_span()
put('3.10 gravity span max', f0.M_extremes(e0)[0])

# ================================================================ Part C. Frames under lateral load
F_roof, F_1 = 100.0, 60.0
XS = [0.0, 9.0, 18.0, 27.0]


def frame3x2(Fr=F_roof, F1=F_1, fc=F_COL, fb=F_BEAM, gir=GIRDER):
    f = Frame()
    base = [f.node(x, 0) for x in XS]
    l1 = [f.node(x, H) for x in XS]
    l2 = [f.node(x, 2 * H) for x in XS]
    cols1 = [f.elem(base[i], l1[i], E, CA, CI * fc) for i in range(4)]
    cols2 = [f.elem(l1[i], l2[i], E, CA, CI * fc) for i in range(4)]
    b1 = [f.elem(l1[i], l1[i + 1], E, gir[0], gir[1] * fb) for i in range(3)]
    b2 = [f.elem(l2[i], l2[i + 1], E, gir[0], gir[1] * fb) for i in range(3)]
    for n in base:
        f.support(n, 0, 0, 0)
    f.load(l2[0], fx=Fr); f.load(l1[0], fx=F1)
    f.solve()
    return f, dict(base=base, l1=l1, l2=l2, cols1=cols1, cols2=cols2, b1=b1, b2=b2)


V2, V1 = F_roof, F_roof + F_1
portal_res = {}
portal_res['top ext V'], portal_res['top int V'] = V2 / 6, V2 / 3
portal_res['bot ext V'], portal_res['bot int V'] = V1 / 6, V1 / 3
portal_res['top ext M'], portal_res['top int M'] = V2 / 6 * H / 2, V2 / 3 * H / 2
portal_res['bot ext M'], portal_res['bot int M'] = V1 / 6 * H / 2, V1 / 3 * H / 2
portal_res['roof beam M'] = portal_res['top ext M']
portal_res['l1 beam M'] = portal_res['top ext M'] + portal_res['bot ext M']
portal_res['roof beam V'] = 2 * portal_res['roof beam M'] / SPAN
portal_res['l1 beam V'] = 2 * portal_res['l1 beam M'] / SPAN
portal_res['ext axial top'] = portal_res['roof beam V']
portal_res['ext axial bot'] = portal_res['roof beam V'] + portal_res['l1 beam V']
for k, v in portal_res.items():
    put('3.11 portal ' + k, v, 3)
f311, g = frame3x2()
mod = {}
mod['bot ext V'] = -f311.end_forces(g['cols1'][0])[1]
mod['bot int V'] = -f311.end_forces(g['cols1'][1])[1]
mod['top ext V'] = -f311.end_forces(g['cols2'][0])[1]
mod['top int V'] = -f311.end_forces(g['cols2'][1])[1]
mod['bot ext base M'] = -f311.end_forces(g['cols1'][0])[2]
mod['bot int base M'] = -f311.end_forces(g['cols1'][1])[2]
mod['bot ext top M'] = f311.end_forces(g['cols1'][0])[5]
mod['l1 beam M ext'] = -f311.end_forces(g['b1'][0])[2]
mod['roof beam M ext'] = -f311.end_forces(g['b2'][0])[2]
mod['ext axial bot'] = f311.end_forces(g['cols1'][0])[0]
mod['ext axial bot right'] = f311.end_forces(g['cols1'][3])[0]
mod['int axial bot'] = f311.end_forces(g['cols1'][1])[0]
for k, v in mod.items():
    put('3.11 model ' + k, abs(v), 3)
fst, gst = frame3x2(fb=1000.0)
put('3.11 stiff beams ext V', abs(fst.end_forces(gst['cols1'][0])[1]), 3)
put('3.11 stiff beams int V', abs(fst.end_forces(gst['cols1'][1])[1]), 3)
for i, e in enumerate(g['cols1'][:2]):
    bm_, tm_ = abs(f311.end_forces(e)[2]), abs(f311.end_forces(e)[5])
    put(f'3.11 model inflection from base {i}', bm_ / (bm_ + tm_) * H, 3)
put('3.11 sum base shear model', abs(sum(f311.end_forces(e)[1] for e in g['cols1'])), 3)
# practice: 120 and 80 kN
put('3.11 practice bot int M', (120 + 80) / 3 * H / 2, 3); put('3.11 practice l1 beam M', (120 / 6 + 200 / 6) * H / 2, 3)

# 3.12 Cantilever method
xc = sum(XS) / 4
dists = [x - xc for x in XS]
sd2 = sum(d * d for d in dists)
put('3.12 sum d2', sd2)
M_top = F_roof * H / 2
M_bot = F_roof * (H + H / 2) + F_1 * H / 2
put('3.12 OTM top', M_top); put('3.12 OTM bot', M_bot)
for lvl, Mo in (('top', M_top), ('bot', M_bot)):
    put(f'3.12 {lvl} ext N', Mo * abs(dists[0]) / sd2, 3); put(f'3.12 {lvl} int N', Mo * abs(dists[1]) / sd2, 3)
# beam shears from axial changes at each joint (exterior)
put('3.12 roof beam V ext', R['3.12 top ext N'], 3)
put('3.12 l1 beam V ext', R['3.12 bot ext N'] - R['3.12 top ext N'], 3)
put('3.12 model ext N bot', abs(mod['ext axial bot']), 3); put('3.12 model int N bot', abs(mod['int axial bot']), 3)
OTM_base = F_roof * 2 * H + F_1 * H
put('3.12 OTM base', OTM_base)
M_bot_p = 120 * (H + H / 2) + 80 * H / 2
put('3.12 practice OTM', M_bot_p); put('3.12 practice ext N', M_bot_p * 13.5 / sd2, 3); put('3.12 practice int N', M_bot_p * 4.5 / sd2, 3)

# 3.13 Virtual work: canopy frame, column 4 m fixed at base, cantilever beam 3 m, tip load 50 kN
h13, a13, P13 = 4.0, 3.0, 50.0
EIb, EIc = E * GI, E * CI
d_beam = P13 * a13 ** 3 / (3 * EIb)
d_col = P13 * a13 * a13 * h13 / EIc
put('3.13 beam part mm', d_beam * 1000, 3); put('3.13 column part mm', d_col * 1000, 3)
put('3.13 total mm', (d_beam + d_col) * 1000, 3); put('3.13 column share pct', d_col / (d_beam + d_col) * 100, 1)
f = Frame()
n0 = f.node(0, 0); n1 = f.node(0, h13); n2 = f.node(a13, h13)
f.elem(n0, n1, E, CA, CI); f.elem(n1, n2, E, GA, GI)
f.support(n0, 0, 0, 0); f.load(n2, fy=-P13); f.solve()
put('3.13 model mm', -f.disp(n2)[1] * 1000, 3); put('3.13 model sway mm', f.disp(n1)[0] * 1000, 3)
put('3.13 sway hand mm', (P13 * a13) * h13 ** 2 / (2 * EIc) * 1000, 3)
# practice: 6 m column
d_col6 = P13 * a13 * a13 * 6.0 / EIc
put('3.13 practice total mm', (d_beam + d_col6) * 1000, 3); put('3.13 practice column share', d_col6 / (d_beam + d_col6) * 100, 1)

# 3.14 Storey stiffness: bottom storey of the frame alone, 160 kN, fixed bases


def one_storey(P=160.0, gir=GIRDER, fc=F_COL, fb=F_BEAM):
    f = Frame()
    base = [f.node(x, 0) for x in XS]; top = [f.node(x, H) for x in XS]
    for i in range(4):
        f.elem(base[i], top[i], E, CA, CI * fc); f.support(base[i], 0, 0, 0)
    for i in range(3):
        f.elem(top[i], top[i + 1], E, gir[0], gir[1] * fb)
    f.load(top[0], fx=P); f.solve()
    return f.disp(top[0])[0]


k_sb = 4 * 12 * E * CI * F_COL / H ** 3
put('3.14 k shear building', k_sb, 0); put('3.14 drift shear building mm', 160 / k_sb * 1000, 3)
d314 = one_storey()
put('3.14 drift model mm', d314 * 1000, 3); put('3.14 ratio', d314 / (160 / k_sb), 3)
put('3.14 k model', 160 / d314, 0)
d314b = one_storey(gir=rect(0.4, 0.8))
put('3.14 practice deep beam mm', d314b * 1000, 3); put('3.14 practice ratio', d314b / (160 / k_sb), 3)
put('3.14 drift ratio pct', d314 / H * 100, 4)


def one_storey_rigid_diaphragm(gir=GIRDER):
    f = Frame()
    base = [f.node(x, 0) for x in XS]; top = [f.node(x, H) for x in XS]
    for i in range(4):
        f.elem(base[i], top[i], E, CA, CI * F_COL); f.support(base[i], 0, 0, 0)
    for i in range(3):
        f.elem(top[i], top[i + 1], E, gir[0] * 1e4, gir[1] * F_BEAM)
    f.load(top[0], fx=160.0); f.solve()
    return f.disp(top[0])[0]


put('3.14 rigid diaphragm mm', one_storey_rigid_diaphragm() * 1000, 3)
put('3.14 rigid diaphragm practice mm', one_storey_rigid_diaphragm(rect(0.4, 0.8)) * 1000, 3)

# ================================================================ Part D. Slabs
# 3.15 Direct design method (ACI 318-14 8.10; permitted by ACI 318-19 6.2.4.1)
qu, l1, l2, cs = 13.3, 7.5, 7.5, 0.5
lnd = l1 - cs
Mo = qu * l2 * lnd ** 2 / 8
put('3.15 ln', lnd); put('3.15 Mo', Mo)
dd = {'int neg': 0.65, 'int pos': 0.35, 'end ext neg': 0.26, 'end pos': 0.52, 'end int neg': 0.70}
for k, v in dd.items():
    put('3.15 ' + k, v * Mo, 4)
cs_share = {'int neg': 0.75, 'int pos': 0.60, 'end ext neg': 1.00, 'end pos': 0.60, 'end int neg': 0.75}
for k, v in cs_share.items():
    put('3.15 CS ' + k, v * dd[k] * Mo, 4); put('3.15 MS ' + k, (1 - v) * dd[k] * Mo, 4)
put('3.15 column strip width', 2 * min(l1, l2) / 4)
put('3.15 CS int neg per m', 0.75 * 0.65 * Mo / (min(l1, l2) / 2))
put('3.15 trap Mo with centre span', qu * l2 * l1 ** 2 / 8); put('3.15 trap pct', (l1 ** 2 / lnd ** 2 - 1) * 100, 1)
put('3.15 L/D', 2.5 / 7.75, 3)
# practice: 9 x 7.5 m panel, span 9 m in the direction considered, l2 = 7.5
lnp = 9.0 - 0.5
Mop = qu * 7.5 * lnp ** 2 / 8
put('3.15 practice Mo', Mop); put('3.15 practice int neg CS', 0.65 * 0.75 * Mop); put('3.15 practice int pos CS', 0.35 * 0.60 * Mop)

# 3.16 Live load arrangement in two-way slabs (ACI 6.4.3) with an equivalent strip check
D16, L16 = 7.75, 7.2
put('3.16 L/D storage', L16 / D16, 3)
w_all = (1.2 * D16 + 1.6 * L16)
w_pat = (1.2 * D16 + 0.75 * 1.6 * L16)
w_dead = 1.2 * D16
put('3.16 all panels', w_all); put('3.16 pattern loaded', w_pat); put('3.16 pattern unloaded', w_dead)


def strip(ws, L=7.5, b=7.5):
    f = Frame()
    n = [f.node(i * L, 0) for i in range(4)]
    es = [f.elem(n[i], n[i + 1], E, 0.25 * b, b * 0.25 ** 3 / 12) for i in range(3)]
    for e, w in zip(es, ws):
        f.udl(e, -w * b)
    f.support(n[0], 0, 0)
    for k in n[1:]:
        f.support(k, None, 0)
    f.solve()
    return f, es


fa, ea = strip([w_all] * 3)
fp, ep = strip([w_pat, w_dead, w_pat])
fp2, ep2 = strip([w_dead, w_pat, w_dead])
fn, en = strip([w_pat, w_pat, w_dead])
put('3.16 all end pos', fa.M_extremes(ea[0])[0]); put('3.16 pattern end pos', fp.M_extremes(ep[0])[0])
put('3.16 all mid pos', fa.M_extremes(ea[1])[0]); put('3.16 pattern mid pos', fp2.M_extremes(ep2[1])[0])
put('3.16 all int neg', -fa.M_at(ea[0], 7.5)); put('3.16 pattern int neg', -fn.M_at(en[0], 7.5))
# office case of 3.15
put('3.16 office L/D', 2.5 / 7.75, 3)
put('3.16 practice L/D', 5.0 / 7.75, 3); put('3.16 practice all panels', 1.2 * 7.75 + 1.6 * 5.0)

# 3.17 Reading plate results: simply supported square plate (Navier), a = 7.5 m, q = 13.3, nu = 0.2
a17, q17, nu = 7.5, 13.3, 0.2


def navier_m(x, y, a=a17, q=q17, nu=nu, N=79):
    mx = my = 0.0
    for m_ in range(1, N + 1, 2):
        for n_ in range(1, N + 1, 2):
            amn = 16 * q / (math.pi ** 6 * m_ * n_ * ((m_ / a) ** 2 + (n_ / a) ** 2) ** 2)
            s = math.sin(m_ * math.pi * x / a) * math.sin(n_ * math.pi * y / a)
            # w = sum amn/D sin sin; mx = D (w,xx + nu w,yy) with sign so that sagging is positive
            mx += amn * math.pi ** 2 * ((m_ / a) ** 2 + nu * (n_ / a) ** 2) * s
            my += amn * math.pi ** 2 * ((n_ / a) ** 2 + nu * (m_ / a) ** 2) * s
    return mx, my


ys = np.linspace(0, a17, 61)
mx_line = np.array([navier_m(a17 / 2, y)[0] for y in ys])
R['3.17 mx line'] = dict(y=ys.round(3).tolist(), mx=mx_line.round(3).tolist())
peak = mx_line.max()
put('3.17 peak', peak, 3); put('3.17 peak coef', peak / (q17 * a17 ** 2), 5)
tot = np.trapezoid(mx_line, ys)
put('3.17 total across', tot, 2); put('3.17 average full width', tot / a17, 3)
mid = (ys >= a17 / 4 - 1e-9) & (ys <= 3 * a17 / 4 + 1e-9)
tot_mid = np.trapezoid(mx_line[mid], ys[mid])
put('3.17 middle half total', tot_mid, 2); put('3.17 middle half average', tot_mid / (a17 / 2), 3)
put('3.17 peak times width', peak * a17, 2); put('3.17 overestimate pct', (peak * a17 / tot - 1) * 100, 1)
put('3.17 one-way strip wL2/8', q17 * a17 ** 2 / 8, 3)
put('3.17 practice middle share pct', tot_mid / tot * 100, 1)

# ================================================================ Part E. Checking software output
# 3.18 Reactions under lateral load: the 3.11 model
Vb = [-f311.end_forces(e)[1] for e in g['cols1']]
Nb = [f311.end_forces(e)[0] for e in g['cols1']]
Mb = [-f311.end_forces(e)[2] for e in g['cols1']]
for i in range(4):
    put(f'3.18 base V{i + 1}', Vb[i], 3); put(f'3.18 base N{i + 1}', Nb[i], 3); put(f'3.18 base M{i + 1}', Mb[i], 3)
put('3.18 sum V', abs(sum(Vb)), 3); put('3.18 sum N', sum(Nb), 4)
# overturning about the base of the left column: applied 975 = sum(N x) resisting + sum(M base)
couple = sum(-Nb[i] * XS[i] for i in range(4))
put('3.18 axial couple', abs(couple), 2); put('3.18 sum base M', abs(sum(Mb)), 2); put('3.18 total resisting', abs(couple + sum(Mb)), 2)
put('3.18 axial share pct', abs(couple) / OTM_base * 100, 1)
put('3.18 trap axial if all OTM', OTM_base * 13.5 / 405, 2)
put('3.18 OTM', OTM_base)
# trap: a load lost on an unconnected node -> sum V 100 instead of 160
put('3.18 trap sum V', F_roof)
put('3.18 practice OTM', 120 * 2 * H + 80 * H)

# 3.19 Local axes: one-bay portal, columns 300 x 700, strong axis in the frame against turned 90 degrees
strong = rect(0.3, 0.7)
weak = (0.21, 0.7 * 0.3 ** 3 / 12)
fs, nds, els = portal(colsec=strong)
fw, ndw, elw = portal(colsec=weak)
put('3.19 I strong', strong[1] * 1e6, 1); put('3.19 I weak', weak[1] * 1e6, 1); put('3.19 I ratio', strong[1] / weak[1], 3)
put('3.19 drift strong mm', fs.disp(nds[1])[0] * 1000, 3); put('3.19 drift weak mm', fw.disp(ndw[1])[0] * 1000, 3)
put('3.19 drift ratio', fw.disp(ndw[1])[0] / fs.disp(nds[1])[0], 3)
put('3.19 base M strong', abs(fs.end_forces(els[0])[2])); put('3.19 base M weak', abs(fw.end_forces(elw[0])[2]))
put('3.19 top M strong', abs(fs.end_forces(els[0])[5])); put('3.19 top M weak', abs(fw.end_forces(elw[0])[5]))
ps_, pw_ = rect(0.4, 0.6), (0.24, 0.6 * 0.4 ** 3 / 12)
f1_, n1_, _ = portal(colsec=ps_); f2_, n2_, _ = portal(colsec=pw_)
put('3.19 practice I ratio', ps_[1] / pw_[1], 3); put('3.19 practice drift ratio', f2_.disp(n2_[1])[0] / f1_.disp(n1_[1])[0], 3)

# 3.20 Stiffness modifiers applied twice: the 3 x 2 frame, roof drift
f_ok, g_ok = frame3x2()
f_tw, g_tw = frame3x2(fc=0.70 * 0.70, fb=0.35 * 0.35)
f_bt, g_bt = frame3x2(fb=0.35 * 0.35)
d_ok = f_ok.disp(g_ok['l2'][0])[0]; d_tw = f_tw.disp(g_tw['l2'][0])[0]; d_bt = f_bt.disp(g_bt['l2'][0])[0]
put('3.20 roof drift ok mm', d_ok * 1000, 3); put('3.20 roof drift twice mm', d_tw * 1000, 3)
put('3.20 ratio twice', d_tw / d_ok, 3)
put('3.20 roof drift beams twice mm', d_bt * 1000, 3); put('3.20 ratio beams twice', d_bt / d_ok, 3)
put('3.20 col base M ok', abs(f_ok.end_forces(g_ok['cols1'][1])[2])); put('3.20 col base M beams twice', abs(f_bt.end_forces(g_bt['cols1'][1])[2]))
put('3.20 beam l1 M ok', abs(f_ok.end_forces(g_ok['b1'][0])[2])); put('3.20 beam l1 M beams twice', abs(f_bt.end_forces(g_bt['b1'][0])[2]))
put('3.20 col base M twice', abs(f_tw.end_forces(g_tw['cols1'][1])[2])); put('3.20 beam l1 M twice', abs(f_tw.end_forces(g_tw['b1'][0])[2]))
for tag, ff, gg in (('ok', f_ok, g_ok), ('beams twice', f_bt, g_bt)):
    put(f'3.20 col top ext {tag}', abs(ff.end_forces(gg['cols1'][0])[5])); put(f'3.20 col top int {tag}', abs(ff.end_forces(gg['cols1'][1])[5]))
    put(f'3.20 col base ext {tag}', abs(ff.end_forces(gg['cols1'][0])[2]))

# 3.21 End releases and mechanisms
fr1, er1 = one_bay(release=True)
put('3.21 released mid', fr1.M_at(er1, SPAN / 2)); put('3.21 released col M', abs(fr1.end_forces(1)[5]))
put('3.21 continuous mid', R['3.1 real mid model'])
try:
    fm, _, _ = portal(base_fixed=False, rel=True)
    put('3.21 mechanism cond', math.log10(fm.cond), 1)
    R['3.21 mechanism'] = 'solved (ill-conditioned)'
except np.linalg.LinAlgError:
    R['3.21 mechanism'] = 'singular matrix'
fpin, ndp, elp = portal(base_fixed=False)
put('3.21 pinned base drift mm', fpin.disp(ndp[1])[0] * 1000, 3)
ffix, ndf, elf = portal()
put('3.21 fixed base drift mm', ffix.disp(ndf[1])[0] * 1000, 3)
frel, ndr, _ = portal(rel=True)
put('3.21 practice released fixed-base drift mm', frel.disp(ndr[1])[0] * 1000, 3)
put('3.21 practice hand mm', 100 * H ** 3 / (2 * 3 * E * CI * F_COL) * 1000, 3)

# 3.22 Load direction and projection: rafter 10 m on plan at 30 degrees, frames at 6 m
th = math.radians(30)
plan, spacing, snow, sw_len = 10.0, 6.0, 0.84, 3.0
Ls = plan / math.cos(th)
w_plan = snow * spacing
put('3.22 slope length', Ls, 3); put('3.22 snow per plan m', w_plan, 3); put('3.22 snow total', w_plan * plan, 2)
put('3.22 snow wrong total', w_plan * Ls, 2); put('3.22 snow wrong pct', (Ls / plan - 1) * 100, 1)
put('3.22 self weight total', sw_len * Ls, 2); put('3.22 self weight wrong total', sw_len * plan, 2)
put('3.22 self weight wrong pct', (plan / Ls - 1) * 100, 1)
put('3.22 snow per slope m', w_plan * math.cos(th), 3)
# practice: 45 degrees
put('3.22 practice pct', (1 / math.cos(math.radians(45)) - 1) * 100, 1)

# 3.23 Hand check against the model: summary of the comparisons above
cmp = {
    '3.6 moment distribution MB': (R['3.6 MB sym'], R['3.6 MB model']),
    '3.1 joint end moment': (R['3.1 real end hand'], R['3.1 real end model']),
    '3.5 column moment': (R['3.5 column moment hand'], R['3.5 column below model']),
    '3.11 portal base M interior': (R['3.11 portal bot int M'], R['3.11 model bot int base M']),
    '3.11 portal base M exterior': (R['3.11 portal bot ext M'], R['3.11 model bot ext base M']),
    '3.11 portal level-1 beam M': (R['3.11 portal l1 beam M'], R['3.11 model l1 beam M ext']),
    '3.12 cantilever exterior N': (R['3.12 bot ext N'], R['3.12 model ext N bot']),
    '3.14 shear-building drift': (R['3.14 drift shear building mm'], R['3.14 drift model mm']),
    '3.7 ACI first interior support': (R['3.7 coef first int neg /10'], R['3.7 analysis first int neg']),
}
for k, (h_, m_) in cmp.items():
    put('3.23 ' + k + ' diff pct', (h_ / m_ - 1) * 100, 1)
R['3.23 table'] = {k: (round(h_, 2), round(m_, 2), round((h_ / m_ - 1) * 100, 1)) for k, (h_, m_) in cmp.items()}

if __name__ == '__main__':
    for k, v in R.items():
        print(f'{k}: {v}')
