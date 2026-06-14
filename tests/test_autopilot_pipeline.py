import asyncio
import unittest
from unittest.mock import patch

from services.autopilot_service import AutoPilotService


class AutoPilotPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_project_run_is_skipped_and_lock_is_released(self):
        service = AutoPilotService()
        calls = []

        async def fake_run_workflow(keyword, project_id=None, config_dict=None):
            calls.append((keyword, project_id, config_dict))
            await asyncio.sleep(0.01)
            return {"status": "ok"}

        service.run_workflow = fake_run_workflow

        with patch("services.autopilot_service.log_debug"):
            first, second = await asyncio.gather(
                service.run_project_workflow("topic", project_id=123, config_dict={"a": 1}),
                service.run_project_workflow("topic", project_id=123, config_dict={"a": 1}),
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(first, {"status": "ok"})
        self.assertEqual(second, {"status": "skipped", "reason": "already_running"})
        self.assertEqual(service._active_project_ids, set())
        self.assertIsNone(service.current_project_id)

    async def test_different_projects_are_serialized(self):
        service = AutoPilotService()
        started = []
        finished = []

        async def fake_run_workflow(keyword, project_id=None, config_dict=None):
            started.append(project_id)
            await asyncio.sleep(0.01)
            finished.append(project_id)
            return project_id

        service.run_workflow = fake_run_workflow

        first, second = await asyncio.gather(
            service.run_project_workflow("first", project_id=1, config_dict={}),
            service.run_project_workflow("second", project_id=2, config_dict={}),
        )

        self.assertEqual((first, second), (1, 2))
        self.assertEqual(started, [1, 2])
        self.assertEqual(finished, [1, 2])
        self.assertEqual(service._active_project_ids, set())
        self.assertIsNone(service.current_project_id)

    def test_queue_status_exposes_worker_and_active_project_state(self):
        service = AutoPilotService()
        service.is_batch_running = True
        service.is_batch_worker_running = True
        service.current_project_id = 7
        service._active_project_ids.add(7)

        status = service.get_queue_status()

        self.assertTrue(status["is_running"])
        self.assertTrue(status["worker_running"])
        self.assertEqual(status["current_project_id"], 7)
        self.assertEqual(status["active_project_ids"], [7])
        self.assertIn("queued_count", status)
        self.assertIn("processing_count", status)


if __name__ == "__main__":
    unittest.main()
