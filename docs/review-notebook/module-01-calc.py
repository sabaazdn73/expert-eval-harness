"""Module 1, Load path and static equilibrium: every number in the text. Run: python3 module-01-calc.py"""
import math
R = {}
def r(k, v, nd=2):
    R[k] = round(v, nd); return v

# 1.1 equilibrium: 50 kN at 30 deg below horizontal, 2 m from A, span 6 m
P = 50; Px = P*math.cos(math.radians(30)); Py = P*math.sin(math.radians(30))
r('e11_Px', Px); r('e11_Py', Py)
By = Py*2/6; Ay = Py - By
r('e11_Ay', Ay); r('e11_By', By); r('e11_Ax', Px)

# 1.2 base example
slab = 0.2*25 + 0.5; wb = 0.3*0.45*25; wg = 0.4*0.6*25
wD = slab*3 + wb; wL = 2*3
Rb = wD*9/2; RbL = wL*9/2
Rg = (2*Rb*2 + wg*9)/2; RgL = 2*RbL*2/2
colD = 2*Rg + 2*2*Rb/2*1  # two girders + two column-line beams (each 2 x Rb from both sides? no)
# column-line beam: beam on column line spans 9 m, slab both sides -> reaction Rb; both sides of column -> 2 beams -> 2*Rb
colD = 2*Rg + 2*Rb; colL = 2*RgL + 2*RbL
r('e12_slab', slab); r('e12_wD', wD); r('e12_Rb', Rb); r('e12_Rg', Rg); r('e12_colD', colD, 1); r('e12_colL', colL, 1)
assert abs(colD - (81*slab + 27*wb + 9*wg)) < 0.01 and abs(colL - 162) < 1e-9

# 1.3 edge and corner (parapet 3 kN/m)
Rge = (2*Rb + (wg+3)*9)/2
edgeD = 2*Rge + Rb; edgeL = 2*27 + 27
wbe = slab*1.5 + wb + 3; Rbe = wbe*4.5
corD = Rge + Rbe; corL = 27 + 2*1.5*4.5
r('e13_Rge', Rge); r('e13_edgeD', edgeD); r('e13_corD', corD); r('e13_Rbe', Rbe)
assert abs(edgeD - (40.5*slab + 13.5*wb + 9*wg + 27)) < 0.01
assert abs(corD - (20.25*slab + 9*wb + 4.5*wg + 27)) < 0.01

# 1.4 continuity
w = wD; L = 9
r('e14_end2', 0.375*w*L); r('e14_mid2', 1.25*w*L); r('e14_end3', 0.4*w*L); r('e14_int3', 1.1*w*L)

# 1.6 two-way slab 6 x 9, w = 7 kPa
lx, ly, q0 = 6.0, 9.0, 7.0
q = q0*lx/2
Ws = q*lx/2; Wl = q*(ly - lx/2)
Ms = q*lx**2/12; a = lx/2; Ml = q*ly**2/8 - q*a**2/6
weqMs = q*2/3; weqMl = q*(1 - (lx/ly)**2/3)
weqVs = q/2; weqVl = q*(1 - lx/(2*ly))
r('e16_q', q); r('e16_Ws', Ws); r('e16_Wl', Wl); r('e16_Ms', Ms); r('e16_Ml', Ml, 1)
r('e16_weqMs', weqMs); r('e16_weqMl', weqMl); r('e16_weqVl', weqVl)
assert abs(2*Ws + 2*Wl - q0*lx*ly) < 1e-9
assert abs(weqMl*ly**2/8 - Ml) < 1e-9
oneway_long = q0*lx*ly/2
r('e16_oneway', oneway_long)
# practice: 8 x 8, 6 kPa
qp = 6*8/2; r('p16_q', qp); r('p16_W', qp*8/2); r('p16_R', qp*8/4); r('p16_M', qp*64/12)

# 1.7 flat plate 7.5 grid, 250 mm, SDL 1.5, L 2.5, col 500, d 210
sw = 0.25*25; D7 = 7.5*7.5*(sw + 1.5); L7 = 7.5*7.5*2.5
qu = 1.2*(sw + 1.5) + 1.6*2.5
bo_side = 0.5 + 0.21
Vu = qu*(7.5*7.5 - bo_side**2)
r('e17_D', D7); r('e17_L', L7); r('e17_qu', qu); r('e17_Acrit', bo_side**2, 4); r('e17_Vu', Vu, 1); r('e17_bo', 4*bo_side)

