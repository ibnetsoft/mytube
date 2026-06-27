import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class LongformScriptPlanAccessTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.cookies = {"user_email": "worker@example.com"}
        self.html_headers = {"accept": "text/html"}

    def _auth_patches(self, membership="std", email="worker@example.com", is_admin=False):
        return [
            patch("services.auth_service.auth_service.login_user"),
            patch("services.auth_service.auth_service.get_user_email", return_value=email),
            patch("services.auth_service.auth_service.get_membership", return_value=membership),
            patch("services.auth_service.auth_service.get_token_balance", return_value=0),
            patch("database.is_user_admin", return_value=is_admin),
        ]

    def test_longform_script_plan_renders_and_hides_music_specific_ui(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches():
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 10, "name": "Longform Project", "employee_email": "worker@example.com", "app_mode": "longform"}))
            stack.enter_context(patch("database.get_project_settings", return_value={"app_mode": "longform", "assigned_duration_minutes": 15, "estimated_payout": 4, "style_locked": "1", "duration_locked": "1"}))
            response = self.client.get("/script-plan?project_id=10", headers=self.html_headers, cookies=self.cookies)

        self.assertEqual(response.status_code, 200)
        self.assertIn("scriptStyleSelect", response.text)
        self.assertNotIn('<div id="nurseryIdeasPanel"', response.text)
        self.assertNotIn("style_nursery_rhyme", response.text)

    def test_music_project_redirects_to_music_plan_from_script_plan(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches(membership="pro"):
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 11, "name": "Music Project", "employee_email": "worker@example.com", "app_mode": "longform_music"}))
            stack.enter_context(patch("database.get_project_settings", return_value={"app_mode": "longform_music"}))
            response = self.client.get("/script-plan?project_id=11", headers=self.html_headers, cookies=self.cookies, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/music-plan?project_id=11")

    def test_longform_project_redirects_back_from_music_plan(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches(membership="pro"):
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 12, "name": "Longform Project", "employee_email": "worker@example.com", "app_mode": "longform"}))
            stack.enter_context(patch("database.get_project_settings", return_value={"app_mode": "longform"}))
            response = self.client.get("/music-plan?project_id=12", headers=self.html_headers, cookies=self.cookies, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/script-plan?project_id=12")

    def test_standard_member_cannot_enter_music_plan(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches(membership="std"):
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 13, "name": "Music Project", "employee_email": "worker@example.com", "app_mode": "longform_music"}))
            stack.enter_context(patch("database.get_project_settings", return_value={"app_mode": "longform_music"}))
            response = self.client.get("/music-plan?project_id=13", headers=self.html_headers, cookies=self.cookies, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/projects")

    def test_project_api_blocks_foreign_project_access(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches():
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 21, "name": "Foreign", "employee_email": "other@example.com", "app_mode": "longform"}))
            response = self.client.get("/api/projects/21")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Project access denied")

    def test_project_full_api_blocks_foreign_project_access(self):
        with ExitStack() as stack:
            for mocked in self._auth_patches():
                stack.enter_context(mocked)
            stack.enter_context(patch("database.get_project", return_value={"id": 22, "name": "Foreign", "employee_email": "other@example.com", "app_mode": "longform"}))
            response = self.client.get("/api/projects/22/full")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Project access denied")
