from __future__ import annotations

import os
import unittest

os.environ.setdefault("API_AUTH_ENABLED", "false")

from fastapi.testclient import TestClient

from backend.main import create_app


class DesktopShellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.client.close()

    def test_root_redirects_to_picks(self) -> None:
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/picks")

    def test_desktop_page_is_served(self) -> None:
        response = self.client.get("/picks")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/vue/assets/", response.text)

    def test_unknown_routes_use_desktop_shell(self) -> None:
        response = self.client.get("/unknown-route")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/vue/assets/", response.text)


if __name__ == "__main__":
    unittest.main()
