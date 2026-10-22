"""Conservative lexical support, never semantic or statistical certification."""
import re
from math import isclose

NUMBER=r"(?<![\w.\-+−–—])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"

def numeric_claims(text: str) -> list[tuple[float, bool]]:
    normalized=text.replace('−','-').replace('–','-').replace('—','-')
    normalized=re.sub(r'(?<=\d)-(?=[.\d])',' -',normalized)
    normalized=re.sub(r'(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?',lambda match:match.group().replace(',',''),normalized)
    return [(float(match.group()),bool(re.match(r'\s*(?:%|percent\b)',normalized[match.end():],re.IGNORECASE))) for match in re.finditer(NUMBER,normalized)]


def numeric_tokens(text: str) -> list[float]:
    return [value for value,_ in numeric_claims(text)]

def lexical_support(name: str, value: object, quote: str | None) -> bool:
    if not isinstance(quote,str):return False
    if name=='model' and value=='two_sample_t' and re.search(r'\bwelch\b',quote,re.IGNORECASE):return False
    if name=='model' and value=='welch_t' and re.search(r'\b(?:not|never|no)\b.{0,25}\bwelch\b|\bwelch\b.{0,25}\b(?:not|never)\b',quote,re.IGNORECASE):return False
    if name=='effect_metric' and value=='cohens_f':return bool(re.search(r'\bcohens_f\b|\bcohen[’\']?s?\s+f\b',quote,re.IGNORECASE) or re.search(r'\bf\s*=',quote))
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


_NUMBER_LITERAL=r'([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)'
_NUMBER_LABELS={
 'alpha':r'alpha|α|significance\s+(?:level|threshold)',
 'target_power':r'(?:target(?:ed)?|desired|planned)\s+power|power',
 'attrition_rate':r'attrition|dropout|loss(?:es)?(?:\s+to\s+follow.up)?',
 'effect':r'effect(?:\s+(?:size|d|dz|rho|f2|f²|f))?|cohens_dz|cohens_d|cohens_f2|cohens_f|mean\s+difference|rho|d|dz|f2|f²|r',
 'reported_n':r'reported\s+(?:total\s+)?analysable\s+sample|total\s+(?:analysable\s+)?sample|sample\s+size|total\s+N|N|n',
 'allocation_ratio':r'allocation\s+ratio|ratio',
 'family_alpha':r'family\s+alpha|familywise\s+alpha',
 'primary_tests':r'primary\s+tests|primary\s+hypotheses',
 'groups':r'groups|number\s+of\s+groups',
 'predictors':r'predictors|number\s+of\s+predictors',
 'total_predictors':r'total\s+predictors|full.model\s+predictors',
 'tested_predictors':r'tested\s+predictors|tested\s+block\s+size',
 'studies':r'studies|number\s+of\s+studies',
 'tau':r'tau|τ', 'looks':r'looks|interim\s+analyses', 'categories':r'categories',
 'sd_group1':r'sd_group1|sd1|group\s+1\s+(?:SD|standard\s+deviation)',
 'sd_group2':r'sd_group2|sd2|group\s+2\s+(?:SD|standard\s+deviation)',
}


def labeled_numbers(name: str, quote: str | None) -> list[float]:
    label=_NUMBER_LABELS.get(name)
    if not label or not isinstance(quote,str):return []
    text=quote.replace('−','-')
    if name=='alpha' and re.search(r'cronbach|coefficient\s+alpha|reliability',text,re.IGNORECASE):return []
    pattern=r'(?<!\w)(?:'+label+r')(?!\w)\s*(?:(?:was|is|of|at|rate|level|set|to|equal|equals)\s*|[=:]){0,4}\s*'+_NUMBER_LITERAL+r'\s*(%|percent\b)?(?!\w|\.\d)'
    values=[]
    for match in re.finditer(pattern,text,re.IGNORECASE):
        # Reject a numeric prefix of an unevaluated expression or range.
        if re.match(r'\s*[/*+−–—:]|\s*-(?=\s*[.\d])',text[match.end():]):continue
        if name=='target_power' and re.search(r'\b(?:observed|achieved|post[ -]?hoc)\s*$',text[max(0,match.start()-25):match.start()],re.IGNORECASE):continue
        values.append(float(match.group(1))/(100 if match.group(2) else 1))
    return values


