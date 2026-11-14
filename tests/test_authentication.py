"""Tests for authentication and API requests without a Home Assistant runtime."""

import ast
from datetime import datetime
from html.parser import HTMLParser
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


class HomeAssistantError(Exception):
    pass


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = []
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))
        elif tag == "a":
            self.links.append(dict(attrs))

    def select_one(self, selector):
        return next((item for item in self.inputs if item.get("name") == "csrf_token"), None)

    def select(self, selector):
        return [link for link in self.links if "href" in link]


class Response:
    def __init__(self, session, path, body="", status=200, cookie=None):
        self.session = session
        self.url = SimpleNamespace(path=path)
        self.body = body
        self.status = status
        self.cookie = cookie

    async def __aenter__(self):
        if self.cookie:
            self.session.cookie = self.cookie
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self.body


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.cookie = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs, self.cookie))
        return Response(self, **next(self.responses))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def load_coordinator():
    """Load coordinator methods with Home Assistant interfaces stubbed."""
    const_path = ROOT / "custom_components/evohaus_parking/const.py"
    constants = {}
    exec(compile(const_path.read_text(), str(const_path), "exec"), constants)

    path = ROOT / "custom_components/evohaus_parking/coordinator.py"
    tree = ast.parse(path.read_text())
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EvohausDataUpdateCoordinator"
    )
    names = {
        "_clean_json_payload", "_is_authenticated_page", "async_login",
        "fetch_traffic_data", "fetch_meter_data",
    }
    methods = [
        node for node in coordinator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    module = ast.fix_missing_locations(ast.Module(
        body=[ast.ClassDef(name="Coordinator", bases=[], keywords=[], body=methods, decorator_list=[])],
        type_ignores=[],
    ))
    namespace = {
        **constants,
        "BeautifulSoup": lambda html, parser: PageParser(html),
        "HomeAssistantError": HomeAssistantError,
        "json": json,
        "urlsplit": urlsplit,
        "dt_util": SimpleNamespace(now=lambda: datetime(2026, 11, 14)),
        "_LOGGER": logging.getLogger("test.authentication"),
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["Coordinator"]


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.coordinator_class = load_coordinator()

    def coordinator(self, responses):
        coordinator = self.coordinator_class()
        coordinator._username = "example"
        coordinator._password = "example-password"
        coordinator._session = Session(responses)
        return coordinator

    async def test_login_and_api_requests_use_rotated_session_cookie(self):
        coordinator = self.coordinator([
            {"path": "/anmelden", "body": '<input name="csrf_token" value="token">', "cookie": "initial"},
            {"path": "/anmelden", "body": '<script>location.href="/start";</script>', "cookie": "authenticated"},
            {"path": "/start", "body": '<a href="/abmelden">Logout</a>'},
            {"path": "/api/ampel", "body": '{"color": "green"}', "cookie": "refreshed"},
            {"path": "/api/zaehlertabelle", "body": "<table></table>"},
        ])
        await coordinator.async_login()
        self.assertEqual(await coordinator.fetch_traffic_data(), {"color": "green"})
        await coordinator.fetch_meter_data()
        calls = coordinator._session.calls
        self.assertEqual(calls[0][:2], ("GET", "https://ems003.enocoo.com:48889/anmelden"))
        self.assertEqual(calls[1], (
            "POST", "https://ems003.enocoo.com:48889/anmelden?mode=ok",
            {"data": {"user": "example", "passwort": "example-password", "csrf_token": "token"}},
            "initial",
        ))
        self.assertEqual(calls[2], ("GET", "https://ems003.enocoo.com:48889/start", {}, "authenticated"))
        self.assertEqual(calls[3], ("GET", "https://ems003.enocoo.com:48889/api/ampel", {}, "authenticated"))
        self.assertEqual(calls[4], (
            "POST", "https://ems003.enocoo.com:48889/api/zaehlertabelle",
            {"data": {"dateParam": "2026-11-14"}}, "refreshed",
        ))

    async def test_missing_csrf_token_fails_without_posting_credentials(self):
        coordinator = self.coordinator([{"path": "/anmelden", "body": "<form></form>"}])
        with self.assertRaisesRegex(HomeAssistantError, "CSRF token"):
            await coordinator.async_login()
        self.assertEqual(len(coordinator._session.calls), 1)

    async def test_failed_login_is_not_treated_as_success(self):
        coordinator = self.coordinator([
            {"path": "/anmelden", "body": '<input name="csrf_token" value="token">'},
            {"path": "/anmelden", "body": "Ihre Anmeldedaten waren nicht korrekt."},
        ])
        with self.assertRaisesRegex(HomeAssistantError, "credentials were rejected"):
            await coordinator.async_login()

    async def test_start_page_without_authenticated_session_fails(self):
        coordinator = self.coordinator([
            {"path": "/anmelden", "body": '<input name="csrf_token" value="token">'},
            {"path": "/anmelden", "body": '<script>location.href="/start";</script>'},
            {"path": "/start", "body": "Sie sind nicht angemeldet"},
        ])
        with self.assertRaisesRegex(HomeAssistantError, "not authenticated"):
            await coordinator.async_login()

    async def test_http_failure_is_not_treated_as_success(self):
        coordinator = self.coordinator([{"path": "/anmelden", "status": 503}])
        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            await coordinator.async_login()

    async def test_existing_authenticated_session_does_not_submit_login(self):
        coordinator = self.coordinator([{"path": "/start", "body": '<a href="/abmelden">Logout</a>'}])
        await coordinator.async_login()
        self.assertEqual(len(coordinator._session.calls), 1)

    async def test_unexpected_start_page_after_login_page_redirect_fails(self):
        coordinator = self.coordinator([{"path": "/start", "body": "Sie sind nicht angemeldet"}])
        with self.assertRaisesRegex(HomeAssistantError, "not authenticated"):
            await coordinator.async_login()


if __name__ == "__main__":
    unittest.main()
