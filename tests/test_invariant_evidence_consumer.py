import importlib.util
import json
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "import_invariant_packet.py"
spec = importlib.util.spec_from_file_location("import_invariant_packet", MODULE_PATH)
import_invariant_packet = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(import_invariant_packet)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "invariant-lab-counterexample-v0.1.json"


class InvariantEvidenceConsumerTests(unittest.TestCase):
    def packet(self):
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def raw(self, packet):
        return (json.dumps(packet, sort_keys=True) + "\n").encode("utf-8")

    def test_exact_donor_fixture_imports_as_evidence_only(self):
        result = import_invariant_packet.import_packet_bytes(FIXTURE_PATH.read_bytes())
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["invariant"], "INV-01-no-silent-authority-escalation")
        self.assertEqual(result["traceLength"], 2)
        self.assertEqual(result["effect"], "evidence_only_no_pipeline_status_change")
        self.assertFalse(any(result["authority"].values()))

    def test_authority_escalation_is_rejected(self):
        packet = self.packet()
        packet["authority"]["merge"] = True
        with self.assertRaises(import_invariant_packet.PacketError):
            import_invariant_packet.import_packet_bytes(self.raw(packet))

    def test_pass_is_not_rewritten_into_counterexample_semantics(self):
        packet = self.packet()
        packet["status"] = "PASS"
        with self.assertRaises(import_invariant_packet.PacketError):
            import_invariant_packet.import_packet_bytes(self.raw(packet))

    def test_unrecognized_fields_are_rejected(self):
        packet = self.packet()
        packet["verified"] = True
        with self.assertRaises(import_invariant_packet.PacketError):
            import_invariant_packet.import_packet_bytes(self.raw(packet))

    def test_hold_packet_is_preserved_as_hold(self):
        packet = self.packet()
        packet["status"] = "HOLD"
        packet["trace"] = []
        result = import_invariant_packet.import_packet_bytes(self.raw(packet))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["traceLength"], 0)

    def test_import_is_deterministic_for_identical_bytes(self):
        raw = FIXTURE_PATH.read_bytes()
        first = import_invariant_packet.stable_json(import_invariant_packet.import_packet_bytes(raw))
        second = import_invariant_packet.stable_json(import_invariant_packet.import_packet_bytes(raw))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
