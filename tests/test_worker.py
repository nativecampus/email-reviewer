from unittest.mock import patch


class TestGetQueue:
    @patch.dict("os.environ", {"REDIS_URL": ""}, clear=False)
    def test_returns_none_when_redis_url_empty(self):
        # Re-import to pick up patched env
        from app.worker import get_queue

        assert get_queue() is None

    @patch.dict("os.environ", {"REDIS_URL": ""}, clear=False)
    def test_redis_available_false_when_redis_url_empty(self):
        from app.worker import redis_available

        assert redis_available() is False
