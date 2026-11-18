import copy,hashlib,sys
from pathlib import Path
sys.path.insert(0,r'D:\Codes\Luz-Project\scripts')
import quality_rules as q

def fixture(tmp_path):
    artifact=tmp_path/'actual.txt';artifact.write_text('real execution fixture','utf-8')
    catalog={'schema':'luz-quality-rules/1','sources':{},'rules':[{
        'id':'AX-01','axes':['AX'],'owner':'luz-dev','stages':['implementation'],
        'title':'Observable results','applies_when':'tools','basis':'local','requirement':'verify result',
        'metric':{'target':'0 missing results','unit':'count'},'exceptions':'none',
        'verification':'run the action','required_evidence':'actual result','source_ids':[],
        'severity':'blocker','local_policy':'local','implementation_status':'requires execution'}]}
    report=q.plan(catalog,'abc',None,None)
    row=report['rows'][0];row.update(status='pass',observed='Result checked against the fixture',reviewer='fixture reviewer',
        evidence=[{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}])
    return catalog,report,artifact

def test_initial_plan_is_not_a_pass(tmp_path):
    c,_,_=fixture(tmp_path)
    assert q.check_assessment(q.plan(c,'abc',None,None),c,'abc',tmp_path)

def test_bound_current_report_is_accepted_with_explicit_limit(tmp_path):
    c,r,_=fixture(tmp_path)
    assert q.check_assessment(r,c,'abc',tmp_path)==[]
    assert r['limit']=='Checks coverage and file integrity, not the truth of observations or product acceptance.'

def test_changed_catalog_invalidates_assessment(tmp_path):
    c,r,_=fixture(tmp_path)
    assert q.check_assessment(r,c,'changed',tmp_path)

def test_changed_evidence_invalidates_assessment(tmp_path):
    c,r,p=fixture(tmp_path);p.write_text('modified','utf-8')
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_pass_without_observation_or_evidence_is_rejected(tmp_path):
    c,r,_=fixture(tmp_path);r['rows'][0].update(observed='',evidence=[])
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_missing_or_duplicate_rule_cannot_hide_coverage(tmp_path):
    c,r,_=fixture(tmp_path);r['rows']*=2
    assert q.check_assessment(r,c,'abc',tmp_path)
    r['rows']=[]
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_not_applicable_requires_reason_and_reviewer(tmp_path):
    c,r,_=fixture(tmp_path);r['rows'][0].update(status='not-applicable',reason='',reviewer='')
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_unknown_scope_cannot_create_empty_pass(tmp_path):
    c,r,_=fixture(tmp_path);r['scope']['owner']='missing';r['rows']=[]
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_blocker_cannot_be_averaged_away(tmp_path):
    c,r,_=fixture(tmp_path);r['rows'][0]['status']='fail';r['score']=100
    assert q.check_assessment(r,c,'abc',tmp_path)

def test_catalog_requires_metric_and_valid_source(tmp_path):
    c,_,_=fixture(tmp_path)
    c['rules'][0]['source_ids']=['imaginary'];c['rules'][0].pop('metric')
    assert len(q.catalog_errors(c))>=2
