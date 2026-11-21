"""Read quality rules and check assessment coverage/integrity; never certify observations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

CATALOG=Path(__file__).resolve().parents[1]/'references/quality-rules.json'
LIMIT='Checks coverage and file integrity, not the truth of observations or product acceptance.'
FIELDS=('id','owner','title','applies_when','basis','requirement','exceptions','verification','required_evidence','severity','local_policy','implementation_status')

def read(path): return json.loads(Path(path).read_text('utf-8-sig'))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def nonempty(value): return isinstance(value,str) and bool(value.strip())

def catalog_errors(catalog):
    errors=[]
    if not isinstance(catalog,dict) or catalog.get('schema')!='luz-quality-rules/1':return ['Invalid catalog schema']
    sources=catalog.get('sources');rules=catalog.get('rules')
    if not isinstance(sources,dict) or not isinstance(rules,list) or not rules:return ['Catalog needs sources and rules']
    seen=set()
    for rule in rules:
        if not isinstance(rule,dict):errors.append('Invalid rule object');continue
        rid=rule.get('id')
        for field in FIELDS:
            if not nonempty(rule.get(field)):errors.append(f'{rid}: missing {field}')
        if not isinstance(rid,str):continue
        if rid in seen:errors.append(f'Duplicate rule {rid}')
        seen.add(rid)
        if not isinstance(rule.get('axes'),list) or not rule['axes'] or any(a not in {'UX','DX','AX'} for a in rule['axes']):errors.append(f'{rid}: invalid axes')
        if not isinstance(rule.get('stages'),list) or not rule['stages'] or not all(nonempty(x) for x in rule['stages']):errors.append(f'{rid}: invalid stages')
        metric=rule.get('metric')
        if not isinstance(metric,dict) or not all(nonempty(metric.get(f)) for f in ('target','unit')):errors.append(f'{rid}: missing metric target/unit')
        refs=rule.get('source_ids')
        if not isinstance(refs,list) or any(not isinstance(s,str) or s not in sources for s in refs):errors.append(f'{rid}: unknown source')
        if rule.get('basis') in {'standard','vendor','specification'} and not refs:errors.append(f'{rid}: external rule requires a source')
        if rule.get('severity') not in {'blocker','advisory'}:errors.append(f'{rid}: invalid severity')
    return errors

def select(catalog,owner=None,stage=None):
    # The joint design batch documents the contract; the following demo tests the rendered UI.
    return [rule for rule in catalog['rules']
            if (owner is None or rule['owner'] == owner)
            and (stage is None or stage in rule['stages']
                 or (stage == 'demo' and rule['owner'] == 'luz-design' and 'design' in rule['stages']))]

def plan(catalog,catalog_hash,owner,stage):
    return {'schema':'luz-quality-assessment/1','catalog_sha256':catalog_hash,'scope':{'owner':owner,'stage':stage},'limit':LIMIT,
            'rows':[{'rule_id':r['id'],'status':'pending','observed':'','reason':'','reviewer':'','evidence':[]} for r in select(catalog,owner,stage)]}

def check_assessment(report,catalog,catalog_hash,base):
    errors=catalog_errors(catalog)
    if errors:return errors
    if not isinstance(report,dict) or report.get('schema')!='luz-quality-assessment/1':return ['Invalid assessment schema']
    if report.get('catalog_sha256')!=catalog_hash:errors.append('Catalog changed; reassess affected rules')
    scope=report.get('scope')
    if not isinstance(scope,dict) or set(scope)!={'owner','stage'}:return errors+['Assessment needs exact owner/stage scope']
    if any(v is not None and not nonempty(v) for v in scope.values()):return errors+['Invalid scope']
    selected=select(catalog,scope['owner'],scope['stage'])
    if not selected:return errors+['Scope matches no rules; this is not a pass']
    wanted={r['id']:r for r in selected};rows=report.get('rows')
    if not isinstance(rows,list):return errors+['Missing rows']
    seen=set()
    for row in rows:
        if not isinstance(row,dict):errors.append('Invalid row');continue
        rid=row.get('rule_id')
        if not isinstance(rid,str) or rid not in wanted:errors.append('Unknown or out-of-scope rule');continue
        if rid in seen:errors.append(f'Duplicate {rid}')
        seen.add(rid);status=row.get('status')
        if status not in {'pass','fail','pending','not-applicable'}:errors.append(f'{rid}: unknown status');continue
        if status in {'pending','fail'} and wanted[rid]['severity']=='blocker':errors.append(f'{rid}: blocking {status}')
        if status=='not-applicable':
            if not nonempty(row.get('reason')) or not nonempty(row.get('reviewer')):errors.append(f'{rid}: not-applicable needs reason and reviewer')
            continue
        if status=='pass':
            if not nonempty(row.get('observed')) or not nonempty(row.get('reviewer')):errors.append(f'{rid}: pass needs actual observations and reviewer')
            refs=row.get('evidence')
            if not isinstance(refs,list) or not refs:errors.append(f'{rid}: pass needs evidence');continue
            for ref in refs:
                if not isinstance(ref,dict) or not nonempty(ref.get('path')) or not nonempty(ref.get('sha256')):errors.append(f'{rid}: invalid evidence');continue
                path=Path(ref['path']);path=path if path.is_absolute() else Path(base)/path
                if not path.is_file() or digest(path)!=ref['sha256']:errors.append(f'{rid}: missing or changed evidence {path}')
    if seen!=set(wanted):errors.append('Rule coverage is incomplete')
    return errors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['list','show','plan','check-catalog','check'])
    parser.add_argument('value',nargs='?');parser.add_argument('--owner');parser.add_argument('--stage');parser.add_argument('--out',type=Path)
    parser.add_argument('--catalog',type=Path,default=CATALOG)
    args=parser.parse_args()
    try:
        catalog=read(args.catalog);errors=catalog_errors(catalog)
        if errors:raise ValueError('; '.join(errors))
        if args.command=='list':result=select(catalog,args.owner,args.stage)
        elif args.command=='show':
            result=next((r for r in catalog['rules'] if r['id']==args.value),None)
            if result is None:raise ValueError('Unknown rule')
        elif args.command=='plan':
            result=plan(catalog,digest(args.catalog),args.owner,args.stage)
            if not result['rows']:raise ValueError('Scope matches no rules')
        elif args.command=='check-catalog':result={'ok':True,'rules':len(catalog['rules']),'limit':LIMIT}
        else:
            if not args.value:raise ValueError('check needs an assessment JSON')
            errors=check_assessment(read(args.value),catalog,digest(args.catalog),Path(args.value).resolve().parent)
            result={'ok':not errors,'errors':errors,'limit':LIMIT}
        text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.out:
            if args.command!='plan':raise ValueError('--out is only for a pending assessment plan')
            with args.out.open('x',encoding='utf-8') as stream:stream.write(text)
            print(str(args.out))
        else:print(text)
        return 1 if args.command=='check' and errors else 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
