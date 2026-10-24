import random, sympy, sys
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
x=sympy.Symbol('x')
def lin():
    a=random.choice([-3,-2,-1,1,2,3]);b=random.randint(-6,6)
    return ("%s%s%s"%("" if a==1 else ("-" if a==-1 else a),"x","%+d"%b if b else ""))
def quad():
    return "%s*(%s)"%(lin(),lin())
bad=0;n=0;fails=[]
def val(nd):
    try:
        if nd.type.value=='NEGATIVE' and nd.children[0].value=='∞': return -sympy.oo
        if nd.value=='∞': return sympy.oo
        return to_sympy(nd)
    except Exception: return None
for _ in range(150):
    kind=random.choice(['lim_rat','lim_rat_inf','lim_trig','defint_poly','defint_trig','defint_exp'])
    if kind=='lim_rat':
        a=random.randint(-3,3)
        src="{lim({%d},{frac({(x-%d)*(%s)},{(x-%d)*(%s)})})}"%(a,a,lin(),a,lin())
        src=src.replace("-%d)"%a,"%+d)"%(-a)) if False else src
        # ensure valid: use (x-a) as written
        src="{lim({%d},{frac({(x%+d)*(%s)},{(x%+d)*(%s)})})}"%(a,-a,lin(),-a,lin())
        f=lambda: sympy.limit(((x-a)*sympy.sympify(lin())/(x-a)),x,a) if False else None
        expr=None
    elif kind=='lim_rat_inf':
        src="{lim({∞},{frac({%s},{%s})})}"%(quad(),quad())
        expr=None
    elif kind=='lim_trig':
        k=random.randint(1,5)
        src="{lim({0},{frac({sin({%dx})},{x})})}"%k
        expr=None
    elif kind=='defint_poly':
        a,b=sorted(random.sample(range(-3,5),2))
        src="{integral_def({%d},{%d},{%s})}"%(a,b,quad() if random.random()<0.5 else lin())
        expr=None
    elif kind=='defint_trig':
        src="{integral_def({0},{pi},{%s({x})})}"%random.choice(['sin','cos'])
        expr=None
    else:
        src="{integral_def({0},{%d},{\\e^x})}"%random.randint(1,3)
        expr=None
    try: node=parse_protocol(src)
    except Exception as e: continue
    n+=1
    try: res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e: fails.append((src,repr(e)[:90])); continue
    sol=res.get('solution')
    if not sol: fails.append((src,'no solution')); continue
    got=val(parse_json(sol))
    # independent value
    try:
        if node.type.value in ('LIMIT','LIMIT_NORMAL') or 'lim' in src[:6]:
            point=val(node.children[0]); fexp=to_sympy(node.children[1]); want=sympy.limit(fexp,x,point)
        else:
            lo,hi,fe=[to_sympy(c) for c in node.children[:3]]; want=sympy.integrate(fe,(x,lo,hi))
    except Exception as e: fails.append((src,'check '+repr(e)[:60])); continue
    try:
        ok = (got==want) or abs(complex(sympy.N(got-want)))<1e-6
    except Exception: ok=False
    if not ok: bad+=1; print('WRONG',src,got,want)
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:12]: print('FAIL',f)
