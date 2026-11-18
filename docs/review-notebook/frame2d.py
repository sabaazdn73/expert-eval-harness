"""frame2d: a small 2D frame solver (direct stiffness method) used to check Module 3 a second way.

Units: kN, m. Each node has ux, uy, rz. An element end can be released for moment (hinge),
which gives that end its own rotation degree of freedom. Loads: nodal forces, uniform load on an
element (local y, positive along local +y), point loads on an element (local y). Supports are fixed
degrees of freedom with an optional prescribed displacement (settlement). Springs are added to the
diagonal of a node degree of freedom.

Sign convention for results: element end forces in local axes, acting on the element (N, V, M with
moments counterclockwise positive). Internal bending moment M(x) is sagging positive for a member
drawn left to right (local y up): M(x) = -Mi + Vi x + q x^2/2 + sum P (x - a).
"""
import numpy as np


class Frame:
    def __init__(self):
        self.nodes = []          # (x, y)
        self.els = []            # dict
        self.fixed = {}          # global dof -> prescribed value
        self.springs = {}        # global dof -> stiffness
        self.nodal = {}          # global dof -> force

    # ------------------------------------------------------------ model
    def node(self, x, y):
        self.nodes.append((float(x), float(y)))
        return len(self.nodes) - 1

    def elem(self, i, j, E, A, I, rel_i=False, rel_j=False):
        self.els.append(dict(i=i, j=j, E=E, A=A, I=I, rel_i=rel_i, rel_j=rel_j, q=0.0, P=[]))
        return len(self.els) - 1

    def support(self, n, ux=None, uy=None, rz=None):
        """Pass 0.0 to fix a dof, a number for a prescribed displacement, None to leave free."""
        for k, v in enumerate((ux, uy, rz)):
            if v is not None:
                self.fixed[3 * n + k] = float(v)

    def spring(self, n, dof, k):
        self.springs[3 * n + dof] = self.springs.get(3 * n + dof, 0.0) + k

    def load(self, n, fx=0.0, fy=0.0, mz=0.0):
        for k, v in enumerate((fx, fy, mz)):
            if v:
                self.nodal[3 * n + k] = self.nodal.get(3 * n + k, 0.0) + v

    def udl(self, e, q):
        self.els[e]['q'] += q          # local +y; gravity on a beam drawn left to right: q = -w

    def point(self, e, P, a):
        self.els[e]['P'].append((P, a))

    # ------------------------------------------------------------ element helpers
    def _geom(self, el):
        (x1, y1), (x2, y2) = self.nodes[el['i']], self.nodes[el['j']]
        L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        c, s = (x2 - x1) / L, (y2 - y1) / L
        T = np.zeros((6, 6))
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        T[:3, :3] = R; T[3:, 3:] = R
        return L, T

    @staticmethod
    def _k_local(E, A, I, L):
        k = np.zeros((6, 6))
        a = E * A / L
        b, c, d, e = 12 * E * I / L ** 3, 6 * E * I / L ** 2, 4 * E * I / L, 2 * E * I / L
        k[0, 0] = k[3, 3] = a; k[0, 3] = k[3, 0] = -a
        k[1, 1] = k[4, 4] = b; k[1, 4] = k[4, 1] = -b
        k[1, 2] = k[2, 1] = k[1, 5] = k[5, 1] = c
        k[4, 2] = k[2, 4] = k[4, 5] = k[5, 4] = -c
        k[2, 2] = k[5, 5] = d; k[2, 5] = k[5, 2] = e
        return k

    @staticmethod
    def _fef(el, L):
        """Fixed-end forces (local, acting on the element) for the member loads."""
        f = np.zeros(6)
        q = el['q']
        f += np.array([0, -q * L / 2, -q * L ** 2 / 12, 0, -q * L / 2, q * L ** 2 / 12])
        for P, a in el['P']:
            b = L - a
            f += np.array([0, -P * b * b * (3 * a + b) / L ** 3, -P * a * b * b / L ** 2,
                           0, -P * a * a * (a + 3 * b) / L ** 3, P * a * a * b / L ** 2])
        return f

    # ------------------------------------------------------------ solve
    def solve(self):
        nn = len(self.nodes)
        ndof = 3 * nn
        self.edofs = []
        for el in self.els:
            d = [3 * el['i'], 3 * el['i'] + 1, 3 * el['i'] + 2, 3 * el['j'], 3 * el['j'] + 1, 3 * el['j'] + 2]
            if el['rel_i']:
                d[2] = ndof; ndof += 1
            if el['rel_j']:
                d[5] = ndof; ndof += 1
            self.edofs.append(d)
        K = np.zeros((ndof, ndof)); F = np.zeros(ndof)
        for dof, v in self.nodal.items():
            F[dof] += v
        self.kl, self.Ts, self.fefs, self.Ls = [], [], [], []
        for el, d in zip(self.els, self.edofs):
            L, T = self._geom(el)
            kl = self._k_local(el['E'], el['A'], el['I'], L)
            fef = self._fef(el, L)
            kg = T.T @ kl @ T
            fg = T.T @ fef
            for a in range(6):
                F[d[a]] -= fg[a]
                for b in range(6):
                    K[d[a], d[b]] += kg[a, b]
            self.kl.append(kl); self.Ts.append(T); self.fefs.append(fef); self.Ls.append(L)
        for dof, k in self.springs.items():
            K[dof, dof] += k
        fixed = sorted(self.fixed)
        free = [i for i in range(ndof) if i not in self.fixed]
        u = np.zeros(ndof)
        for dof in fixed:
            u[dof] = self.fixed[dof]
        Kff = K[np.ix_(free, free)]
        rhs = F[free] - K[np.ix_(free, fixed)] @ u[fixed]
        if free:
            self.cond = np.linalg.cond(Kff)
            u[free] = np.linalg.solve(Kff, rhs)
        else:
            self.cond = 1.0
        self.u = u
        R = K @ u - F
        self.reactions = {dof: R[dof] for dof in fixed}
        for dof, k in self.springs.items():
            self.reactions[('spring', dof)] = -k * u[dof]
        self.ef = []
        for el, d, kl, T, fef in zip(self.els, self.edofs, self.kl, self.Ts, self.fefs):
            ul = T @ u[d]
            self.ef.append(kl @ ul + fef)
        return self

    # ------------------------------------------------------------ results
    def disp(self, n):
        return self.u[3 * n], self.u[3 * n + 1], self.u[3 * n + 2]

    def reac(self, n, dof):
        return self.reactions.get(3 * n + dof, 0.0)

    def end_forces(self, e):
        return self.ef[e]

    def M_at(self, e, x):
        """Internal moment, sagging positive, at distance x from end i."""
        el, f = self.els[e], self.ef[e]
        m = -f[2] + f[1] * x + el['q'] * x * x / 2
        for P, a in el['P']:
            if x > a:
                m += P * (x - a)
        return m

    def V_at(self, e, x):
        el, f = self.els[e], self.ef[e]
        v = f[1] + el['q'] * x
        for P, a in el['P']:
            if x > a:
                v += P
        return v

    def M_extremes(self, e, n=400):
        L = self.Ls[e]
        xs = np.linspace(0, L, n + 1)
        ms = np.array([self.M_at(e, x) for x in xs])
        return ms.max(), xs[ms.argmax()], ms.min(), xs[ms.argmin()]


