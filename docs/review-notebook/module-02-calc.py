"""Module 2, Loads and load combinations: every worked-example and practice number.

ASCE 7-22 is used for the US side, the Eurocodes (recommended values, check the National Annex)
for the European side. Run: python3 module-02-calc.py  (prints every value).
"""
import math

R = {}


def put(k, v, nd=2):
    R[k] = round(v, nd)
    return R[k]


# ---------------------------------------------------------------- building used across the module
GRID = 9.0                       # m, column grid
PLAN_B, PLAN_L = 36.0, 27.0      # m, 4 x 3 bays
AREA = PLAN_B * PLAN_L           # 972 m2
H_ST = 3.75                      # m storey height, 4 storeys, roof at 15 m
LEVELS = [3.75, 7.5, 11.25, 15.0]
N_COL = 5 * 4                    # 20 columns
GAMMA_C = 25.0                   # kN/m3 reinforced concrete

# ---------------------------------------------------------------- Part A. Dead loads
# 2.1 floor build-up
slab = 0.20 * GAMMA_C            # 5.00
screed = 0.06 * 22.0             # 1.32 (22 kN/m3 assumed)
tiles = 0.25
ceil = 0.50                      # ceiling + services
put('2.1 slab', slab); put('2.1 screed', screed)
sdl = screed + tiles + ceil
put('2.1 SDL', sdl); slab_level = slab + sdl; put('2.1 slab level', slab_level)
beam_web = 0.30 * 0.45 * GAMMA_C           # 3.375 kN/m every 3 m
girder_web = 0.40 * 0.60 * GAMMA_C         # 6.0 kN/m every 9 m
beams_avg = beam_web / 3.0 + girder_web / 9.0
put('2.1 beams avg', beams_avg, 3)
floor_D = slab_level + beams_avg
put('2.1 floor D', floor_D, 3)
col_storey = 0.5 * 0.5 * H_ST * GAMMA_C    # 23.44 kN
put('2.1 column per storey', col_storey)
# practice: 250 mm slab, 75 mm screed
p21 = 0.25 * GAMMA_C + 0.075 * 22.0 + tiles + ceil
put('2.1 practice', p21)
# trap: 24 instead of 25 and no screed
put('2.1 trap low', 0.2 * 24 + tiles + ceil)

# 2.2 partitions
put('2.2 ASCE partition', 0.72)
put('2.2 EN light 1.6 kN/m', 0.8)           # <= 2.0 kN/m class
wall_line = 3.5 * 0.15 * 18.0               # heavy masonry wall 9.45 kN/m
put('2.2 heavy wall', wall_line)
put('2.2 EN office imposed with partitions', 3.0 + 0.8)
p22_wall = 2.8 * 0.10 * 14.0                 # 3.92 kN/m > 3.0 -> line load
put('2.2 practice wall', p22_wall)

# 2.3 green roof and tank
sub_sat, sub_dry = 0.25 * 18.0, 0.25 * 11.0  # substrate 250 mm, 18 / 11 kN/m3 (supplier values, assumed)
drain_sat, drain_dry = 0.30, 0.10
green_sat = sub_sat + drain_sat; green_dry = sub_dry + drain_dry
put('2.3 green sat', green_sat); put('2.3 green dry', green_dry)
roof_struct = 1.0                             # light steel-deck roof with insulation, kN/m2 (example)
up_net = 3.8                                  # strength-level net wind uplift on the roof corner zone, kN/m2 (given)
chk_dry = 0.9 * (roof_struct + green_dry) - up_net
chk_sat = 0.9 * (roof_struct + green_sat) - up_net
put('2.3 uplift check dry', chk_dry); put('2.3 uplift check sat', chk_sat)
tank_full = 10 * 9.81 + 8.0; tank_empty = 8.0
put('2.3 tank full', tank_full, 1); put('2.3 tank empty', tank_empty, 1)

# ---------------------------------------------------------------- Part B. Live loads
OFFICE, CORR, GARAGE = 2.40, 3.83, 1.92     # kN/m2, ASCE 7-22 Table 4.3-1
# 2.4 beam with office on one side and corridor on the other, tributary 3 m
w_mixed = 1.5 * OFFICE + 1.5 * CORR
put('2.4 mixed', w_mixed, 3); put('2.4 office only', 3 * OFFICE)
put('2.4 increase %', (w_mixed / (3 * OFFICE) - 1) * 100, 1)
put('2.4 practice', 2.0 * OFFICE + 1.0 * CORR)


def llr(Lo, kll, at, floors):
    f = 0.25 + 4.57 / math.sqrt(kll * at)
    fmin = 0.5 if floors == 1 else 0.4
    if kll * at < 37.16:
        return 1.0
    return max(min(f, 1.0), fmin)


