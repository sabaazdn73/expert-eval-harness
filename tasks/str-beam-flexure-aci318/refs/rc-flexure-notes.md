# Reinforced concrete flexure: working notes (author's own summary, not code text)
- Equivalent rectangular stress block: depth a = As fy / (0.85 f'c b).
- beta1 = 0.85 for f'c up to 28 MPa, reducing by 0.05 per 7 MPa above, not below 0.65. Neutral axis c = a / beta1.
- Net tensile strain eps_t = 0.003 (d - c) / c. Tension-controlled when eps_t >= 0.005: phi = 0.90. Compression-controlled at eps_t <= ey: phi = 0.65 (tied). Linear in between.
- Nominal moment Mn = As fy (d - a/2). Design strength phi Mn must be >= Mu.
- Basic factored load combinations for gravity: 1.4D; 1.2D + 1.6L. Use the larger.
- Simply supported beam under uniform load: M = w L^2 / 8 at midspan.
- Minimum flexural steel: the larger of 0.25 sqrt(f'c)/fy and 1.4/fy, times bw d (MPa units).
