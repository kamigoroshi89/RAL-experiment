import numpy as np
from scipy.stats import norm
from scipy import integrate
SIG=8.0; A,B=110.0,140.0; W=B-A
def G(u): return u*norm.cdf(u)+norm.pdf(u)
def p_in_uniform(d,s=SIG,a=A,b=B):
    w=b-a; return (s/w)*(G((w-d)/s)-2*G(-d/s)+G((-w-d)/s))
def p_out_L(m,s=SIG):  # latent U[a,b] + N(0,s) + sign*m*s, fair sign
    d=m*s
    return 1-0.5*(p_in_uniform(d)+p_in_uniform(-d))
def p_out_O(m):  # observed uniform in band, offset m*SIG
    return min(1.0,m*SIG/W)
def p_out_density(f,lo,hi,m,s=SIG,a=A,b=B):
    d=m*s
    def g(x,dd):
        return f(x)*(1-(norm.cdf((b-x-dd)/s)-norm.cdf((a-x-dd)/s)))
    v=0
    for dd in (d,-d):
        v+=0.5*integrate.quad(g,lo,hi,args=(dd,),limit=200)[0]
    return v
def Pk(p,k): return 1-(1-p)**k
if __name__=="__main__":
    f=lambda x: 1/W
    for m in (0,0.5,1,1.5,2.5,3):
        print(m, p_out_L(m), p_out_density(f,A,B,m), p_out_O(m))
