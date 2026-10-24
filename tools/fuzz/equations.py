import random, sympy, traceback, sys
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
x=sympy.Symbol('x')
def poly(deg):
    terms=[]
    for d in range(deg,-1,-1):
        c=random.choice([-5,-4,-3,-2,-1,0,1,1,2,3,4,5,6])
        if d==deg and c==0: c=1
        if c==0: continue
        mono="" if d==0 else ("x" if d==1 else f"x^{d}")
        coef=str(abs(c)) if (d==0 or abs(c)!=1) else ""
        terms.append(("+" if c>0 else "-")+coef+mono)
    s="".join(terms).lstrip('+')
    return s
def src_of(lhs,rhs): return "{=({%s},{%s})}"%(lhs,rhs)
bad=0;n=0;fails=[]
for _ in range(400):
    kind=random.choice(['poly','polyrhs','rational','radical'])
    if kind=='poly': L,R=poly(random.choice([1,2,2,3])),"0"
    elif kind=='polyrhs': L,R=poly(random.choice([1,2])),str(random.randint(-6,6))
    elif kind=='rational': 
        a,b,c=[random.randint(1,5) for _ in range(3)]
        L,R="frac({%dx+%d},{x+%d})"%(a,b,c),str(random.randint(1,4))
    else:
        a=random.randint(1,6); b=random.randint(0,5)
        L,R="root2({x+%d})"%a, str(random.randint(1,5))
    src=src_of(L,R)
    try:
        node=parse_protocol(src)
    except Exception: continue
    n+=1
    try:
        res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e:
        fails.append((src,repr(e)[:80])); continue
    sol=res.get('solution')
    lhs,rhs=node.children
    resid=to_sympy(lhs)-to_sympy(rhs)
    try:
        ss=sympy.solveset(resid,x,sympy.S.Reals)
        if not isinstance(ss,sympy.FiniteSet): 
            if ss==sympy.S.EmptySet: valid=set()
            else: continue
        else: valid={round(float(sympy.N(r)),5) for r in ss}
    except Exception: continue
    got=set()
    if sol:
        nd=parse_json(sol)
        items=nd.children if nd.type.value=='LIST' else [nd]
        for it in items:
            if it.type.value=='EQUALS':
                try:
                    z=complex(sympy.N(to_sympy(it.children[1])))
                except Exception: continue
                if abs(z.imag)<1e-9: got.add(round(z.real,5))
    if got!=valid:
        bad+=1; print('MISMATCH',src,sorted(got),sorted(valid))
print('checked',n,'mismatch',bad,'failures',len(fails))
for f in fails[:15]: print('FAIL',f)