# 2.5 interior column, 9 x 9, office
f1 = llr(OFFICE, 4, 81, 1); put('2.5 f one floor raw', 0.25 + 4.57 / math.sqrt(324), 4); put('2.5 f one floor', f1, 4)
put('2.5 L one floor', f1 * OFFICE * 81, 1)
f3 = llr(OFFICE, 4, 243, 3); put('2.5 f three raw', 0.25 + 4.57 / math.sqrt(972), 4); put('2.5 f three', f3, 3)
put('2.5 L three floors', f3 * OFFICE * 243, 1); put('2.5 L three unreduced', OFFICE * 243, 1)
put('2.5 partitions three', 0.72 * 243, 1)
aA = 5 / 7 * 0.7 + 10 / 81; put('2.5 EN alphaA', aA, 3)
an3 = (2 + (3 - 2) * 0.7) / 3; put('2.5 EN alphan n3', an3, 3)
put('2.5 EN column Qk', (3.0 + 0.8) * 243 * an3, 1)
# practice: edge column no cantilever, KLL 4, AT 40.5 per floor, 3 floors
fp = llr(OFFICE, 4, 121.5, 3); put('2.5 practice f raw', 0.25 + 4.57 / math.sqrt(486), 4); put('2.5 practice f', fp, 4)
put('2.5 practice L', fp * OFFICE * 121.5, 1)

# 2.6 garage
at6 = 243.0
raw6 = 0.25 + 4.57 / math.sqrt(4 * at6); put('2.6 eq raw', raw6, 4)
put('2.6 office-style', max(raw6, 0.4) * GARAGE * at6, 1)
put('2.6 garage 20%', 0.8 * GARAGE * at6, 1); put('2.6 unreduced', GARAGE * at6, 1)
put('2.6 one floor', GARAGE * 81, 1)
bar_M = 26.70 * 0.686; put('2.6 barrier M', bar_M); put('2.6 barrier Mu', 1.6 * bar_M)
put('2.6 practice', 0.8 * GARAGE * 162, 1)


# 2.7 pattern loading: 3 equal spans, exact stiffness solution
def three_span(L, w):
    """w = [w1, w2, w3] uniform loads on the three spans. Returns support moments MB, MC (hogging negative)
    and the maximum sagging moment in each span, using the three-moment equation."""
    # three-moment: M_A L + 2 M_B (2L) + M_C L = -w1 L^3/4 - w2 L^3/4 ... (equal spans, M_A = M_D = 0)
    import numpy as np
    A = np.array([[4 * L, L], [L, 4 * L]])
    b = np.array([-(w[0] + w[1]) * L ** 3 / 4, -(w[1] + w[2]) * L ** 3 / 4])
    MB, MC = np.linalg.solve(A, b)
    sup = [0.0, MB, MC, 0.0]
    spans = []
    for i in range(3):
        Ml, Mr, wi = sup[i], sup[i + 1], w[i]
        # M(x) = Ml + (Mr-Ml) x/L + wi x (L-x)/2 ; max where dM/dx = 0
        xs = [j * L / 400 for j in range(401)]
        Ms = [Ml + (Mr - Ml) * x / L + wi * x * (L - x) / 2 for x in xs]
        spans.append((max(Ms), min(Ms)))
    return MB, MC, spans


L7 = 9.0
wd = 1.2 * (7.07 * 3 + 3.375); wl = 1.6 * (2.40 * 3)   # office secondary beam of 2.1 and 2.4
put('2.7 wd', wd, 3); put('2.7 wl', wl, 3)
cases = {
    'all': [wd + wl] * 3,
    '1+3': [wd + wl, wd, wd + wl],
    '2': [wd, wd + wl, wd],
    '1+2': [wd + wl, wd + wl, wd],
}
res7 = {k: three_span(L7, v) for k, v in cases.items()}
put('2.7 all M1+', res7['all'][2][0][0], 1); put('2.7 all MB', res7['all'][0], 1); put('2.7 all M2+', res7['all'][2][1][0], 1)
put('2.7 13 M1+', res7['1+3'][2][0][0], 1); put('2.7 13 M2max', res7['1+3'][2][1][0], 1)
put('2.7 2 M2+', res7['2'][2][1][0], 1)
put('2.7 12 MB', res7['1+2'][0], 1)
put('2.7 M1 increase %', (res7['1+3'][2][0][0] / res7['all'][2][0][0] - 1) * 100, 1)
put('2.7 MB increase %', (res7['1+2'][0] / res7['all'][0] - 1) * 100, 1)
put('2.7 M2 increase %', (res7['2'][2][1][0] / res7['all'][2][1][0] - 1) * 100, 1)
R['_res7'] = res7
# practice: live 3 x heavier (storage-like): wl = 1.6*18
wl_p = 1.6 * 18.0
rp_all = three_span(L7, [wd + wl_p] * 3); rp_13 = three_span(L7, [wd + wl_p, wd, wd + wl_p])
put('2.7 practice all M1+', rp_all[2][0][0], 1); put('2.7 practice 13 M1+', rp_13[2][0][0], 1)
put('2.7 practice increase %', (rp_13[2][0][0] / rp_all[2][0][0] - 1) * 100, 1)

