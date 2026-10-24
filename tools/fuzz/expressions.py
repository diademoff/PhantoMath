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
    a=random.choice([1,1,2,-1,3]);b=random.randint(-6,6);c=random.randint(-8,8)
    s=("" if a==1 else ("-" if a==-1 else str(a)))+"x^2"
    if b: s+="%+d"%b+"x" if abs(b)!=1 else ("+x" if b==1 else "-x")
    if c: s+="%+d"%c
    return s
def expr():
    k=random.choice(['sum','prod','sq','cube','frac','mix'])
    if k=='sum': return "%s+%s-%s"%(lin(),lin(),lin())
    if k=='prod': return "(%s)*(%s)"%(lin(),lin())
    if k=='sq': return "(%s)^2"%lin()
    if k=='cube': return "(%s)^3"%lin()
    if k=='frac': return "frac({%s},{%s})+frac({%s},{%s})"%(lin(),lin(),lin(),lin())
    return "2(%s)-3(%s)"%(lin(),lin())
bad=0;n=0;fails=[]
for _ in range(250):
    src="{%s}"%expr()
    try: node=parse_protocol(src)
    except Exception: continue
    n+=1
    try: f=to_sympy(node)
    except Exception: continue
    try:
        res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e:
        fails.append((src,repr(e)[:90])); continue
    sol=res.get('solution')
    if not sol: fails.append((src,'no solution')); continue
    nd=parse_json(sol)
    # either an expression equal to f, or a list of roots of f
    if nd.type.value=='LIST' or nd.type.value=='EQUALS':
        items=nd.children if nd.type.value=='LIST' else [nd]
        for it in items:
            if it.type.value!='EQUALS': continue
            v=to_sympy(it.children[1])
            try:
                r=complex(sympy.N(f.subs(x,v)))
            except Exception: continue
            if abs(r)>1e-6:
                bad+=1; print('NOT A ROOT',src,v,r)
    else:
        g=to_sympy(nd)
        ok=True
        for pt in (0.37,1.9,-2.3):
            try:
                if abs(complex(sympy.N(f.subs(x,pt)))-complex(sympy.N(g.subs(x,pt))))>1e-7: ok=False
            except Exception: pass
        if not ok:
            bad+=1; print('NOT EQUAL',src,g)
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:12]: print('FAIL',f)
