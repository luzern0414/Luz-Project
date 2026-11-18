"""Read-only, sequential drift check for the seven local Luz entrypoints and rule cards.

Does not claim semantic correctness or replace each skill's regression tests.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILLS = ('Project', 'System', 'Design', 'Dev', 'Ops', 'Writing', 'Crawl')
CONTRACTS = {
    'skill-architecture.md': 'Project',
    'evidence-policy.md': 'Crawl',
    'document-evidence.md': 'Design',
}
MIRRORS = {
    'Luz-Design/scripts/make_summary.py': [f'Luz-{name}/scripts/make_summary.py' for name in SKILLS if name != 'Design'],
    'Luz-Design/scripts/check_output_layout.py': [f'Luz-{name}/scripts/check_output_layout.py' for name in SKILLS if name != 'Design'],
    'Luz-Design/scripts/estimate_terms.py': [f'Luz-{name}/scripts/estimate_terms.py' for name in ('Project', 'System', 'Writing')],
    'Luz-System/references/handoff.schema.json': ['Luz-Dev/contracts/handoff.schema.json'],
}
CARDS = {'System': 'context.py', 'Design': 'context.py', 'Dev': 'context.py', 'Writing': '06-context.py'}
COMMON_RULES = '## 用户的共同硬规则'  # every rule card opens with this section of skill-architecture.md
# An entrypoint is read on every call: protocol, routing and hard limits only; the detail lives in references and rule cards.
SKILL_LIMIT = 8000


def entry_errors(codes: Path) -> list[str]:
    errors = []
    for name in SKILLS:
        file = codes / f'Luz-{name}' / 'SKILL.md'
        if not file.is_file():
            errors.append(f'{name}: missing SKILL.md')
            continue
        content = file.read_text(encoding='utf-8-sig')
        header = content.split('---', 2)[1] if content.startswith('---\n') else ''
        if not re.search(rf'^name:\s*luz-{name.lower()}\s*$', header, re.M):
            errors.append(f'{name}: wrong skill name')
        if not re.search(r'^description:\s*\S.+$', header, re.M) or '## 调用协议' not in content:
            errors.append(f'{name}: missing trigger or invocation protocol')
        if len(content) > SKILL_LIMIT:
            errors.append(f'{name}: SKILL.md has {len(content)} characters, over {SKILL_LIMIT}; move detail into references or rule cards')
        for contract, owner in CONTRACTS.items():
            expected = (codes / f'Luz-{owner}' / 'references' / contract).resolve()
            matches = re.findall(r'\]\(([^)\n]*' + re.escape(contract) + r')\)', content)
            if not matches:
                errors.append(f'{name}: missing shared contract link {contract}')
            for target in matches:
                resolved = (file.parent / target).resolve()
                if not resolved.is_file():
                    errors.append(f'{name}: broken contract link {target}')
                elif resolved != expected:
                    errors.append(f'{name}: {target} must point to the Luz-{owner} contract')
    return errors


def mirror_errors(codes: Path, mirrors: dict[str, list[str]]) -> list[str]:
    errors = []
    for canonical, replicas in mirrors.items():
        owner = codes / canonical
        if not owner.is_file():
            errors.append(f'Missing canonical file: {canonical}')
            continue
        content = owner.read_bytes()
        for replica in replicas:
            copy = codes / replica
            if not copy.is_file() or copy.read_bytes() != content:
                errors.append(f'{replica} differs from {canonical}; inspect changes before syncing')
    return errors


def check(codes: Path, *, registration: bool = True) -> dict:
    checks = [
        {'name': 'shared-entrypoints', 'errors': entry_errors(codes)},
        {'name': 'shared-mirrors', 'errors': mirror_errors(codes, MIRRORS)},
    ]
    architecture = codes / 'Luz-Project/references/skill-architecture.md'
    common = architecture.read_text(encoding='utf-8-sig') if architecture.is_file() else ''
    checks.append({'name': 'common-rules', 'errors': [] if COMMON_RULES in common.splitlines() else
                   [f'skill-architecture.md lost the section {COMMON_RULES}; the rule cards print it first']})
    commands = [(f'{name}-cards', codes / f'Luz-{name}' / 'scripts' / script, ['check']) for name, script in CARDS.items()]
    # The rule-card core and the notes store are one block each, copied into four skills from the Luz-Design master.
    commands.append(('shared-code-blocks', codes / 'Luz-Design/scripts/sync_rule_core.py', ['--check']))
    if registration:
        commands.append(('managed-registration', codes / 'Luz-Dev/scripts/register_skills.py', ['--check']))
    for name, script, args in commands:
        try:
            result = subprocess.run([sys.executable, '-X', 'utf8', str(script), *args],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
            checks.append({'name': name, 'exit_code': result.returncode,
                           'errors': [] if result.returncode == 0 else [(result.stdout + result.stderr)[-8000:]],
                           'result': result.stdout.strip()[-2000:]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({'name': name, 'errors': [str(exc)]})
    return {'ok': not any(row['errors'] for row in checks), 'checks': checks,
            'scope': '入口、共享链接、共同硬规则、规则卡解析、共享代码块与注册一致性；不证明来源语义、产品行为或视觉质量。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codes', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--skip-registration', action='store_true', help='For a portable copy without this machine registration')
    args = parser.parse_args(argv)
    result = check(args.codes, registration=not args.skip_registration)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