def anchored_number(name: str, value: float, quote: str | None) -> bool:
    return any(isclose(number,value,rel_tol=1e-10,abs_tol=1e-12) for number in labeled_numbers(name,quote))


def code_support(name: str, value: object, quote: str | None) -> bool:
    from .code_source import literal_power_call
    parsed=literal_power_call(quote)
    expected=parsed.get(name)
    if expected is None or value is None:return False
    if isinstance(expected,(int,float)):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and isclose(expected,value,rel_tol=1e-10,abs_tol=1e-12)
    return isinstance(value,str) and value==expected


def finding_supported(code: str, quote: str | None, text: str) -> bool:
    if not isinstance(quote,str) or len(re.findall(r"\w+",quote))<3:return False
    if code=='observed_effect_posthoc':
        return bool(re.search(r'\bobserved\b',quote,re.IGNORECASE) and re.search(r'post[ -]?hoc|after (?:data )?collection|observed (?:study )?effects?',quote,re.IGNORECASE))
    if code in {'missing_alpha','missing_target_power','missing_attrition'}:
        field={'missing_alpha':'alpha','missing_target_power':'target_power','missing_attrition':'attrition_rate'}[code]
        return not labeled_numbers(field,text)
    if code=='missing_sidedness':return not re.search(r'\b(?:two[ -]sided|two[ -]tailed|one[ -]sided|one[ -]tailed|greater|less)\b',text,re.IGNORECASE)
    if code=='missing_allocation':return not (labeled_numbers('allocation_ratio',text) or re.search(r'\bequal\s+(?:allocation|between groups)|allocation was equal|balanced (?:groups|allocation)',text,re.IGNORECASE))
    if code=='missing_effect_rationale':return not re.search(r'(?:effect rationale|smallest effect of interest|prior evidence|previous research)',text,re.IGNORECASE)
    if code=='per_group_vs_total':
        from .code_source import literal_power_call
        n=literal_power_call(quote).get('n_per_group')
        match=re.search(r'(?:manuscript|reported|reports).*?\btotal\s+N\s*[=:]\s*(\d+)',quote,re.IGNORECASE|re.DOTALL)
        return isinstance(n,(int,float)) and bool(match) and int(match.group(1))!=2*n
    if code=='missing_seed_for_simulation':return bool(re.search(r'simulat|rnorm|runif|random\.',quote,re.IGNORECASE) and not re.search(r'set\.seed|random_state|default_rng|seed\s*[=(]',text,re.IGNORECASE))
    if code=='unreported_decision_rule':return not re.search(r'sig\.level\s*=|\balpha\s*=|\bconfidence\s*=',text,re.IGNORECASE)
    if code=='unsupported_or_ambiguous_code':
        from .code_source import literal_power_call
        return not bool(literal_power_call(quote))
    return code=='analysis_match_unresolved'


def rewrite_labels_match(paragraph: str, confirmed: dict) -> bool:
    request=confirmed.get('canonical_request',{})
    scenario=request.get('scenario',{}) if isinstance(request,dict) else {}
    scenario=scenario if isinstance(scenario,dict) else {}
    effect=scenario.get('effect',{})
    effect=effect if isinstance(effect,dict) else {}
    rule=scenario.get('decision_rule',{})
    rule=rule if isinstance(rule,dict) else {}
    result=confirmed.get('canonical_result',{})
    expectations={
      'effect':[confirmed.get('effect'),*(effect.get(key) for key in ('cohens_d','cohens_dz','rho','cohens_f','cohens_f2','mean_difference')),result.get('detectable_effect') if isinstance(result,dict) else None],
      'alpha':[confirmed.get('alpha'),rule.get('alpha')],
      'target_power':[confirmed.get('target_power'),scenario.get('target_power')],
      'reported_n':[confirmed.get('n'),confirmed.get('reported_n'),*(result.get(key) for key in ('n_total','n1','n2','n_per_group'))] if isinstance(result,dict) else [],
    }
    canonical=confirmed.get('canonical_paragraph','')
    for field,values in expectations.items():
        allowed=[value for value in values if isinstance(value,(int,float)) and not isinstance(value,bool)]
        allowed+=labeled_numbers(field,canonical)
        for claim in labeled_numbers(field,paragraph):
            if allowed and not any(isclose(claim,value,rel_tol=1e-10,abs_tol=1e-12) for value in allowed):return False
    return True
