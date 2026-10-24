import random, sympy, sys
from mymath_backend import service
from mymath_backend.input import parse_json, parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
def src(A):
    return "mat("+",".join("{mat_row("+",".join("{%s}"%sympy.sstr(v) for v in A.row(i))+")}" for i in range(A.rows))+")"
def mat(r,c):
    A=sympy.Matrix([[random.randint(-4,5) for _ in range(c)] for _ in range(r)])
    return src(A), A
def request(source, command=None, args=()):
    action=None
    if command:
        action={"command":command,"args":[parse_protocol(a).to_contract() for a in args]}
    return service.solve_request(parse_protocol(source).to_contract(), action, locale="ru")['result']
bad=0;n=0;fails=[]
for _ in range(240):
    k=random.choice(['add','mul','scalar','sub','det','inv','mul3','rank','rank','solve_left','solve_right'])
    command=None;args=()
    if k=='add':
        r,c=random.randint(1,3),random.randint(1,3); a,A=mat(r,c); b,B=mat(r,c); s="{%s+%s}"%(a,b); want=A+B
    elif k=='sub':
        r,c=random.randint(1,3),random.randint(1,3); a,A=mat(r,c); b,B=mat(r,c); s="{%s-%s}"%(a,b); want=A-B
    elif k=='mul':
        r,m,c=[random.randint(1,3) for _ in range(3)]; a,A=mat(r,m); b,B=mat(m,c); s="{%s*%s}"%(a,b); want=A*B
    elif k=='scalar':
        r,c=random.randint(1,3),random.randint(1,3); a,A=mat(r,c); t=random.randint(2,5); s="{%d*%s}"%(t,a); want=t*A
    elif k=='det':
        r=random.randint(2,3); a,A=mat(r,r); s="{det(%s)}"%a; want=A.det()
    elif k=='inv':
        r=random.randint(2,3); a,A=mat(r,r)
        if A.det()==0: continue
        s="{%s^(-1)}"%a; want=A.inv()
    elif k=='mul3':
        a,A=mat(2,2); b,B=mat(2,2); c,C=mat(2,2); s="{%s*%s*%s}"%(a,b,c); want=A*B*C
    elif k=='rank':
        r,c=random.randint(1,4),random.randint(1,5)
        if random.random()<0.15: A=sympy.zeros(r,c)
        else: _,A=mat(r,c)
        s=src(A); command='matrix_rank'; want=A.rank()
    elif k=='solve_left':
        r,c=random.randint(1,4),random.randint(1,4); a,A=mat(r,r); b,B=mat(r,c)
        if A.det()==0: continue
        s=a; command='matrix_solve_left'; args=(b,); want=A.inv()*B
    else:
        r,c=random.randint(1,4),random.randint(1,4); a,A=mat(r,r); b,B=mat(c,r)
        if A.det()==0: continue
        s=a; command='matrix_solve_right'; args=(b,); want=B*A.inv()
    try: parse_protocol(s)
    except Exception as e: continue
    n+=1
    try: res=request(s, command, args)
    except Exception as e: fails.append((s[:60],repr(e)[:80])); continue
    sol=res.get('solution')
    if not sol: fails.append((s[:60],'no solution')); continue
    try: got=to_sympy(parse_json(sol))
    except Exception as e: fails.append((s[:60],'conv '+repr(e)[:50])); continue
    if hasattr(want,'shape') and hasattr(got,'shape'):
        ok = sympy.simplify(got-want) == sympy.zeros(*want.shape)
    else:
        ok = sympy.simplify(got-want) == 0
    if not ok:
        bad+=1; print('WRONG',s[:80],got,want)
print('checked',n,'wrong',bad,'failures',len(fails))
for f in fails[:12]: print('FAIL',f)