# ---------------------------------------------------------------- Part C. Roof loads
def roof_lr(at):
    if at <= 18.58: r1 = 1.0
    elif at < 55.74: r1 = 1.2 - 0.011 * at
    else: r1 = 0.6
    return r1, min(max(0.96 * r1, 0.58), 0.96)


r1b, lrb = roof_lr(27); put('2.8 R1 beam', r1b, 3); put('2.8 Lr beam', lrb, 3)
r1g, lrg = roof_lr(81); put('2.8 R1 girder', r1g, 3); put('2.8 Lr girder raw', 0.96 * r1g, 3); put('2.8 Lr girder', lrg, 3)
r1p, lrp = roof_lr(40); put('2.8 practice R1', r1p, 3); put('2.8 practice Lr', lrp, 4)

pg9 = 1.20; pf9 = 0.7 * 1.0 * 1.0 * pg9; put('2.9 pf', pf9, 3)
pm9 = pg9 if pg9 <= 1.44 else 1.44; put('2.9 pm', pm9, 3)
put('2.9 trap Is RC IV', pf9 * 1.2, 3)
pgp = 2.00; put('2.9 practice pf', 0.7 * pgp, 3); put('2.9 practice pm', 1.44, 3)
put('2.9 EN s', 0.8 * 1.0 * 1.0 * 1.0, 2)

# 2.10 drift (ASCE 7-22, customary units)
def drift(pg_psf, lu_ft, W2):
    gam = min(0.13 * pg_psf + 14, 30.0)
    hd = 1.5 * math.sqrt(pg_psf ** 0.74 * lu_ft ** 0.70 * W2 ** 1.7 / gam)
    return gam, hd


pg_psf = 30.0; lu_up, lu_low = 100.0, 60.0; step_ft = 8.0; W2 = 0.45
gam, hd_lee = drift(pg_psf, lu_up, W2)
_, hd_w0 = drift(pg_psf, lu_low, W2); hd_wind = 0.75 * hd_w0
pf_low = 0.7 * pg_psf
hb = pf_low / gam; hc = step_ft - hb
hd = max(hd_lee, hd_wind)
hd = min(hd, 0.6 * lu_low)
w_d = 4 * hd if hd <= hc else 4 * hd ** 2 / hc
pd = hd * gam
put('2.10 gamma pcf', gam, 2); put('2.10 hd lee ft', hd_lee, 2); put('2.10 hd wind ft', hd_wind, 2)
put('2.10 pf psf', pf_low, 1); put('2.10 hb ft', hb, 2); put('2.10 hc ft', hc, 2); put('2.10 hc/hb', hc / hb, 2)
put('2.10 w ft', w_d, 2); put('2.10 pd psf', pd, 1)
FT, PSF = 0.3048, 0.04788
put('2.10 hd m', hd * FT, 2); put('2.10 w m', w_d * FT, 2); put('2.10 pd kPa', pd * PSF, 2); put('2.10 pf kPa', pf_low * PSF, 2)
put('2.10 peak kPa', (pf_low + pd) * PSF, 2)
put('2.10 gamma SI', 0.426 * 1.44 + 2.2, 2)
_, hdp = drift(pg_psf, lu_up, 0.55); put('2.10 practice hd ft', hdp, 2); put('2.10 practice pd psf', hdp * gam, 1)
put('2.10 practice pd kPa', hdp * gam * PSF, 2)

# 2.11 rain
put('2.11 R', 0.0098 * (75 + 25 + 15), 3); put('2.11 R no dp dh', 0.0098 * 75, 3)
put('2.11 practice', 0.0098 * (100 + 30 + 20), 3)

# ---------------------------------------------------------------- Part D. Wind
def kz_c(z):
    zz = max(z, 4.6)
    return 2.41 * (zz / 750.0) ** (2 / 9.8)


V = 46.0
def qz(z):
    return 0.613 * kz_c(z) * 1.0 * 1.0 * V ** 2 / 1000.0   # kPa


