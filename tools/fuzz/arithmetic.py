import random, sympy, sys, math
from fractions import Fraction
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
x=sympy.Symbol('x')
def num(): return random.choice([1,2,3,4,5,6,7,8,9,10,12,15])
def aexpr(d=0):
    if d>2 or random.random()<0.35:
        k=random.random()
        if k<0.2: return "frac({%d},{%d})"%(num(),num())
        if k<0.3: return "root2({%d})"%random.choice([2,3,4,8,9,12,16,18,25,50])
        return str(num())
    a,b=aexpr(d+1),aexpr(d+1)
    op=random.choice(['+','-','*','+','-'])
    if op=='*': return "(%s)*(%s)"%(a,b)
    if op=='-': return "%s-(%s)"%(a,b)
    return "%s+%s"%(a,b)
bad=0;n=0;fails=[]
for _ in range(300):
    src="{%s}"%aexpr()
    try: node=parse_protocol(src)
    except Exception: continue
    try: want=complex(sympy.N(to_sympy(node)))
    except Exception: continue
    n+=1
    try:
        res=service.solve_request(node.to_contract(), locale="ru")['result']
    except Exception as e:
        fails.append((src,repr(e)[:90])); continue
    sol=res.get('solution')
    if not sol: fails.append((src,'no solution')); continue
    got=complex(sympy.N(to_sympy(parse_json(sol))))
    if abs(got-want)>1e-6*(1+abs(want)):
        bad+=1; print('WRONG',src,got,want)
    alts=res.get('alternativeForms') or []
    for a in alts:
        try:
            av=complex(sympy.N(to_sympy(parse_json(a))))
        except Exception: continue
        if abs(av-want)>1e-4*(1+abs(want)):
            bad+=1; print('ALT WRONG',src,av,want)
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:12]: print('FAIL',f)