def rect(b, h):
    return b * h, b * h ** 3 / 12.0


if __name__ == '__main__':
    # self checks against closed forms
    E = 25_000_000.0
    A, I = rect(0.3, 0.6)
    w, L = 10.0, 8.0
    # fixed-fixed beam
    f = Frame(); a = f.node(0, 0); b = f.node(L, 0); e = f.elem(a, b, E, A, I)
    f.support(a, 0, 0, 0); f.support(b, 0, 0, 0); f.udl(e, -w); f.solve()
    assert abs(f.M_at(e, 0) + w * L * L / 12) < 1e-6 and abs(f.M_at(e, L / 2) - w * L * L / 24) < 1e-6
    # simply supported via release
    f = Frame(); a = f.node(0, 0); b = f.node(L, 0); e = f.elem(a, b, E, A, I)
    f.support(a, 0, 0); f.support(b, None, 0); f.udl(e, -w); f.solve()
    assert abs(f.M_at(e, L / 2) - w * L * L / 8) < 1e-6
    d = f.disp(f.nodes.index((L, 0.0)))
    # midspan deflection by adding a node
    f = Frame(); a = f.node(0, 0); m = f.node(L / 2, 0); b = f.node(L, 0)
    e1 = f.elem(a, m, E, A, I); e2 = f.elem(m, b, E, A, I)
    f.support(a, 0, 0); f.support(b, None, 0); f.udl(e1, -w); f.udl(e2, -w); f.solve()
    assert abs(-f.disp(m)[1] - 5 * w * L ** 4 / (384 * E * I)) < 1e-9
    # propped cantilever with point load at midspan: M_fixed = 3PL/16
    f = Frame(); a = f.node(0, 0); b = f.node(L, 0); e = f.elem(a, b, E, A, I)
    f.support(a, 0, 0, 0); f.support(b, None, 0); f.point(e, -100.0, L / 2); f.solve()
    assert abs(f.M_at(e, 0) + 3 * 100 * L / 16) < 1e-6
    # two-span settlement: M_B = 3 E I delta / L^2
    f = Frame(); a = f.node(0, 0); b = f.node(L, 0); c = f.node(2 * L, 0)
    e1 = f.elem(a, b, E, A, I); e2 = f.elem(b, c, E, A, I)
    f.support(a, 0, 0); f.support(b, None, -0.01); f.support(c, None, 0); f.solve()
    assert abs(f.M_at(e1, L) - 3 * E * I * 0.01 / L ** 2) < 1e-6
    print('frame2d self checks passed')
