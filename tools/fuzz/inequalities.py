import random, sympy, sys
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
x=sympy.Symbol('x')
def poly(deg):
    terms=[]
    for d in range(deg,-1,-1):
        c=random.choice([-4,-3,-2,-1,0,1,1,2,3,5])
        if d==deg and c==0: c=1
        if c==0: continue
        mono="" if d==0 else ("x" if d==1 else f"x^{d}")
        coef=str(abs(c)) if (d==0 or abs(c)!=1) else ""
        terms.append(("+" if c>0 else "-")+coef+mono)
    return "".join(terms).lstrip('+')
rels=[("<","<"),(">",">"),("<=","<="),(">=",">=")]
bad=0;n=0;fails=[]
def inset(sol_node, v):
    t=sol_node.type.value
    def val(nd):
        if nd.type.value=='NEGATIVE' and nd.children[0].value=='∞': return -sympy.oo
        if nd.value=='∞': return sympy.oo
        return to_sympy(nd)
    if t in ('OPEN_OPEN_INTERVAL','OPEN_CLOSED_INTERVAL','CLOSED_OPEN_INTERVAL','CLOSED_CLOSED_INTERVAL'):
        a,b=val(sol_node.children[0]),val(sol_node.children[1])
        lo=t.startswith('CLOSED'); hi=t.endswith('CLOSED_INTERVAL') and t.split('_')[1]=='CLOSED'
        L=lo and True; H=t.split('_')[1]=='CLOSED'
        return (a<v if not L else a<=v) and (v<b if not H else v<=b)
    if t=='UNION': return any(inset(c,v) for c in sol_node.children)
    if t in ('LESS_THAN','LESS_THAN_EQUAL','GREATER_THAN','GREATER_THAN_EQUAL'):
        rhs=to_sympy(sol_node.children[1])
        return {'LESS_THAN':v<rhs,'LESS_THAN_EQUAL':v<=rhs,'GREATER_THAN':v>rhs,'GREATER_THAN_EQUAL':v>=rhs}[t]
    if t=='EMPTY': return False
    if t=='LIST': return any(inset(c,v) for c in sol_node.children)
    if t=='EQUALS': return abs(float(sympy.N(v-to_sympy(sol_node.children[1]))))<1e-9
    raise ValueError(t)
for _ in range(300):
    op,_=random.choice(rels)
    kind=random.choice(['poly','rational','abs'])
    if kind=='poly': L,R=poly(random.choice([1,2,2,3])),str(random.randint(-3,3))
    elif kind=='rational': L,R="frac({%s},{%s})"%(poly(1),poly(1)),str(random.randint(-2,2))
    else: L,R="abs({%s})"%poly(1),str(random.randint(0,6))
    src="{%s({%s},{%s})}"%(op,L,R)
    try: node=parse_protocol(src)
    except Exception: continue
    n+=1
    try: res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e: fails.append((src,repr(e)[:90])); continue
    sol=res.get('solution')
    if not sol:
        fails.append((src,'no node')); continue
    nd=parse_json(sol)
    lhs,rhs=node.children
    fl,fr=to_sympy(lhs),to_sympy(rhs)
    rel={'<':sympy.Lt,'>':sympy.Gt,'<=':sympy.Le,'>=':sympy.Ge}[op]
    for v in [sympy.Rational(k,4) for k in range(-40,41,3)]+[sympy.Rational(7,3),sympy.Rational(-11,3)]:
        try:
            truth=bool(rel(fl.subs(x,v),fr.subs(x,v)))
            if fl.subs(x,v).has(sympy.zoo,sympy.nan) or fr.subs(x,v).has(sympy.zoo,sympy.nan): continue
        except Exception: continue
        try: got=inset(nd,v)
        except Exception as e: fails.append((src,'check '+repr(e)[:50])); break
        if got!=truth:
            bad+=1; print('WRONG',src,'at',v,'truth',truth,'got',got); break
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:12]: print('FAIL',f)