# 1.8 composite deck direction: bay 9x9, beams at 3 m, deck+concrete 4.0 kPa
g = 4.0
wbeam = g*3; Pbeam = wbeam*9/2; Pgird = 2*Pbeam
Mg_ok = Pgird*3; Mb_ok = wbeam*81/8
wg_wrong = g*9  # girder strip 4.5 m each side
Mg_wrong = wg_wrong*81/8
r('e18_wbeam', wbeam); r('e18_Pbeam', Pbeam); r('e18_Pgird', Pgird); r('e18_Mg_ok', Mg_ok); r('e18_Mb_ok', Mb_ok)
r('e18_wg_wrong', wg_wrong); r('e18_Mg_wrong', Mg_wrong)
# girder load total check: correct: 2 point loads x 54 kN = 108 + ... per girder from one bay side each: interior girder gets both bays
tot_ok = 2*Pgird; tot_wrong = wg_wrong*9
r('e18_tot_ok', tot_ok); r('e18_tot_wrong', tot_wrong)

# 1.9 opening: slab 5.5 kPa, beam 3.375 kN/m, base bay
Rtail = wD*3/2
Rhead = (Rtail + wb*6)/2
M6 = wD*81/8; M6new = M6 + Rhead*3
r('e19_Rtail', Rtail); r('e19_Rhead', Rhead); r('e19_M6', M6, 1); r('e19_M6new', M6new, 1); r('e19_inc', (M6new/M6 - 1)*100, 0)
net = -(9*slab) - 3*wb + 2*6*wb
r('e19_net', net, 3)
girder_change = (Rtail - Rb) + Rhead
r('e19_girder_change', girder_change)
assert abs(2*girder_change + 2*Rhead - net) < 0.01

# 1.10 cantilever: L 4, a 2, wb 5, wc 20, P 10
Lb, ac, wbk, wc, Pt = 4, 2, 5, 20, 10
RA = (wbk*Lb*Lb/2 - wc*ac*ac/2 - Pt*ac)/Lb
RB = wbk*Lb + wc*ac + Pt - RA
MB = -(wc*ac**2/2 + Pt*ac)
r('e110_RA', RA); r('e110_RB', RB); r('e110_MB', MB)
RA_trib = wbk*Lb/2
r('e110_RA_trib', RA_trib)

# 1.11 wall perpendicular to one-way slab span 3 m at midspan, 6 kN/m; equipment 30 kN at 2 m on 9 m beam
Mw = 6*3/4; Ms_udl = slab*9/8
r('e111_Mw', Mw); r('e111_Ms', Ms_udl); r('e111_inc', Mw/Ms_udl*100, 0)
Pe, ae = 30, 2.0
R1 = Pe*(9 - ae)/9; R2 = Pe*ae/9; Me = Pe*ae*(9 - ae)/9
r('e111_R1', R1); r('e111_R2', R2); r('e111_Me', Me)

# 1.12 torsion: spandrel slab reaction 1.5 m x 5.5 = 8.25 kN/m at 0.15 m; canopy 2 m x 3 kPa at 1.15 m
t1 = slab*1.5*0.15; T1 = t1*9/2
t2 = 2*3*1.15; T2 = t2*9/2
r('e112_t1', t1, 3); r('e112_T1', T1); r('e112_t2', t2); r('e112_T2', T2)

# 1.13 irregular grid: columns x 0,5,12; y 0,6,10; column (5,6)
A13 = (5/2 + 7/2)*(6/2 + 4/2)
r('e113_A', A13); r('e113_D', A13*7)
# wrong: full spans one side
r('e113_wrong', 7*6*7)

# 1.14 takedown: 4 garage levels 590.6/162 per level, column 0.5x0.5x3.2
colsw = 0.5*0.5*3.2*25
rows = []
cD = cL = 0
for lvl in range(4, 0, -1):
    cD += colD + colsw; cL += colL
    n = 5 - lvl
    red = 0.8 if n >= 2 else 1.0
    rows.append((lvl, n, round(cD + 1e-9, 1), round(cL, 1), round(cL*red, 1)))
R['e114_rows'] = rows; r('e114_colsw', colsw)

# 1.15 pile cap: 4 piles +-0.9, P 3000, My 450, Mx 270
Pp, My, Mx, s = 3000, 450, 270, 0.9
Sx2 = 4*s*s
dMy = My*s/Sx2; dMx = Mx*s/Sx2
piles = {(sx, sy): Pp/4 + sx*dMy + sy*dMx for sx in (1, -1) for sy in (1, -1)}
r('e115_avg', Pp/4); r('e115_dMy', dMy); r('e115_dMx', dMx)
R['e115_piles'] = {f"{sx:+d}{sy:+d}": round(v, 1) for (sx, sy), v in piles.items()}
assert abs(sum(piles.values()) - Pp) < 1e-9
# practice tension
r('p115_t', 1000/4 - 1500*0.9/(4*0.81), 1)

