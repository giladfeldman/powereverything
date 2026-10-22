"""Independent high-precision log-g integration of the stated Cauchy mixture."""
import mpmath as mp
import pytest
from powerbench.specialist_extras import jzs_bf10_from_t

def test_extreme_jzs_matches_independent_high_precision_log_g_integral():
 with mp.workdps(60):
  t,nu,neff,r=mp.mpf(50),mp.mpf(18),mp.mpf(5),mp.mpf('.7071')
  def integrand(x):
   g=mp.exp(x);variance=1+neff*g
   log_ratio=-mp.log(variance)/2-(nu+1)/2*mp.log1p(t*t/(nu*variance))+(nu+1)/2*mp.log1p(t*t/nu)
   return mp.exp(log_ratio+mp.log(r)-mp.log(2*mp.pi)/2-x/2-r*r/(2*g))
  # In log(g), the upper omitted tail decays as exp(-x); the lower tail
  # decays faster than exp(-r² exp(-x)/2). These bounds are negligible at
  # this precision for the declared t=50, df=18, n_eff=5 case.
  expected=mp.quad(integrand,[-100,-20,-10,-5,0,5,10,20,50,100])
  assert jzs_bf10_from_t(50,10,10)==pytest.approx(float(expected),rel=1e-10)
