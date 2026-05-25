import os
import unittest
from unittest.mock import patch

import xquik_research as research


class XquikResearchTest(unittest.TestCase):
    def test_api_key_uses_xquik_key_only(self):
        with patch.dict(os.environ, {"XQUIK_API_KEY": "xq_test"}, clear=True):
            self.assertEqual(research.api_key(), "xq_test")

    def test_build_url_encodes_query(self):
        with patch.dict(os.environ, {"XQUIK_BASE_URL": "https://example.com/"}, clear=True):
            self.assertEqual(
                research.build_url("/api/v1/x/tweets/search", {"q": "AI crypto", "limit": 5}),
                "https://example.com/api/v1/x/tweets/search?q=AI+crypto&limit=5",
            )

    def test_build_headers_supports_key_and_bearer(self):
        self.assertEqual(research.build_headers("xq_test"), {"Accept": "application/json", "x-api-key": "xq_test"})
        self.assertEqual(
            research.build_headers("Bearer token"),
            {"Accept": "application/json", "Authorization": "Bearer token"},
        )

    def test_tweet_list_handles_nested_payload(self):
        payload = {"data": {"results": [{"id": "1", "text": "hello"}]}}
        self.assertEqual(research.tweet_list(payload), [{"id": "1", "text": "hello"}])

    def test_normalize_tweet_maps_common_shape(self):
        tweet = research.normalize_tweet(
            {
                "id": "123",
                "full_text": "AI crypto agents need current X context.",
                "user": {"username": "example"},
                "public_metrics": {
                    "like_count": 9,
                    "retweet_count": 3,
                    "reply_count": 2,
                    "quote_count": 1,
                    "impression_count": "700",
                },
            },
            "AI crypto",
        )
        self.assertEqual(
            tweet,
            {
                "id": "123",
                "query": "AI crypto",
                "author": "@example",
                "text": "AI crypto agents need current X context.",
                "url": "https://x.com/example/status/123",
                "created_at": "",
                "likes": 9,
                "reposts": 3,
                "replies": 2,
                "quotes": 1,
                "views": 700,
            },
        )

    def test_markdown_mentions_verification(self):
        markdown = research.render_markdown([], "AI crypto")
        self.assertIn("Verify factual claims before publishing.", markdown)
        self.assertIn("No matching posts returned.", markdown)


if __name__ == "__main__":
    unittest.main()
