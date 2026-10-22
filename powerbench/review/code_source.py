"""Read a single literal power call as data. Never execute source or expressions."""
import ast
import re
from math import isfinite


def _number(node):
    if isinstance(node,ast.Constant):
        value=node.value
    elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)) and isinstance(node.operand,ast.Constant) and isinstance(node.operand.value,(int,float)) and not isinstance(node.operand.value,bool):
        value=(-1 if isinstance(node.op,ast.USub) else 1)*node.operand.value
    else:raise ValueError('Not a scalar literal')  # noqa: TRY004 - source validation uses ValueError
    if value is None or isinstance(value,str):return value
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value):raise ValueError('Not a finite scalar literal')
    return value


def _r_without_comments(text):
    lines=[];quote=None;escaped=False
    for line in text.splitlines():
        kept=[]
        for character in line:
            if quote:
                kept.append(character)
                if escaped:escaped=False
                elif character=='\\':escaped=True
                elif character==quote:quote=None
            elif character in {'"',"'"}:quote=character;kept.append(character)
            elif character=='#':break
            else:kept.append(character)
        lines.append(''.join(kept))
    return '\n'.join(lines).strip()


def literal_power_call(text):
    """Return matched literal arguments, or abstain on ambiguous syntax/call units."""
    if not isinstance(text,str) or len(text)>100000:return {}
    try:
        r=_r_without_comments(text)
        match=re.fullmatch(r'(?:[A-Za-z_]\w*\s*(?:<-|=)\s*)?(?:pwr::)?pwr\.t\.test\s*\(([^()]*)\)\s*;?',r,re.DOTALL)
        if match:
            arguments={}
            for item in match.group(1).split(','):
                pair=re.fullmatch(r'\s*([A-Za-z_][\w.]*)\s*=\s*(.*?)\s*',item,re.DOTALL)
                if not pair or pair.group(1) in arguments:return {}
                key,raw=pair.groups()
                if key not in {'n','d','sig.level','power','type','alternative'}:return {}
                arguments[key]=None if raw=='NULL' else _number(ast.parse(raw,mode='eval').body)
            model={'two.sample':'two_sample_t','paired':'paired_t'}.get(arguments.get('type'))
            n=arguments.get('n');effect=arguments.get('d');alpha=arguments.get('sig.level')
            target=arguments.get('power')
            goal='achieved_power' if n is not None and effect is not None and target is None else 'required_sample_size' if 'n' in arguments and n is None and effect is not None and target is not None else 'sensitivity' if 'd' in arguments and effect is None and n is not None and target is not None else None
            return {'model':model,'n_per_group':n if model=='two_sample_t' else None,'effect':effect,'alpha':alpha,'goal':goal}
        module=ast.parse(text.strip(),mode='exec')
        statements=[item for item in module.body if not isinstance(item,(ast.Import,ast.ImportFrom))]
        if len(statements)!=1:return {}
        statement=statements[0]
        call=statement.value if isinstance(statement,(ast.Expr,ast.Assign,ast.AnnAssign)) else None
        if not isinstance(call,ast.Call) or call.args or not isinstance(call.func,ast.Attribute) or call.func.attr not in {'power','solve_power'}:return {}
        constructor=call.func.value
        if not isinstance(constructor,ast.Call) or not isinstance(constructor.func,ast.Name) or constructor.func.id!='TTestIndPower' or constructor.args or constructor.keywords:return {}
        if any(keyword.arg is None for keyword in call.keywords):return {}
        arguments={keyword.arg:_number(keyword.value) for keyword in call.keywords}
        if len(arguments)!=len(call.keywords) or set(arguments)-{'nobs1','effect_size','alpha','power','ratio','alternative'}:return {}
        n,effect,alpha=arguments.get('nobs1'),arguments.get('effect_size'),arguments.get('alpha')
        goal='achieved_power' if call.func.attr=='power' and n is not None and effect is not None else 'required_sample_size' if call.func.attr=='solve_power' and 'nobs1' in arguments and n is None else 'sensitivity' if call.func.attr=='solve_power' and 'effect_size' in arguments and effect is None else None
        return {'model':'two_sample_t','n_per_group':n if arguments.get('ratio')==1 else None,'effect':effect,'alpha':alpha,'goal':goal}
    except (SyntaxError,ValueError,TypeError,RecursionError):return {}