put('2.12 Kz15', kz_c(15), 3); put('2.12 qz15', qz(15), 3)
put('2.12 Kd qz15', 0.85 * qz(15), 3)
put('2.12 Kz30', kz_c(30), 3); put('2.12 qz30', qz(30), 3)
# Eurocode terrain III
def qp_en(z, vb0=27.0, z0=0.3, zmin=5.0):
    zz = max(z, zmin)
    kr = 0.19 * (z0 / 0.05) ** 0.07
    cr = kr * math.log(zz / z0)
    vm = cr * 1.0 * vb0
    Iv = 1.0 / (1.0 * math.log(zz / z0))
    return kr, cr, vm, Iv, (1 + 7 * Iv) * 0.5 * 1.25 * vm ** 2 / 1000.0


kr, cr, vm, Iv, qp15 = qp_en(15)
put('2.12 kr', kr, 4); put('2.12 cr', cr, 4); put('2.12 vm', vm, 2); put('2.12 Iv', Iv, 4); put('2.12 qp15', qp15, 3)
put('2.12 qb', 0.5 * 1.25 * 27 ** 2 / 1000, 4)
put('2.12 EN factored', 1.5 * qp15, 3)
put('2.12 qp30', qp_en(30)[4], 3)

# 2.13 MWFRS pressures, wind on the 36 m face (B = 36, L = 27)
G, Kd = 0.85, 0.85
Bw, Lw, h = 36.0, 27.0, 15.0
cp_lee = -0.5   # L/B = 0.75 <= 1
qh = qz(h)
trib = {3.75: 3.75, 7.5: 3.75, 11.25: 3.75, 15.0: 1.875}
story = {}
for z, t in trib.items():
    # windward pressure taken at the level height (simple, conservative within the storey)
    pw = qz(z) * Kd * G * 0.8
    pl = qh * Kd * G * abs(cp_lee)
    story[z] = (pw, pl, (pw + pl) * Bw * t)
R['_story'] = story
put('2.13 qh', qh, 3)
put('2.13 pw15', story[15.0][0], 3); put('2.13 pw3.75', story[3.75][0], 3); put('2.13 pl', story[15.0][1], 3)
for z in trib: put(f'2.13 F{z}', story[z][2], 1)
Vw = sum(v[2] for v in story.values()); put('2.13 Vw', Vw, 1)
# practice: wind on the 27 m face: B = 27, L/B = 36/27 = 1.333 -> leeward Cp interpolated between -0.5 (1) and -0.3 (2)
lb = 36 / 27; cpl = -0.5 + (lb - 1) * 0.2; put('2.13 practice cp', cpl, 3)
pl_p = qh * Kd * G * abs(cpl)
Vp = sum((qz(z) * Kd * G * 0.8 + pl_p) * 27 * t for z, t in trib.items()); put('2.13 practice V', Vp, 1)

# 2.14 internal pressure
lee_enc = qh * Kd * (G * -0.5 - 0.18); lee_pe = qh * Kd * (G * -0.5 - 0.55)
ww_enc = qh * Kd * (G * 0.8 + 0.18); ww_pe = qh * Kd * (G * 0.8 + 0.55)
put('2.14 lee enc', lee_enc, 3); put('2.14 lee pe', lee_pe, 3); put('2.14 lee incr %', (lee_pe / lee_enc - 1) * 100, 1)
put('2.14 ww enc', ww_enc, 3); put('2.14 ww pe', ww_pe, 3)
put('2.14 lee external only', qh * Kd * G * -0.5, 3)

# ---------------------------------------------------------------- Part E. Seismic
SDS, SD1, TL = 0.80, 0.40, 8.0
T0 = 0.2 * SD1 / SDS; TS = SD1 / SDS
put('2.15 T0', T0, 2); put('2.15 TS', TS, 2)
def sa(T):
    if T < T0: return SDS * (0.4 + 0.6 * T / T0)
    if T <= TS: return SDS
    if T <= TL: return SD1 / T
    return SD1 * TL / T ** 2
put('2.15 Sa0.05', sa(0.05), 3); put('2.15 Sa1.2', sa(1.2), 3); put('2.15 Sa0.533', sa(0.5329), 3)
# Eurocode Type 1, ground B, ag = 0.20 g, q = 3.9 (assumed for the example)
ag, S_, TB, TC, TD, q = 0.20, 1.2, 0.15, 0.5, 2.0, 3.9
put('2.15 EN elastic plateau', ag * S_ * 2.5, 3); put('2.15 EN design plateau', ag * S_ * 2.5 / q, 4)
put('2.15 EN design 1.2', ag * S_ * 2.5 / q * TC / 1.2, 4)