# 1.16 strip footing
Pf, B = 300, 2.0
for M, key in ((30, 'a'), (120, 'b')):
    e = M/Pf
    if e <= B/6:
        qmax = Pf/B*(1 + 6*e/B); qmin = Pf/B*(1 - 6*e/B); lc = B
    else:
        lc = 3*(B/2 - e); qmax = 2*Pf/lc; qmin = 0
    r(f'e116{key}_e', e, 3); r(f'e116{key}_qmax', qmax, 1); r(f'e116{key}_qmin', qmin, 1); r(f'e116{key}_lc', lc)

# 1.17 transfer girder L 12, P 2400 at 4, sw 0.8x1.8x25
Lt, Pt2, at = 12, 2400, 4
wsw = 0.8*1.8*25
RL = Pt2*(Lt - at)/Lt + wsw*Lt/2; RR = Pt2*at/Lt + wsw*Lt/2
Mmax = Pt2*at*(Lt - at)/Lt + wsw*at*(Lt - at)/2
r('e117_wsw', wsw); r('e117_RL', RL); r('e117_RR', RR); r('e117_M', Mmax)

# 1.18 transfer slab 8x8 bay, 1.2 m thick, P 1800
r('e118_sym', 1800/4); r('e118_sw', 1.2*25*64/4)
ecc = 2; dF = 1800*ecc*4/(4*16)
r('e118_near', 1800/4 + dF); r('e118_far', 1800/4 - dF)

# 1.19 hanging floors
r('e119_top', 900); r('e119_core', (900 + 200)/2)

# 1.20 discontinued wall
r('e120_C', 4800/5.4, 1)

# 1.21 wind
p, h, Bw = 1.2, 3.5, 30  # windward 0.75 + leeward 0.45
r('e121_windward_panel', 0.75*h/2)
r('e121_line', p*h); r('e121_floor', p*h*Bw); r('e121_roof', p*h/2*Bw); r('e121_panel', p*h/2)

# 1.22 seismic vertical distribution
wx = [3000, 3000, 3000, 2500]; hx = [3.5, 7, 10.5, 14]; V = 900
wh = [a*b for a, b in zip(wx, hx)]; S = sum(wh)
F = [V*x/S for x in wh]
shear = [sum(F[i:]) for i in range(4)]
R['e122_wh'] = wh; R['e122_F'] = [round(x, 1) for x in F]; R['e122_V'] = [round(x, 1) for x in shear]

# 1.23 diaphragm
Vd = 600; xs = [0, 12, 24]; k = [1, 1, 2]
flex = [Vd*6/24, Vd*12/24, Vd*6/24]
xr = sum(x*kk for x, kk in zip(xs, k))/sum(k); xm = 12
direct = [Vd*kk/sum(k) for kk in k]
J = sum(kk*(x - xr)**2 for x, kk in zip(xs, k))
T = Vd*(xr - xm)
tors = [T*kk*(xr - x)/J for x, kk in zip(xs, k)]
rigid = [d + t for d, t in zip(direct, tors)]
r('e123_xr', xr); r('e123_J', J); r('e123_T', T)
R['e123_flex'] = flex; R['e123_direct'] = direct; R['e123_tors'] = [round(x, 1) for x in tors]; R['e123_rigid'] = [round(x, 1) for x in rigid]
assert abs(sum(rigid) - Vd) < 1e-9
eacc = 0.05*24
r('e123_eacc', eacc)
for sgn, key in ((1, 'p'), (-1, 'm')):
    Tt = Vd*((xr - xm) + sgn*eacc)
    R[f'e123_rigid_{key}'] = [round(d + Tt*kk*(xr - x)/J, 1) for x, kk, d in zip(xs, k, direct)]

# 1.24 chords/collectors
wl, Ld, dd = 25, 24, 12
Md = wl*Ld**2/8; chord = Md/dd; vend = wl*Ld/2/dd
r('e124_M', Md); r('e124_chord', chord); r('e124_v', vend); r('e124_coll', vend*6); r('e124_vwall', wl*Ld/2/6)

# 1.25 overturning: wall takes half of 1.22 forces
Fw = [x/2 for x in F]
Mot = sum(f*hh for f, hh in zip(Fw, hx)); Vb = sum(Fw)
fD = 0.9 - 0.2*1.0  # ASCE 7 seismic minimum dead factor, SDS = 1.0
Tup = Mot/5.4 - fD*1200/2
r('e125_M', Mot, 1); r('e125_V', Vb); r('e125_T', Tup, 1); r('e125_mu', 0.5*fD*1200)
R['e125_Fw'] = [round(x, 2) for x in Fw]

