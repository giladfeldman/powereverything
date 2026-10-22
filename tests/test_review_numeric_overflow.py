import pytest

from powerbench.review.assistant import validate_assistance


@pytest.mark.parametrize('value',[10**400,10**307])
def test_extraction_withholds_unrepresentable_or_scaled_number(value):
    text='The target power was 95%, alpha 5%.'
    output={'has_power_analysis':True,'analyses':[{'fields':{'alpha':{'value':value,'quote':text,'start':0,'end':len(text),'status':'reported'}}}]}
    result=validate_assistance('extraction',text,output)
    assert result['analyses'][0]['fields']['alpha']['value'] is None


def test_code_withholds_unrepresentable_number():
    text='pwr::pwr.t.test(n=100, d=.4, sig.level=.05, type="two.sample")'
    output={'fields':{'n_per_group':10**400},'evidence':{'n_per_group':{'quote':text}},'findings':[]}
    result=validate_assistance('code',text,output)
    assert result['fields']['n_per_group']['value'] is None


def test_unrepresentable_confirmed_number_is_a_validation_error():
    confirmed={'n':10**400}
    with pytest.raises(ValueError):
        validate_assistance('rewrite','source',{'paragraph':'Draft [effect rationale needed]','confirmed':confirmed},confirmed)
