import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import frontdoor_discovery_bridge as bridge


PROVIDER_SCRIPT = r'''
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('mode', choices=['build','verify']); p.add_argument('--output', required=True); p.add_argument('--receipt', required=True); a=p.parse_args()
out=Path(a.output); receipt=Path(a.receipt)
if a.mode == 'build':
    out.write_bytes(b'portable-discovery-fixture')
    receipt.write_text(json.dumps({'artifact': {'network_required': False, 'runtime_dependencies': []}}), encoding='utf-8')
else:
    assert out.read_bytes() == b'portable-discovery-fixture'
    data=json.loads(receipt.read_text(encoding='utf-8'))
    assert data['artifact']['network_required'] is False
print('PASS')
'''

CONSUMER_SCRIPT = r'''
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--provider', required=True); p.add_argument('--provider-sha256', required=True); p.add_argument('--workspace', required=True); p.add_argument('--output', required=True); p.add_argument('--receipt', required=True); a=p.parse_args()
sha=hashlib.sha256(Path(a.provider).read_bytes()).hexdigest(); assert sha == a.provider_sha256
Path(a.output).write_text(json.dumps({
  'summary': {'capability_records': 1, 'ready_for_publication': 0, 'repositories': 1, 'requires_human_review': 1},
  'authority': {'publish': False, 'registry_write': False, 'merge': False, 'canon': False, 'release_approval': False}
}), encoding='utf-8')
Path(a.receipt).write_text(json.dumps({
  'schema':'axm.frontdoor.portable-discovery-intake/v0.1',
  'provider': {'artifact_sha256': sha, 'automatic_download': False}
}), encoding='utf-8')
print('frontdoor-portable-discovery-intake: PASS')
'''


class FrontDoorDiscoveryBridgeTests(unittest.TestCase):
    def build_snapshot(self, *, provider_commit=bridge.PROVIDER_COMMIT, consumer_commit=bridge.CONSUMER_COMMIT):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        provider = root / 'modules' / bridge.PROVIDER_MODULE
        consumer = root / 'modules' / bridge.CONSUMER_MODULE
        (provider / 'tools').mkdir(parents=True)
        (consumer / 'scripts').mkdir(parents=True)
        (provider / bridge.SOURCE_NAME).write_text(json.dumps({'repository': bridge.PROVIDER_REPOSITORY, 'commit': provider_commit}), encoding='utf-8')
        (consumer / bridge.SOURCE_NAME).write_text(json.dumps({'repository': bridge.CONSUMER_REPOSITORY, 'commit': consumer_commit}), encoding='utf-8')
        (provider / 'tools' / 'build_portable_discovery.py').write_text(textwrap.dedent(PROVIDER_SCRIPT), encoding='utf-8')
        (consumer / 'scripts' / 'portable_discovery_intake.py').write_text(textwrap.dedent(CONSUMER_SCRIPT), encoding='utf-8')
        return tmp, root

    def test_exact_selected_refs_execute_review_only_bridge(self):
        tmp, root = self.build_snapshot()
        self.addCleanup(tmp.cleanup)
        result = bridge.run(root)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['executed'])
        self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['intake_authority']['publish'])
        self.assertFalse(result['intake_authority']['registry_write'])
        self.assertFalse(result['source_snapshot_mutated'])

    def test_changed_provider_ref_holds_without_execution(self):
        tmp, root = self.build_snapshot(provider_commit='0' * 40)
        self.addCleanup(tmp.cleanup)
        result = bridge.run(root)
        self.assertEqual(result['status'], 'HOLD_PROVIDER_REF_MISMATCH')
        self.assertFalse(result['executed'])

    def test_changed_consumer_ref_holds_without_execution(self):
        tmp, root = self.build_snapshot(consumer_commit='0' * 40)
        self.addCleanup(tmp.cleanup)
        result = bridge.run(root)
        self.assertEqual(result['status'], 'HOLD_CONSUMER_REF_MISMATCH')
        self.assertFalse(result['executed'])


if __name__ == '__main__':
    unittest.main()