# 2.16 seismic weight
roof_slab_level = 5.0 + 1.0 + 0.5        # slab + insulation/waterproofing + ceiling (example)
roof_D = roof_slab_level + beams_avg; put('2.16 roof D', roof_D, 3)
perim = 2 * (PLAN_B + PLAN_L)
clad = perim * H_ST * 0.8                # facade 0.8 kN/m2 (assumed)
w_floor = AREA * floor_D + AREA * 0.48 + N_COL * col_storey + clad
w_roof = AREA * roof_D + N_COL * col_storey / 2 + clad / 2 + 150.0
put('2.16 floor slab+beams', AREA * floor_D, 1); put('2.16 partitions', AREA * 0.48, 1); put('2.16 columns', N_COL * col_storey, 1)
put('2.16 clad', clad, 1); put('2.16 w floor', w_floor, 1); put('2.16 w roof', w_roof, 1)
W = 3 * w_floor + w_roof; put('2.16 W', W, 1)
put('2.16 trap live', 3 * AREA * OFFICE, 1); put('2.16 trap %', 3 * AREA * OFFICE / W * 100, 1)
put('2.16 practice storage', 0.25 * 6.0 * 200, 1); put('2.16 practice 5% limit', 0.05 * w_floor, 1)

# 2.17 ELF
Ta = 0.0466 * 15 ** 0.9; put('2.17 Ta', Ta, 4)
Cu = 1.4; put('2.17 CuTa', Cu * Ta, 3)
Cs0 = SDS / 8; Csmax = SD1 / (Ta * 8); Csmin = max(0.044 * SDS, 0.01)
Cs = max(min(Cs0, Csmax), Csmin)
put('2.17 Cs0', Cs0, 4); put('2.17 Csmax', Csmax, 4); put('2.17 Csmin', Csmin, 4); put('2.17 Cs', Cs, 4)
Vs = Cs * W; put('2.17 V', Vs, 1)
k = 1 + (Ta - 0.5) / 2.0; put('2.17 k', k, 4)
ws = {3.75: w_floor, 7.5: w_floor, 11.25: w_floor, 15.0: w_roof}
den = sum(w * z ** k for z, w in ws.items())
Fx = {z: Vs * w * z ** k / den for z, w in ws.items()}
for z in Fx: put(f'2.17 F{z}', Fx[z], 1)
R['_Fx'] = Fx
put('2.17 V/Vw', Vs / Vw, 2)
Csp = SD1 / (Cu * Ta * 8); put('2.17 practice Cs', Csp, 4); put('2.17 practice V', Csp * W, 1)

# 2.18 interior ground column of the office building
D_col = 3 * (floor_D * 81 + col_storey) + roof_D * 81 + col_storey
put('2.18 D col', D_col, 1)
L_col = f3 * OFFICE * 243 + 0.72 * 243; put('2.18 L col', L_col, 1)
S_comp = 0.84 * 81; put('2.18 S companion', S_comp, 1)
QE = 250.0
c6 = (1.2 + 0.2 * SDS) * D_col + QE + 0.5 * L_col + 0.15 * S_comp
c7 = (0.9 - 0.2 * SDS) * D_col - QE
c7_noEv = 0.9 * D_col - QE
c6_o = (1.2 + 0.2 * SDS) * D_col + 3 * QE + 0.5 * L_col + 0.15 * S_comp
c7_o = (0.9 - 0.2 * SDS) * D_col - 3 * QE
put('2.18 Ev', 0.2 * SDS * D_col, 1)
put('2.18 c6', c6, 1); put('2.18 c7', c7, 1); put('2.18 c7 noEv', c7_noEv, 1); put('2.18 c6 omega', c6_o, 1); put('2.18 c7 omega', c7_o, 1)
SDSp = 1.2
put('2.18 practice c6', (1.2 + 0.2 * SDSp) * D_col + QE + 0.5 * L_col + 0.15 * S_comp, 1)
put('2.18 practice c7', (0.9 - 0.2 * SDSp) * D_col - QE, 1)

