import unittest
from types import SimpleNamespace

from app.grounding import grounding_state_for


class GroundingStateSmokeTests(unittest.TestCase):
    def test_verified_sources_are_grounded(self):
        result = SimpleNamespace(
            blocked=False,
            intent='TEACHING',
            citations=['source-1'],
            citations_verified=True,
            hallucination_flag=False,
            answer_evidence=SimpleNamespace(source_count=1),
        )
        self.assertEqual(grounding_state_for(result), 'grounded')

    def test_missing_evidence_abstains(self):
        result = SimpleNamespace(
            blocked=False,
            intent='TEACHING',
            citations=[],
            citations_verified=None,
            hallucination_flag=False,
            answer_evidence=None,
        )
        self.assertEqual(grounding_state_for(result), 'abstained')

    def test_hallucination_flag_never_promotes_to_grounded(self):
        result = SimpleNamespace(
            blocked=False,
            intent='TEACHING',
            citations=['source-1'],
            citations_verified=True,
            hallucination_flag=True,
            answer_evidence=SimpleNamespace(source_count=1),
        )
        self.assertEqual(grounding_state_for(result), 'abstained')

    def test_blocked_and_crisis_responses_are_safety_redirects(self):
        blocked = SimpleNamespace(blocked=True, intent='TEACHING', citations=[])
        crisis = SimpleNamespace(blocked=False, intent='CRISIS', citations=[])
        self.assertEqual(grounding_state_for(blocked), 'safety_redirect')
        self.assertEqual(grounding_state_for(crisis), 'safety_redirect')

    def test_real_distress_and_safety_violation_intents_are_safety_redirects(self):
        """rag/nodes/intent.py only ever sets intent='DISTRESS' or 'SAFETY_VIOLATION' --
        never 'CRISIS'/'SAFETY'/'SELF_HARM'. A crisis-helpline response must not
        fall through to the evidence-based grounded/abstained branch."""
        distress = SimpleNamespace(blocked=False, intent='DISTRESS', citations=[])
        safety_violation = SimpleNamespace(blocked=False, intent='SAFETY_VIOLATION', citations=[])
        self.assertEqual(grounding_state_for(distress), 'safety_redirect')
        self.assertEqual(grounding_state_for(safety_violation), 'safety_redirect')


if __name__ == '__main__':
    unittest.main()
