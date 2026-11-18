"""Bind component UI requirements to the project's current approved architecture.

The projection deliberately excludes unrelated later-stage ledger changes.
It checks existing approval records, never creates or authenticates approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import project_core as pc
import client_data as cd
from client_flow import effective_features


def _packaged_copy(root,path):
    """True for ui-requirements.json inside a package of a Design session that is linked to this project (its MANIFEST names this state root)."""
    if path.name!='ui-requirements.json': return False
    for parent in path.parents:
        manifest=parent/'raw'/'99-delivery'/'MANIFEST.json'
        if manifest.is_file():
            try: link=json.loads(manifest.read_text(encoding='utf-8-sig')).get('project')
            except (OSError,ValueError): return False
            state=link.get('state_root') if isinstance(link,dict) else None
            return bool(state) and Path(str(state)).resolve()==Path(root).resolve() and path.is_relative_to(parent/'raw')
    return False


def binding(root,requirements_path):
    root=pc.resolve_state_root(root);requirements_path=Path(requirements_path).resolve()
    manifest=pc.load_project(root)
    stage=next((s for s in manifest.get('stages',[]) if s.get('id')=='architecture'),{})
    if stage.get('status') not in {'approved','completed'}: raise ValueError('System architecture is not approved')
    artifacts=[a for a in pc._load_artifacts(root) if a.get('stage')=='architecture']
    contract_kinds={'frontend-spec','ui-requirements'}
    matches=[a for a in artifacts if a.get('kind') in contract_kinds
             and pc.locate(root,a['path']).resolve()==requirements_path]
    if not matches and _packaged_copy(root,requirements_path):
        # A frontend.py package carries the contract it was sealed against; it stands for the registered artifact only when its bytes equal it.
        digest=pc.sha256_file(requirements_path)
        matches=[a for a in artifacts if a.get('kind') in contract_kinds and pc.locate(root,a['path']).is_file()
                 and pc.sha256_file(pc.locate(root,a['path']))==digest]
        if len(matches)==1: requirements_path=pc.locate(root,matches[0]['path']).resolve()
    if len(matches)!=1: raise ValueError('UI requirements must be the registered architecture artifact, not an unregistered copy')
    hashes={}
    for item in artifacts:
        path=pc.locate(root,item['path'])
        if not path.is_file() or pc.sha256_file(path)!=item.get('sha256'): raise ValueError('Architecture artifact changed: '+item['path'])
        hashes[item['id']]=item['sha256']
    requirements_sha=pc.sha256_file(requirements_path)
    if (manifest.get('approval_policy') or {}).get('model')=='document':
        import approval_docs
        ctx=approval_docs.Ctx(root)
        if not approval_docs.stage_complete(ctx,'architecture',allow_pre=False):
            raise ValueError('Current architecture documents and sources do not have effective human approvals')
        approved=[]
        requirements_bound=False
        for document in approval_docs.documents(root,'architecture'):
            status=approval_docs.document_status(ctx,document)
            grant,problem=approval_docs.effective_record(ctx,'document',document=document['path'])
            if (status['state']!='approved' or problem is not None or not grant
                    or grant.get('id')!=status.get('record') or grant.get('stage')!='architecture'
                    or grant.get('project_id')!=manifest.get('project_id')
                    or not grant.get('approver') or not grant.get('note')):
                raise ValueError('Architecture document approval is not current for this project')
            approved.append(dict(grant))
            # Only a current approved document or its exact source path binds
            # this artifact. Equal bytes at another path, historical records,
            # and artifact IDs without an approved path are not sufficient.
            references={grant['document']:grant.get('hash'),**(grant.get('source_hashes') or {})}
            requirements_bound= requirements_bound or any(
                '#' not in path and pc.locate(root,path).resolve()==requirements_path and digest==requirements_sha
                for path,digest in references.items())
        if not requirements_bound:
            raise ValueError('Current architecture approval does not bind the exact UI requirements path and hash')
    else:
        grant=next((r for r in pc._load_approvals(root)['approvals'] if r.get('id')==stage.get('approval_id')),None)
        if (not grant or grant.get('status','approved')!='approved' or grant.get('stage')!='architecture'
                or grant.get('project_id')!=manifest.get('project_id')
                or not grant.get('approver') or not grant.get('note')
                or stage.get('approved_hashes')!=hashes or grant.get('artifact_hashes')!=hashes):
            raise ValueError('Current architecture approval does not bind all artifacts and its human record')
        approved=[grant]
    requirements=json.loads(requirements_path.read_text(encoding='utf-8-sig'))
    features=effective_features(root,cd.load_features(root))
    wanted={f['id'] for f in features};actual={f['id'] for f in requirements.get('features',[])}
    if wanted!=actual: raise ValueError('UI requirements differ from effective project scope; missing='+str(sorted(wanted-actual))+'; extra='+str(sorted(actual-wanted)))
    projection={'project_id':manifest.get('project_id'),'requirements':{'path':str(requirements_path),'sha256':requirements_sha},
                'architecture_artifacts':hashes,'architecture_approvals':approved,
                'effective_features':features,'validator_sha256':pc.sha256_file(Path(__file__))}
    digest=hashlib.sha256(json.dumps(projection,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'sha256':digest,'projection':projection}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project');parser.add_argument('requirements')
    args=parser.parse_args()
    try:
        print(json.dumps(binding(args.project,args.requirements),ensure_ascii=False));return 0
    except (OSError,ValueError,TypeError,KeyError,pc.ProjectError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__': raise SystemExit(main())
