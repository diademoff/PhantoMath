import random, sys, sympy
from mymath_backend import service
from mymath_backend.input import parse_protocol, parse_json
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]))
names = sympy.symbols("x y z w")
def term(c, v):
    return ("" if c == 1 else "-" if c == -1 else str(c)) + v
def eqsrc(row, rhs, vs):
    parts = [(c, str(v)) for c, v in zip(row, vs) if c]
    if not parts: return None
    s = term(*parts[0])
    for c, v in parts[1:]:
        s += ("+" + term(c, v)) if c > 0 else ("-" + term(-c, v))
    return "{=({%s},{%d})}" % (s, rhs)
n_ok = n_bad = n_err = 0
for _ in range(120):
    m, n = random.randint(2, 4), random.randint(2, 4)
    vs = names[:n]
    r = random.randint(1, min(m, n))
    B = sympy.Matrix([[random.randint(-3, 3) for _ in range(n)] for _ in range(r)])
    C = sympy.Matrix([[random.randint(-2, 2) for _ in range(r)] for _ in range(m)])
    A = C * B
    if random.random() < 0.3: rhs = sympy.zeros(m, 1)
    else:
        x0 = sympy.Matrix([random.randint(-3, 3) for _ in range(n)])
        rhs = A * x0
        if random.random() < 0.4: rhs[random.randrange(m)] += random.randint(1, 3)
    eqs = [eqsrc(list(A.row(i)), rhs[i], vs) for i in range(m)]
    if None in eqs or len(set(eqs)) < m or any(set(map(str, vs)) - set("".join(eqs)) for _ in [0]): continue
    src = "{system(" + ",".join(eqs) + ")}"
    want = sympy.linsolve((A, rhs), *vs)
    try:
        res = service.solve_request(parse_protocol(src).to_contract(), locale="ru")["result"]
        sol = parse_json(res["solution"]) if res.get("solution") else None
    except Exception as e:
        n_err += 1; print("ERR", src, repr(e)[:100]); continue
    if sol is None:
        n_err += 1; print("NOSOL", src); continue
    t = sol.type.value
    if want == sympy.EmptySet:
        ok = t == "EMPTY"
    else:
        sub = {}
        parts = sol.children if t == "LIST" else [sol]
        for p in parts:
            if p.type.value == "EQUALS":
                sub[to_sympy(p.children[0])] = to_sympy(p.children[1])
        point = list(want)[0]
        # basic unknowns: compare; free ones must map to themselves
        ok = all(sympy.simplify(sub.get(v, v) - pv) == 0 for v, pv in zip(vs, point)) if t != "EMPTY" else False
    if ok: n_ok += 1
    else: n_bad += 1; print("BAD", src, sol.type.value, want)
print("ok", n_ok, "bad", n_bad, "err", n_err)
