"""Finite reflected tails independently checked against installed R stats."""
from itertools import product
import math
import subprocess
import pytest
from powerbench.adapters.r_pwr import _resolve_rscript
from powerbench.references import _noncentral_t_power

def test_noncentral_t_tail_grid_matches_r_stats(tmp_path):
 script=r'''options(digits=17)
 for(df in c(1,2,5.5,30)) for(delta in c(-10,-.5,0,.5,10)) for(alpha in c(.01,.05)) for(alt in c("two.sided","greater","less")) {
  critical=qt(1-alpha/ifelse(alt=="two.sided",2,1),df)
  probability=if(alt=="two.sided") pt(-critical,df,ncp=delta)+pt(critical,df,ncp=delta,lower.tail=FALSE) else if(alt=="greater") pt(critical,df,ncp=delta,lower.tail=FALSE) else pt(-critical,df,ncp=delta)
  cat(probability,"\n")
 }
'''
 source=tmp_path/'tail-grid.R'
 source.write_text(script,encoding='utf-8')
 result=subprocess.run([_resolve_rscript(),str(source)],capture_output=True,text=True,check=True,timeout=60)
 expected=[float(value) for value in result.stdout.split()]
 grid=list(product((1,2,5.5,30),(-10,-.5,0,.5,10),(.01,.05),('two.sided','greater','less')))
 actual=[_noncentral_t_power(df,delta,alpha,alternative) for df,delta,alpha,alternative in grid]
 assert len(expected)==len(actual)==120
 assert all(math.isfinite(value) and 0<=value<=1 for value in actual+expected)
 assert actual==pytest.approx(expected,rel=1e-9,abs=1e-10)
 for df,delta,alpha,_ in grid:
  assert _noncentral_t_power(df,delta,alpha,'greater')==pytest.approx(_noncentral_t_power(df,-delta,alpha,'less'),abs=1e-14)
