"""Tests for provenance and partial upstream failures; never download media."""
import unittest
from unittest.mock import patch
from urllib.error import URLError
from preview_server import parse_public_image, fetch_station, PublisherRedirectHandler


class PublicCameraTests(unittest.TestCase):
    def test_time_is_explicitly_from_filename_with_thai_timezone(self):
        url, timestamp = parse_public_image(
            '<img src="cache/P.75/2026/10/cctv_20261006141503_abc123.jpg?t=5&amp;x=1" id="cctvImage">',
            "P.75",
        )
        self.assertEqual(url, "https://appserv.net/cache/P.75/2026/10/cctv_20261006141503_abc123.jpg")
        self.assertEqual(timestamp, "2026-10-06T14:15:03+07:00")

    def test_foreign_origin_private_url_and_wrong_station_rejected(self):
        for src in (
            "https://example.com/cache/P.75/2026/10/cctv_20261006141503_abc.jpg",
            "http://127.0.0.1/private.jpg",
            "https://appserv.net/cache/P.1/2026/10/cctv_20261006141503_abc.jpg",
            "https://appserv.net/cache/P.75/../../private.jpg",
        ):
            with self.subTest(src=src), self.assertRaises(ValueError):
                parse_public_image('<img id="cctvImage" src="' + src + '">', "P.75")

    def test_no_image_and_invalid_date_do_not_get_a_made_up_timestamp(self):
        for html in (
            "<p>camera offline</p>",
            '<img id="cctvImage" src="cache/P.75/2026/10/cctv_20261306141503_abc.jpg">',
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_public_image(html, "P.75")

    def test_upstream_failure_has_no_fake_image_or_capture_time(self):
        with patch("preview_server._opener.open", side_effect=URLError("offline")):
            camera = fetch_station(("P.75", "บ้านช่อแล", "อำเภอแม่แตง"))
        self.assertEqual(camera["status"], "unavailable")
        self.assertIsNone(camera["imageUrl"])
        self.assertIsNone(camera["capturedAt"])
        self.assertIsNone(camera["filenameTimestamp"])

    def test_redirect_cannot_fetch_another_host(self):
        with self.assertRaises(ValueError):
            PublisherRedirectHandler().redirect_request(
                None, None, 302, "Found", {}, "http://127.0.0.1/private"
            )


if __name__ == "__main__":
    unittest.main()
