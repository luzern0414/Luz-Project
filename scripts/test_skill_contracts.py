"""A maintenance check must detect a missing skill and a broken shared rule link."""
import tempfile
import unittest
from pathlib import Path
from skill_contracts import SKILLS, CONTRACTS, SKILL_LIMIT, entry_errors, mirror_errors


class ContractDriftTests(unittest.TestCase):
    def test_missing_entries_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(len(entry_errors(Path(temp))), len(SKILLS))

    def test_real_links_are_resolved_not_only_named(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, owner in CONTRACTS.items():
                folder = root / f'Luz-{owner}' / 'references'
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text('Offline rule fixture', encoding='utf-8')
            for name in SKILLS:
                folder = root / f'Luz-{name}'
                folder.mkdir(exist_ok=True)
                (folder / 'SKILL.md').write_text(f'---\nname: luz-{name.lower()}\ndescription: 测试入口\n---\n## 调用协议\n' +
                    '\n'.join(f'[规则](../Luz-{owner}/references/{contract})' for contract, owner in CONTRACTS.items()), encoding='utf-8')
            self.assertEqual(entry_errors(root), [])
            entry = root / 'Luz-Crawl' / 'SKILL.md'
            text = entry.read_text(encoding='utf-8')
            entry.write_text(text + '\n' + '细' * SKILL_LIMIT, encoding='utf-8')     # an entrypoint that grew a manual is reported
            errors = entry_errors(root)
            self.assertEqual(len(errors), 1, errors)
            self.assertTrue(errors[0].startswith('Crawl: SKILL.md has'), errors)
            contract, owner = next(iter(CONTRACTS.items()))
            (entry.parent / contract).write_text('Same name, stale rule', encoding='utf-8')
            entry.write_text(text.replace(f'../Luz-{owner}/references/{contract}', contract), encoding='utf-8')
            self.assertIn(f'must point to the Luz-{owner} contract', entry_errors(root)[0])
            entry.write_text(text, encoding='utf-8')
            (root / f'Luz-{owner}' / 'references' / contract).unlink()
            errors = entry_errors(root)
            self.assertEqual(len(errors), len(SKILLS))
            self.assertTrue(all('broken contract link' in error for error in errors))

    def test_changed_mirrors_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mirrors = {'owner.py': ['copy.py']}
            (root / 'owner.py').write_bytes(b'rule')
            (root / 'copy.py').write_bytes(b'rule')
            self.assertEqual(mirror_errors(root, mirrors), [])
            (root / 'copy.py').write_bytes(b'different')
            self.assertEqual(mirror_errors(root, mirrors), ['copy.py differs from owner.py; inspect changes before syncing'])