# 1.26 diaphragm opening x 6..12, 4 m deep, at mid-depth
Vx = wl*Ld/2 - wl*9; Mx9 = wl*Ld/2*9 - wl*81/2
r('e126_V', Vx); r('e126_strip', Vx/2); r('e126_sec', Vx/2*3/4, 1); r('e126_M', Mx9); r('e126_chord', Mx9/dd, 1)

# 1.27 column removal: w 20, two spans 9
w27 = 20
r('e127_Msup', w27*81/8); r('e127_Mspan', 9*w27*81/128, 1); r('e127_Mafter', w27*324/8)
r('e127_Rend_before', 0.375*w27*9); r('e127_Rend_after', w27*18/2)

# 1.28 ties
gk, qk, psi = colD/81, 2.0, 0.6  # slab + beams + girders; psi2 for parking
Ti = max(0.8*(gk + psi*qk)*9*9, 75); Tp = max(0.4*(gk + psi*qk)*9*9, 75)
r('e128_Ti', Ti, 1); r('e128_Tp', Tp, 1)

# 1.29 shoring: new slab 5.0 + formwork 0.5 + construction live 1.5 shared by 2 slabs
new = 5.0 + 0.5 + 1.5
r('e129_new', new); r('e129_each', new/2); r('e129_total', 5.0 + new/2); r('e129_ratio', (5.0 + new/2)/5.0)

# 1.30 lever rule: girders at 2.5 m, barrier face 0.7 m outside exterior girder
S = 2.5; xw1 = -0.7 + 0.6; xw2 = xw1 + 1.8
f1 = (S - xw1)/S/2; f2 = (S - xw2)/S/2
r('e130_x1', xw1); r('e130_x2', xw2); r('e130_g', f1 + f2, 3); r('e130_DF', (f1 + f2)*1.2, 3)

# 1.31 braking
BR = max(0.25*325, 0.05*(325 + 9.3*60))*1.2  # one lane, m = 1.2
r('e131_BR', BR); r('e131_M', BR*8, 1)  # pinned fixed bearing: moment from the pier height only

if __name__ == "__main__":
    import json
    print(json.dumps(R, indent=0, default=str))

P = {}
P['1.1'] = (30*4.5/6, 30 - 30*4.5/6)
wD = 5.5*2.25 + 3.375; Rb = wD*9/2; Rg = (3*2*Rb + 54)/2; P['1.2'] = (wD, Rb, Rg, 2*Rg + 2*Rb, 81*5.5 + 36*3.375 + 54)
P['1.3'] = 195.75 - 27
w, L = 10, 6; P['1.4'] = (0.4*w*L, 1.1*w*L)
P['1.5'] = 10900/11500
P['1.7'] = (7.5*3.75*7.75, 7.5*3.75*2.5)
P['1.8'] = 4.0*2.25
P['1.9'] = 5.5*1.5*3/2
P['1.10'] = (40 + 20)/8
P['1.11'] = 6*1*2/3
t = 1.5*3*0.9; P['1.12'] = (t, t*9/2)
P['1.13'] = (3.5*5, 3.5*5*7)
P['1.14'] = (2442.5 + 648, 2442.5 + 518.4)
P['1.15'] = tuple(4200/6 + x*720*1.2/(4*1.44) for x in (1, 0, -1))
e = 60/300; P['1.16'] = (300/2.4*(1 + 6*e/2.4), 300/2.4*(1 - 6*e/2.4))
P['1.17'] = (1200 + 216, 2400*12/4 + 36*144/8)
P['1.18'] = tuple(450 + sx*225 + sy*225 for sx in (1, -1) for sy in (1, -1))
P['1.19'] = (1000, (1000 + 300)/2)
P['1.20'] = 4800/5.0
P['1.21'] = 1.0*4.0*24
wh = [3000*h for h in (3.5, 7, 10.5, 14)]; P['1.22'] = [900*x/sum(wh) for x in wh]
P['1.24'] = 25*3
P['1.25'] = 4612.5/5.4 - 0.7*1600/2
P['1.27'] = 20*15**2/8
P['1.28'] = 0.8*(590.625/81 + 0.6*2.0)*7.5*9
P['1.29'] = (7/3, 5 + 7/3, (5 + 7/3)/5)
P['1.30'] = ((3.1 + 1.3)/3/2, (3.1 + 1.3)/3/2*1.2)
P['1.31'] = 97.5*6
for k, v in P.items():
    print(k, v if not isinstance(v, (tuple, list)) else tuple(round(x, 3) for x in v), sep=': ')