# ---------------------------------------------------------------- Part F. Other loads
# 2.19 basement wall, at rest
K0 = 1 - math.sin(math.radians(30)); put('2.19 K0', K0, 3)
gs, gsat, gw, Hw, dwt, qs = 18.0, 20.0, 9.81, 3.5, 2.0, 10.0
gp = gsat - gw; put('2.19 gamma prime', gp, 2)
p_wt = K0 * gs * dwt                          # soil at water table
p_base_soil = p_wt + K0 * gp * (Hw - dwt)
p_water = gw * (Hw - dwt)
p_sur = K0 * qs
put('2.19 p wt', p_wt, 2); put('2.19 p base soil', p_base_soil, 2); put('2.19 p water', p_water, 2); put('2.19 p sur', p_sur, 2)
put('2.19 p base total', p_base_soil + p_water + p_sur, 2)
# resultant per metre (trapezoid pieces)
F_soil = 0.5 * p_wt * dwt + p_wt * (Hw - dwt) + 0.5 * (p_base_soil - p_wt) * (Hw - dwt)
F_water = 0.5 * p_water * (Hw - dwt)
F_sur = p_sur * Hw
put('2.19 F soil', F_soil, 2); put('2.19 F water', F_water, 2); put('2.19 F sur', F_sur, 2)
put('2.19 F total', F_soil + F_water + F_sur, 2); put('2.19 H factored', 1.6 * (F_soil + F_water + F_sur), 2)
# trap: total unit weight, no water
p_trap = K0 * gs * Hw + p_sur; put('2.19 trap base', p_trap, 2)
F_trap = 0.5 * K0 * gs * Hw ** 2 + p_sur * Hw; put('2.19 trap F', F_trap, 2)
# trap: active Ka = 1/3 for a wall propped at top
put('2.19 Ka', 1 / 3, 3)
# buoyancy on the basement slab
uplift = gw * (Hw - dwt); slab_w = 0.30 * 25.0
put('2.19 uplift', uplift, 2); put('2.19 slab w', slab_w, 2); put('2.19 0.9 slab', 0.9 * slab_w, 2)
# practice: water table at top
p_base_full = K0 * gp * Hw + gw * Hw + p_sur; put('2.19 practice base', p_base_full, 2)
F_full = 0.5 * K0 * gp * Hw ** 2 + 0.5 * gw * Hw ** 2 + p_sur * Hw; put('2.19 practice F', F_full, 2)

# 2.20 temperature
alpha, dT, Lb = 10e-6, 25.0, 60.0
dL = alpha * dT * Lb * 1000; put('2.20 dL mm', dL, 2); put('2.20 end mm', dL / 2, 2)
E, Ic = 30000.0, 500 ** 4 / 12
k_un = 12 * E * Ic / 3750 ** 3 / 1000; put('2.20 k uncracked', k_un, 2)
k_cr = 0.5 * k_un; put('2.20 k cracked', k_cr, 2)
Vt = k_cr * dL / 2; put('2.20 V', Vt, 1); put('2.20 M', Vt * 3.75 / 2, 1)
put('2.20 practice V', k_cr * dL / 4, 1)

# 2.21 crane
wheel, cap, trolley = 90.0, 100.0, 20.0
put('2.21 class B', wheel * 1.10, 1); put('2.21 class D', wheel * 1.25, 1)
lat = 0.20 * (cap + trolley); put('2.21 lateral', lat, 1); put('2.21 lateral per side', lat / 2, 1); put('2.21 lateral per wheel', lat / 4, 1)
put('2.21 longitudinal per wheel', 0.10 * wheel, 1)

# ---------------------------------------------------------------- Part G. Combinations
# 2.22 ASCE 7-22 strength combinations, interior ground column
D, L, Lr = D_col, L_col, 0.58 * 81
S_pr = max(pf9, pm9) * 81            # snow as principal load: the uniform minimum governs here
S_cmp = pf9 * 81                     # companion snow: pf (Exception 2)
Wc = 150.0
put('2.22 D', D, 1); put('2.22 L', L, 1); put('2.22 Lr', Lr, 1); put('2.22 S pr', S_pr, 1); put('2.22 S cmp', S_cmp, 1)
c = {}
c['1a'] = 1.4 * D
c['2a'] = 1.2 * D + 1.6 * L + max(0.5 * Lr, 0.3 * S_cmp)
c['3a'] = 1.2 * D + max(1.6 * Lr, 1.0 * S_pr) + max(0.5 * L, 0.5 * Wc)
c['4a'] = 1.2 * D + 1.0 * Wc + 0.5 * L + max(0.5 * Lr, 0.3 * S_cmp)
c['5a'] = 0.9 * D - 1.0 * Wc
for kk, v in c.items(): put('2.22 ' + kk, v, 1)
R['_c22'] = c
put('2.22 3a 716', 1.2 * D + 1.6 * S_pr + 0.5 * L, 1)
# ASD
asd = {'2a': D + L, '7a': 0.6 * D - 0.6 * Wc}
for kk, v in asd.items(): put('2.22 ASD ' + kk, v, 1)
# practice: roof beam, heavy snow site pg 2.4 kN/m2
beam_D = roof_slab_level * 3 + beam_web
pf_h = 0.7 * 2.4; pm_h = 1.44
put('2.22 practice beam D', beam_D, 3); put('2.22 practice pf', pf_h, 3)
S_beam = max(pf_h, pm_h) * 3; Lr_beam = lrb * 3
put('2.22 practice S', S_beam, 3); put('2.22 practice Lr', Lr_beam, 3)
put('2.22 practice 3a', 1.2 * beam_D + max(1.6 * Lr_beam, 1.0 * S_beam), 3)
put('2.22 practice 3a 1.6S', 1.2 * beam_D + 1.6 * S_beam, 3)
put('2.22 practice diff %', ((1.2 * beam_D + 1.6 * S_beam) / (1.2 * beam_D + max(1.6 * Lr_beam, 1.0 * S_beam)) - 1) * 100, 1)

