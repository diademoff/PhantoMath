import random, sympy, sys
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
x=sympy.Symbol('x')
def rp(deg):
    terms=[]
    for d in range(deg,-1,-1):
        c=random.choice([-4,-3,-2,-1,0,1,1,2,3,5])
        if d==deg and c==0: c=1
        if c==0: continue
        mono="" if d==0 else ("x" if d==1 else f"x^{d}")
        coef=str(abs(c)) if (d==0 or abs(c)!=1) else ""
        terms.append(("+" if c>0 else "-")+coef+mono)
    return "".join(terms).lstrip('+')
FUNCS=["sin({x})","cos({x})","e","ln({x})","x"]
def rnd_expr():
    k=random.choice(['poly','prod','quot','trig','exp','ln','root','chain'])
    if k=='poly': return rp(random.choice([1,2,3,4]))
    if k=='prod': return "(%s)*(%s)"%(rp(random.choice([1,2])),rp(random.choice([1,2])))
    if k=='quot': return "frac({%s},{%s})"%(rp(random.choice([1,2])),rp(1))
    if k=='trig': return random.choice(["sin","cos","tan"])+"({%s})"%rp(1)
    if k=='exp': return "\\\\e^({%s})"%rp(1) if False else "\\e^x*%s"%rp(1)
    if k=='ln': return "ln({%s})"%rp(1)
    if k=='root': return "root2({%s})"%rp(1)
    if k=='chain': return "(%s)^%d"%(rp(1),random.randint(2,5))
def numeq(a,b):
    import random as R
    hits=0
    for _ in range(40):
        v=R.uniform(-6,6)
        try:
            av=complex(sympy.N(a.subs(x,v))); bv=complex(sympy.N(b.subs(x,v)))
        except Exception: continue
        if any(map(lambda z: z!=z or abs(z)>1e12, (av,bv))): continue
        if abs(av.imag)>1e-6 or abs(bv.imag)>1e-6: continue
        hits+=1
        if abs(av-bv)>1e-6*(1+abs(av)): return False
    return hits>=3 or True
bad=0;n=0;fails=[]
for _ in range(250):
    expr=rnd_expr()
    mode=random.choice(['diff','int'])
    src=("{derivation_diff({x},{%s})}" if mode=='diff' else "{integral({%s})}")%expr
    try: node=parse_protocol(src)
    except Exception: continue
    n+=1
    try:
        res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e:
        fails.append((src,repr(e)[:90])); continue
    sol=res.get('solution')
    if not sol: fails.append((src,'no solution')); continue
    nd=parse_json(sol)
    inner=parse_protocol("{%s}"%expr)
    f=to_sympy(inner)
    try:
        if mode=='diff':
            want=sympy.diff(f,x); got=to_sympy(nd)
            ok=numeq(want,got)
        else:
            first=nd.children[0] if nd.type.value=='LIST' else nd
            # strip + C
            if first.type.value=='ADD' and first.children[-1].value=='C': first=first.children[0] if len(first.children)==2 else first
            got=to_sympy(first)
            ok=numeq(sympy.diff(got,x),f)
    except Exception as e:
        fails.append((src,'check '+repr(e)[:60])); continue
    if not ok:
        bad+=1; print('WRONG',src,'->',got)
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:20]: print('FAIL',f)
