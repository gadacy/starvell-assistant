"""Offline checks for Next.js reads; no real accounts or network calls."""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from starvell.client import StarvellClient


class NextDataTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = StarvellClient(api_key="test-session", base_url="https://starvell.test")
        self.client._build_id = "current-build"
        self.client._build_id_fetched_at = time.time()
        self.requests = []
        self.responses = []
        self.client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.respond), headers=self.client.headers,
        )
        self.sleep_patch = patch("starvell.client.asyncio.sleep", new_callable=AsyncMock)
        self.sleep = self.sleep_patch.start()
        self.warning_patch = patch("starvell.client.logger.warning")
        self.warning = self.warning_patch.start()
        self.addCleanup(self.sleep_patch.stop)
        self.addCleanup(self.warning_patch.stop)

    async def asyncTearDown(self):
        await self.client.close()

    def respond(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    @staticmethod
    def homepage(build_id="new-build"):
        data = {"buildId": build_id, "props": {"pageProps": {}}}
        return httpx.Response(200, text=f'<script id="__NEXT_DATA__">{json.dumps(data)}</script>')

    async def test_read_timeout_recovers_for_affected_endpoints(self):
        for path in ("chat/chat-1.json", "chat.json", "wallet.json", "index.json"):
            with self.subTest(path=path):
                self.requests.clear()
                payload = {"pageProps": {"messages": [{"id": "message-1"}]}}
                self.responses = [httpx.ReadTimeout(""), httpx.Response(200, json=payload)]

                self.assertEqual(await self.client.get_next_data(path), payload)
                self.assertEqual(len(self.requests), 2)
                self.assertEqual(self.requests[0].url, self.requests[1].url)
                self.assertEqual(self.requests[1].headers["x-nextjs-data"], "1")
                self.assertEqual(self.requests[1].headers["cookie"], "session=test-session")
                self.assertEqual(self.requests[1].extensions["timeout"]["read"], 30.0)
        self.warning.assert_not_called()

    async def test_transient_network_and_server_errors_recover(self):
        for failure in (
            httpx.ConnectError("connection reset"), httpx.RemoteProtocolError(""),
            httpx.Response(408), httpx.Response(500), httpx.Response(502),
            httpx.Response(503), httpx.Response(504),
        ):
            with self.subTest(failure=failure):
                self.requests.clear()
                self.responses = [failure, httpx.Response(200, json={"pageProps": {}})]
                self.assertEqual(await self.client.get_next_data("chat.json"), {"pageProps": {}})
                self.assertEqual(len(self.requests), 2)
        self.warning.assert_not_called()

    async def test_exhausted_timeout_has_nonempty_diagnostic_and_bounded_retries(self):
        self.responses = [httpx.ReadTimeout(""), httpx.ReadTimeout("")]
        self.assertEqual(await self.client.get_next_data("chat.json"), {})
        self.assertEqual(len(self.requests), 2)
        self.sleep.assert_awaited_once_with(1.0)
        self.warning.assert_called_once()
        self.assertIn("ReadTimeout", self.warning.call_args.args[0])
        self.assertIn("chat.json", self.warning.call_args.args[0])

    async def test_http_failures_report_status_and_do_not_retry_auth_or_rate_limits(self):
        for status, attempts in ((401, 1), (403, 1), (429, 1), (503, 2)):
            with self.subTest(status=status):
                self.requests.clear()
                self.warning.reset_mock()
                self.client._logged_errors.clear()
                self.responses = [httpx.Response(status) for _ in range(attempts)]
                self.assertEqual(await self.client.get_next_data("chat.json"), {})
                self.assertEqual(len(self.requests), attempts)
                self.warning.assert_called_once()
                self.assertIn(str(status), self.warning.call_args.args[0])

    async def test_stale_build_is_refreshed_and_original_request_is_retried(self):
        payload = {"pageProps": {"user": {"id": 12, "publicId": "public-12", "username": "Seller"}}}
        self.responses = [httpx.Response(404), self.homepage(), httpx.Response(200, json=payload)]

        self.assertEqual(await self.client.get_next_data("chat/chat-1.json"), payload)
        self.assertEqual([request.url.path for request in self.requests], [
            "/_next/data/current-build/chat/chat-1.json", "/",
            "/_next/data/new-build/chat/chat-1.json",
        ])
        self.assertEqual(self.client._build_id, "new-build")
        self.assertEqual((self.client.user_id, self.client.public_id, self.client.username),
                         ("12", "public-12", "Seller"))
        self.warning.assert_not_called()

    async def test_repeated_404_stops_after_one_build_refresh(self):
        self.responses = [httpx.Response(404), self.homepage(), httpx.Response(404)]
        self.assertEqual(await self.client.get_next_data("chat/missing.json"), {})
        self.assertEqual(len(self.requests), 3)
        self.assertIsNone(self.client._build_id)
        self.assertIn("404", self.warning.call_args.args[0])

    async def test_failed_build_discovery_does_not_request_default_build_and_can_recover(self):
        self.client._build_id = None
        self.responses = [httpx.ReadTimeout(""), httpx.ReadTimeout("")]
        self.assertEqual(await self.client.get_next_data("chat.json"), {})
        self.assertEqual([request.url.path for request in self.requests], ["/", "/"])
        self.assertIsNone(self.client._build_id)
        self.assertIn("ReadTimeout", self.warning.call_args.args[0])

        self.responses = [self.homepage(), httpx.Response(200, json={"pageProps": {}})]
        self.assertEqual(await self.client.get_next_data("chat.json"), {"pageProps": {}})
        self.assertNotIn("build_id_err", self.client._logged_errors)

    async def test_expired_build_is_preserved_if_homepage_temporarily_fails(self):
        self.client._build_id_fetched_at = time.time() - 1801
        self.responses = [httpx.ReadTimeout(""), httpx.ReadTimeout(""),
                          httpx.Response(200, json={"pageProps": {}})]
        self.assertEqual(await self.client.get_next_data("chat.json"), {"pageProps": {}})
        self.assertEqual(self.requests[-1].url.path, "/_next/data/current-build/chat.json")
        self.assertEqual(self.client._build_id, "current-build")

    async def test_invalid_build_discovery_is_reported_without_data_request(self):
        for response in (httpx.Response(200, text="<html>Unavailable</html>"), self.homepage(None)):
            with self.subTest(response=response):
                self.client._build_id = None
                self.client._logged_errors.clear()
                self.requests.clear()
                self.warning.reset_mock()
                self.responses = [response]
                self.assertEqual(await self.client.get_next_data("chat.json"), {})
                self.assertEqual(len(self.requests), 1)
                self.assertIn("ValueError", self.warning.call_args.args[0])
                self.assertIsNone(self.client._build_id)

    async def test_invalid_data_is_reported(self):
        for response, error in (
            (httpx.Response(200, text="<html>Unavailable</html>"), "JSONDecodeError"),
            (httpx.Response(200, json=[]), "ValueError"),
            (httpx.Response(200, json={"pageProps": None}), "ValueError"),
        ):
            with self.subTest(error=error):
                self.client._logged_errors.clear()
                self.requests.clear()
                self.warning.reset_mock()
                self.responses = [response]
                self.assertEqual(await self.client.get_next_data("chat.json"), {})
                self.assertEqual(len(self.requests), 1)
                self.assertIn(error, self.warning.call_args.args[0])

    async def test_error_is_logged_again_after_recovery(self):
        self.responses = [httpx.ReadTimeout("") for _ in range(4)] + [
            httpx.Response(200, json={"pageProps": {}}),
            httpx.ReadTimeout(""), httpx.ReadTimeout(""),
        ]
        for _ in range(4):
            await self.client.get_next_data("chat.json")
        self.assertEqual(self.warning.call_count, 2)

    async def test_cancellation_propagates_without_retry(self):
        self.responses = [asyncio.CancelledError()]
        with self.assertRaises(asyncio.CancelledError):
            await self.client.get_next_data("chat.json")
        self.assertEqual(len(self.requests), 1)
        self.sleep.assert_not_awaited()
        self.warning.assert_not_called()

    async def test_concurrent_build_discovery_uses_one_homepage_request(self):
        self.client._build_id = None
        started = asyncio.Event()
        release = asyncio.Event()

        async def respond(request):
            started.set()
            await release.wait()
            return self.respond(request)

        await self.client._client.aclose()
        self.client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.responses = [self.homepage()]
        first = asyncio.create_task(self.client.get_build_id())
        await started.wait()
        second = asyncio.create_task(self.client.get_build_id())
        release.set()
        self.assertEqual(await asyncio.gather(first, second), ["new-build", "new-build"])
        self.assertEqual(len(self.requests), 1)


if __name__ == "__main__":
    unittest.main()
