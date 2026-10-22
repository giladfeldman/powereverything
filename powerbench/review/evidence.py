"""Conservative lexical support, never semantic or statistical certification."""
import re
from math import isclose

NUMBER=r"(?<![\w.\-+−–—])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"

def numeric_tokens(text):
    normalized=text.replace('−','-')
    normalized=re.sub(r'(?<![\w\d])[–—](?=[.\d])','-',normalized)
    return [float(token) for token in re.findall(NUMBER,normalized)]

def lexical_support(name,value,quote):
    if not isinstance(quote,str):return False
    patterns={
      'alternative':{'two.sided':r'\btwo[ -](?:sided|tailed)\b','greater':r'\b(?:greater|upper[ -]tailed|positive direction)\b','less':r'\b(?:less|lower[ -]tailed|negative direction)\b'},
      'multiplicity_method':{'none':r'\b(?:none|unadjusted|no (?:multiplicity |multiple.testing )?adjustment|single primary test)\b','bonferroni':r'\bbonferroni\b','hochberg':r'\bhochberg\b'},
      'model':{'two_sample_t':r'\b(?:independent|unpaired|two[ ._-](?:sample|group))\b.*\bt[ -]?(?:test)?\b|\bTTestIndPower\b|\btype\s*=\s*[\'\"]two\.sample[\'\"]',
        'welch_t':r'\bwelch\b','paired_t':r'\bpaired\s+t(?:[ -]test)?\b|\btype\s*=\s*[\'\"]paired[\'\"]',
        'correlation':r'\b(?:pearson|correlation)\b|pwr\.r\.test','one_way_anova':r'\bone[ -]way\s+(?:anova|analysis of variance)\b',
        'linear_regression':r'\b(?:overall\s+)?linear regression\b','incremental_regression':r'\bincremental regression\b'},
      'effect_metric':{'cohens_d':r'\bcohen[’\']?s?\s+d\b|\bcohens_d\b|\bd\s*=', 'cohens_dz':r'\b(?:cohens_dz|dz)\b','rho':r'\b(?:rho|pearson correlation)\b|\br\s*=', 'cohens_f':r'\bcohens_f\b|\bf\s*=', 'cohens_f2':r'\bcohens_f2\b|\bf(?:2|²)\s*='},
      'n_unit':{'total':r'\btotal\b','group':r'\bper[ -]group\b|\beach group\b','per_group':r'\bper[ -]group\b|\beach group\b','pairs':r'\bpairs?\b','participants':r'\bparticipants?\b'}
    }
    if name in patterns:
        if not isinstance(value,str):return False
        pattern=patterns[name].get(value)
        if pattern:return bool(re.search(pattern,quote,re.IGNORECASE))
        return bool(value and re.search(r'(?<!\w)'+re.escape(value)+r'(?!\w)',quote,re.IGNORECASE))
    if name=='software':return isinstance(value,str) and bool(value) and bool(re.search(r'(?<!\w)'+re.escape(value)+r'(?!\w)',quote,re.IGNORECASE))
    return True


def anchored_number(name,value,quote):
    patterns={'alpha':r'\b(?:alpha|α|significance\s+(?:level|threshold))\b','target_power':r'\b(?:target\s+)?power\b','attrition_rate':r'\b(?:attrition|dropout|loss(?:es)?(?:\s+to\s+follow.up)?)\b'}
    if name not in patterns:return True
    number=r'([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)'
    matches=re.finditer(patterns[name]+r'\s*(?:(?:was|is|of|at|rate|level|set|to|equal|equals)\s*|[=:]){0,4}\s*'+number+r'\s*(%|percent)?',quote,re.IGNORECASE)
    return any(isclose(float(m.group(1))/(100 if m.group(2) else 1),value,rel_tol=1e-10,abs_tol=1e-12) for m in matches)


def code_support(name,value,quote):
    if not isinstance(quote,str):return False
    if name=='model':
        return isinstance(value,str) and value in {'two_sample_t','welch_t','paired_t','correlation','one_way_anova','linear_regression','incremental_regression'} and lexical_support(name,value,quote)
    if name in {'n_per_group','effect','alpha'}:
        argument_names={'n_per_group':r'n|nobs1','effect':r'd|effect_size','alpha':r'sig\.level|alpha'}[name]
        number=r'([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)'
        matches=re.finditer(r'(?<![\w.])(?:'+argument_names+r')\s*=\s*'+number+r'(?![\w.])',quote.replace('−','-'))
        if not any(isinstance(value,(int,float)) and not isinstance(value,bool) and isclose(float(match.group(1)),value,rel_tol=1e-10,abs_tol=1e-12) for match in matches):return False
        if name=='n_per_group':
            # A paired n counts pairs. Unequal-group nobs1 is group 1, not a
            # common per-group count. Require both function and explicit units.
            r_balanced=bool(re.search(r'pwr\.t\.test\s*\(',quote) and re.search(r'type\s*=\s*[\'"]two\.sample[\'"]',quote))
            ratio=re.search(r'\bratio\s*=\s*'+number+r'(?![\w.])',quote)
            py_balanced=bool('TTestIndPower' in quote and ratio and float(ratio.group(1))==1)
            return r_balanced or py_balanced
        return True
    if name=='goal':
        if not isinstance(value,str):return False
        if value=='achieved_power':return bool(re.search(r'pwr\.[\w.]+\([^\n]*\bn\s*=\s*[.\d]|\.power\s*\([^\n]*\bnobs1\s*=\s*[.\d]',quote,re.IGNORECASE))
        if value=='required_sample_size':return bool(re.search(r'\b(?:n|nobs1)\s*=\s*(?:NULL|None)\b',quote))
        if value=='sensitivity':return bool(re.search(r'\b(?:d|effect_size)\s*=\s*(?:NULL|None)\b',quote))
        return False
    return True