# 2.23 Eurocode ULS, same column
Gk = D_col
Qk1 = (3.0 + 0.8) * 243 * an3
Qs = 0.8 * 1.0 * 81
Qw = 100.0
put('2.23 Gk', Gk, 1); put('2.23 Qk1', Qk1, 1); put('2.23 Qs', Qs, 1)
e610 = 1.35 * Gk + 1.5 * Qk1 + 1.5 * 0.5 * Qs + 1.5 * 0.6 * Qw
Qk1_un = (3.0 + 0.8) * 243          # alpha_n is not applied together with psi0 (cautious reading of EN 1991-1-1)
put('2.23 Qk1 unreduced', Qk1_un, 1)
e610a = 1.35 * Gk + 1.5 * 0.7 * Qk1_un + 1.5 * 0.5 * Qs + 1.5 * 0.6 * Qw
put('2.23 6.10a with alphan (not used)', 1.35 * Gk + 1.5 * 0.7 * Qk1 + 1.5 * 0.5 * Qs + 1.5 * 0.6 * Qw, 1)
put('2.23 1.5Qk1', 1.5 * Qk1, 1); put('2.23 1.05Qk1un', 1.05 * Qk1_un, 1); put('2.23 acc', 1.5 * 0.5 * Qs + 1.5 * 0.6 * Qw, 1)
e610b = 0.85 * 1.35 * Gk + 1.5 * Qk1 + 1.5 * 0.5 * Qs + 1.5 * 0.6 * Qw
put('2.23 6.10', e610, 1); put('2.23 6.10a', e610a, 1); put('2.23 6.10b', e610b, 1)
put('2.23 saving %', (1 - max(e610a, e610b) / e610) * 100, 1)
R['_e23'] = {'6.10': e610, '6.10a': e610a, '6.10b': e610b}
put('2.23 1.35Gk', 1.35 * Gk, 1); put('2.23 0.85x1.35Gk', 0.85 * 1.35 * Gk, 1)
# practice: wind leading (compression side)
put('2.23 practice 6.10a wind', e610a, 1)
put('2.23 practice 6.10b wind', 0.85 * 1.35 * Gk + 1.5 * Qw + 1.5 * 0.7 * Qk1_un + 1.5 * 0.5 * Qs, 1)

# 2.24 uplift
Du, Wu = 300.0, -350.0
put('2.24 ASCE 5a', 0.9 * Du + Wu, 1); put('2.24 ASD 7a', 0.6 * Du + 0.6 * Wu, 1); put('2.24 wrong 1.2D', 1.2 * Du + Wu, 1)
Qwk = -220.0
put('2.24 EN STR', 1.0 * Du + 1.5 * Qwk, 1); put('2.24 EN EQU', 0.9 * Du + 1.5 * Qwk, 1); put('2.24 EN wrong 1.35', 1.35 * Du + 1.5 * Qwk, 1)
put('2.24 practice 5a', 0.9 * 400 + Wu, 1); put('2.24 practice 7a', 0.6 * 400 + 0.6 * Wu, 1)

# 2.25 garage edge column, seismic
Dg, Lg, QEg = 349.3, 81.0, 60.0
g6 = (1.2 + 0.2 * SDS) * Dg + QEg + 1.0 * Lg
g6_half = (1.2 + 0.2 * SDS) * Dg + QEg + 0.5 * Lg
g7 = (0.9 - 0.2 * SDS) * Dg - QEg
g2a = 1.2 * Dg + 1.6 * Lg
put('2.25 c6', g6, 1); put('2.25 c6 half', g6_half, 1); put('2.25 c7', g7, 1); put('2.25 2a', g2a, 1); put('2.25 1.4D', 1.4 * Dg, 1)
put('2.25 half diff %', (1 - g6_half / g6) * 100, 1)
put('2.25 practice c6', (1.2 + 0.2 * SDS) * Dg + 120 + Lg, 1); put('2.25 practice c7', (0.9 - 0.2 * SDS) * Dg - 120, 1)

