import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from modules import (AgentCoordinator, build_smart_schedule,
                     predict_deadline_risk, read_selected_document,
                     search_personal_knowledge)


class TestAgentModules(unittest.TestCase):
    def test_deadline_risk_explains_basis(self):
        tasks = [{"id": 1, "title": "Exam prep", "due": "2026-10-25",
                  "estimated_minutes": 240, "status": "pending"}]
        result = predict_deadline_risk(tasks, 120, date(2026, 10, 25))
        self.assertEqual(result[0]["risk"], "high")
        self.assertTrue(result[0]["reason"])

    def test_schedule_avoids_commitment_and_reports_overflow(self):
        tasks = [{"id": 1, "title": "Study", "estimated_minutes": 60, "status": "pending"},
                 {"id": 2, "title": "Long task", "estimated_minutes": 600, "status": "pending"}]
        events = [{"title": "Class", "date": "2026-10-25", "start": "10:00", "end": "11:00"}]
        result = build_smart_schedule(tasks, events, date(2026, 10, 25), "09:00", "12:00", 0)
        task = next(block for block in result["blocks"] if block["kind"] == "task")
        self.assertNotEqual(task["start"], "10:00")
        self.assertEqual(result["unscheduled_task_ids"], [2])

    def test_knowledge_search_and_agent_coordination(self):
        rows = {"notes": [{"id": 1, "text": "review biology chapter"}]}
        self.assertEqual(search_personal_knowledge("biology", rows)[0]["id"], 1)
        result = AgentCoordinator().review([], 120)
        self.assertEqual(len(result["agents"]), 3)

    def test_document_reader_requires_approved_root(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            target = Path(folder) / "note.txt"
            target.write_text("private text", encoding="utf-8")
            self.assertEqual(read_selected_document(str(target), [folder])["text"], "private text")
            with self.assertRaises(PermissionError):
                read_selected_document(str(target), [other])


if __name__ == "__main__":
    unittest.main()
