import sys
import json
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import agent

class TestADSPADailyAgent(unittest.TestCase):
    def setUp(self):
        agent.ensure_storage()

    def test_security_self_test(self):
        self.assertTrue(all(agent.run_security_self_test().values()))

    def test_plan_is_structured(self):
        plan = agent.daily_plan()
        self.assertIn("intention", plan)
        self.assertIn("recommended_steps", plan)

    def test_negotiation(self):
        result = agent.negotiate_study_session(90, 60)
        self.assertIn(result["status"], {"AGREEMENT_REACHED", "NO_AGREEMENT"})

    def test_invalid_priority(self):
        with self.assertRaises(ValueError):
            agent.add_task("bad task", priority="impossible")

    def test_natural_language_need_becomes_a_task(self):
        with patch.object(agent, "add_task", return_value={"id": 99, "title": "Buy groceries", "due": None}) as add:
            result = agent.web_chat_reply("I need to buy groceries")
        self.assertEqual(add.call_args.args[0], "Buy groceries")
        self.assertIn("added", result["reply"].lower())

    def test_short_followup_gets_contextual_clarification(self):
        response = agent.local_chat_fallback("what", [
            {"role": "user", "content": "I need to buy groceries"},
            {"role": "assistant", "content": "Added Buy groceries"},
            {"role": "user", "content": "what"},
        ])
        self.assertIn("buy groceries", response.lower())

    def test_yes_after_open_ended_greeting_prompts_for_choice(self):
        response = agent.local_chat_fallback("yes", [
            {"role": "assistant", "content": "Hi! What would you like to work on? I can help organize tasks, plan your day, or capture something you need to remember."},
            {"role": "user", "content": "yes"},
        ])
        self.assertIn("Which should we start with", response)
        self.assertIn("plan your day", response)

    def test_no_followup_acknowledges_without_action(self):
        response = agent.local_chat_fallback("no", [
            {"role": "assistant", "content": "Would you like me to add that task?"},
            {"role": "user", "content": "no"},
        ])
        self.assertIn("no changes made", response)

    def test_date_followup_updates_the_task_named_in_the_prior_turn(self):
        task = {"id": 7, "title": "Buy grocery", "due": None, "priority": "medium",
                "estimated_minutes": 30, "category": "personal"}
        history = [
            {"role": "user", "content": "I need to buy grocery"},
            {"role": "assistant", "content": "Got it — I added “Buy grocery” to your tasks. You can add a due date by saying ‘tomorrow’ or naming a day."},
            {"role": "user", "content": "tomorrow"},
        ]
        with patch.object(agent, "get_pending", return_value=[task]), \
             patch.object(agent, "update_task", return_value={**task, "due": (agent.date.today() + agent.timedelta(days=1)).isoformat()}) as update:
            result = agent.web_chat_reply("tomorrow", history)
        self.assertEqual(update.call_args.args[0], 7)
        self.assertEqual(update.call_args.args[2], (agent.date.today() + agent.timedelta(days=1)).isoformat())
        self.assertIn("due", result["reply"])

    def test_open_question_gets_honest_local_limit(self):
        response = agent.local_chat_fallback("What is the capital of France?")
        self.assertIn("can't reliably answer", response)

    def test_offline_responder_handles_common_questions_and_arithmetic(self):
        self.assertIn("Natural language processing", agent.local_chat_fallback("What is NLP?"))
        self.assertEqual(agent.local_chat_fallback("What is 18 / 3?"), "18 / 3 = 6")
        self.assertIn("25-minute timer", agent.local_chat_fallback("How can I focus?"))

    def test_ollama_provider_reads_local_chat_response(self):
        response = Mock()
        response.read.return_value = json.dumps({"message": {"content": "The answer is 42."}}).encode()
        manager = Mock()
        manager.__enter__ = Mock(return_value=response)
        manager.__exit__ = Mock(return_value=False)
        with patch.object(agent.urllib.request, "urlopen", return_value=manager) as urlopen:
            answer = agent.ollama_chat_reply("What is the answer?", [], "test-model")
        self.assertEqual(answer, "The answer is 42.")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertIn(b'"stream": false', request.data)

if __name__ == "__main__":
    unittest.main()