# 2.26 serviceability (EN)
gk_b = slab_level * 3 + beam_web; qk_b = (3.0 + 0.8) * 3
put('2.26 gk', gk_b, 3); put('2.26 qk', qk_b, 2)
put('2.26 char', gk_b + qk_b, 3); put('2.26 qp', gk_b + 0.3 * qk_b, 3); put('2.26 ULS 6.10', 1.35 * gk_b + 1.5 * qk_b, 3)
put('2.26 qp share %', (gk_b + 0.3 * qk_b) / (gk_b + qk_b) * 100, 1)
put('2.26 practice qp', gk_b + 0.3 * (3.0 + 1.2) * 3, 3)
put('2.26 qp partitions permanent', gk_b + 0.8 * 3 + 0.3 * 3.0 * 3, 3); put('2.26 practice qp partitions permanent', gk_b + 1.2 * 3 + 0.3 * 3.0 * 3, 3)

# ---------------------------------------------------------------- Part H. Software and checking
combos27 = {'1.2D+1.6L': (3000, 40), '1.2D+L+W': (2300, 220), '0.9D+W': (1300, 230), '0.9D-Ev+E': (1050, 270)}
B27 = 3.0
out27 = {}
for kk, (P, M) in combos27.items():
    e = M / P; qmax = P / B27 ** 2 + 6 * M / B27 ** 3; qmin = P / B27 ** 2 - 6 * M / B27 ** 3
    out27[kk] = (P, M, e, qmax, qmin)
    put(f'2.27 {kk} e', e, 3); put(f'2.27 {kk} qmax', qmax, 1); put(f'2.27 {kk} qmin', qmin, 1)
env = (3000, 270)
put('2.27 env qmax', env[0] / 9 + 6 * env[1] / 27, 1); put('2.27 env qmin', env[0] / 9 - 6 * env[1] / 27, 1); put('2.27 env e', env[1] / env[0], 3)
R['_c27'] = out27
put('2.27 practice e', 300 / 900, 3); put('2.27 practice qmin', 900 / 9 - 6 * 300 / 27, 1); put('2.27 practice qmax', 900 / 9 + 6 * 300 / 27, 1)

# 2.28 model check
hand_D = 3 * AREA * floor_D + AREA * roof_D + 4 * (N_COL * col_storey + clad) + 150.0   # base reaction: all four storeys of columns and facade
put('2.28 hand D', hand_D, 0)
hand_L = 3 * AREA * OFFICE; put('2.28 hand L', hand_L, 0)
# errors planted for the example: SDL of the three floors in a case that no combination uses; 50 psf typed as 50 kN/m2
model_D = hand_D - 3 * AREA * sdl
model_SDL_case = 3 * AREA * sdl
put('2.28 model D', model_D, 0); put('2.28 ratio D', model_D / hand_D, 3); put('2.28 SDL case', model_SDL_case, 0)
put('2.28 model L', 3 * AREA * 50.0, 0); put('2.28 ratio L', 50.0 / OFFICE, 2)
put('2.28 practice hand S', 0.84 * AREA, 1); put('2.28 practice model S', 0.84 * 0.04788 * AREA, 1); put('2.28 practice ratio', 0.04788, 4)


# late additions (practice values used in the text)
Ralt = 1.127 * 81
put('2.22 0.5R alt', 0.5 * Ralt, 1); put('2.22 1.6R alt', 1.6 * Ralt, 1)
put('2.22 2a alt', 1.2 * D + 1.6 * L + 0.5 * Ralt, 1); put('2.22 3a alt', 1.2 * D + 1.6 * Ralt + 0.5 * L, 1); put('2.22 4a alt', 1.2 * D + Wc + 0.5 * L + 0.5 * Ralt, 1)
put('2.19 uplift factored', 1.6 * uplift, 2); put('2.19 net upward', 1.6 * uplift - 0.9 * slab_w, 2)
put('2.19 trap gsat', K0 * gs * dwt + K0 * gsat * (Hw - dwt) + p_sur, 2)
put('2.13 bottom strip', (story[3.75][0] + story[3.75][1]) * Bw * 1.875, 1); put('2.13 total incl bottom', Vw + (story[3.75][0] + story[3.75][1]) * Bw * 1.875, 1)
put('2.21 practice lateral', 0.20 * (200 + 30), 1); put('2.21 practice per wheel', 0.20 * (200 + 30) / 4, 2)
put('2.10 practice w ft', 4 * R['2.10 practice hd ft'], 2); put('2.10 practice hd m', R['2.10 practice hd ft'] * 0.3048, 2)
put('2.16 practice share %', 300.0 / R['2.16 w floor'] * 100, 1)
put('2.6 practice formula', max(0.25 + 4.57 / math.sqrt(4 * 162), 0.4) * 1.92 * 162, 1)
put('2.13 practice pl', R['2.13 qh'] * 0.85 * 0.85 * 0.433, 3)


if __name__ == '__main__':
    for kk, v in R.items():
        if not kk.startswith('_'):
            print(f'{kk:32s} {v}')
