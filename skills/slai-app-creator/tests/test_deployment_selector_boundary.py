from pathlib import Path
import pytest
import yaml
import main


def errors(selector):
    doc={'spec':{'selector':selector,'template':{'metadata':{'labels':{'app.kubernetes.io/name':'example','tier':'worker'}}}}}
    return main._app_name_label_errors(yaml.safe_dump(doc),Path('/example/deployment.yaml'))


def test_selector_requires_application_label_even_with_expressions():
    assert errors({})
    assert errors({'matchExpressions':[{'key':'app.kubernetes.io/name','operator':'Exists'}]})
    assert not errors({'matchLabels':{'app.kubernetes.io/name':'example'}})
    assert errors({'matchLabels':{'app.kubernetes.io/name':'example','tier':'other'}})


@pytest.mark.parametrize('expression,accepted',[
    ({'key':'tier','operator':'In','values':['worker']},True),
    ({'key':'tier','operator':'In','values':['other']},False),
    ({'key':'tier','operator':'NotIn','values':['other']},True),
    ({'key':'tier','operator':'NotIn','values':['worker']},False),
    ({'key':'tier','operator':'Exists'},True),
    ({'key':'missing','operator':'DoesNotExist'},True),
    ({'key':'tier','operator':'DoesNotExist'},False),
    ({'key':'tier','operator':'Exists','values':['worker']},False),
    ({'key':'tier','operator':'In','values':[]},False),
    ({'key':'tier','operator':'Invalid'},False),
])
def test_complete_selector_matches_template(expression,accepted):
    assert (not errors({'matchLabels':{'app.kubernetes.io/name':'example'},'matchExpressions':[expression]})) == accepted
