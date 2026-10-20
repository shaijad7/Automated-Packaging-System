import pytest
from unittest.mock import patch, MagicMock
import requests
from config import settings


class TestAPIClientAndAuth:
    """Test suite for Phase 9 & Phase 10: Event payload transmission, auth headers, and HTTP error handling."""

    def test_api_key_header_construction(self):
        """Headers must include X-API-Key with the configured EDGE_NODE_API_KEY."""
        headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}
        assert "X-API-Key" in headers
        assert headers["X-API-Key"] == settings.EDGE_NODE_API_KEY
        assert len(headers["X-API-Key"]) > 0

    @patch("requests.post")
    def test_successful_event_submission(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        event_payload = {
            "event_id": "test-uuid-1234",
            "timestamp": "2026-10-11T18:00:00Z",
            "track_id": 1,
            "qr_status": "VALID_QR",
            "qr_payload": "INV|ADP-001",
            "count_direction": "A_TO_B"
        }

        headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}
        response = requests.post(
            f"{settings.BACKEND_API_URL}/api/events/",
            json=event_payload,
            headers=headers,
            timeout=5.0
        )
        assert response.status_code == 200
        mock_post.assert_called_once_with(
            f"{settings.BACKEND_API_URL}/api/events/",
            json=event_payload,
            headers=headers,
            timeout=5.0
        )

    @patch("requests.post")
    def test_ambiguous_event_submission(self, mock_post):
        """AMBIGUOUS qr_status is serializable and accepted by the event contract."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        event_payload = {
            "event_id": "test-uuid-5678",
            "timestamp": "2026-10-11T18:00:00Z",
            "track_id": 2,
            "qr_status": "AMBIGUOUS",
            "qr_payload": None,
            "count_direction": "B_TO_A"
        }

        headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}
        response = requests.post(
            f"{settings.BACKEND_API_URL}/api/events/",
            json=event_payload,
            headers=headers,
            timeout=5.0
        )
        assert response.status_code == 200

    @patch("requests.post")
    def test_http_401_error_handling(self, mock_post):
        """Tests that a 401 response is accurately captured without crashing unhandled."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        http_err = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_err
        mock_post.return_value = mock_resp

        headers = {"X-API-Key": "WRONG_KEY"}
        response = requests.post(
            f"{settings.BACKEND_API_URL}/api/events/",
            json={},
            headers=headers
        )
        assert response.status_code == 401

    @patch("requests.post")
    @patch("time.sleep", return_value=None)
    def test_worker_bounded_401_retries_and_preservation(self, mock_sleep, mock_post):
        """Worker limits 401 retries to MAX_AUTH_RETRIES and preserves the unauthenticated event."""
        import threading
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        test_event = {"event_id": "test-auth-401-fail", "track_id": 99}
        run_pipeline.preserved_events.clear()
        run_pipeline.running = True
        run_pipeline.event_queue.put(test_event)

        worker_thread = threading.Thread(target=run_pipeline.event_worker, daemon=True)
        worker_thread.start()

        # Wait for queue to finish processing the item without deadlock
        run_pipeline.event_queue.join()
        run_pipeline.running = False
        worker_thread.join(timeout=1.0)

        assert mock_post.call_count == run_pipeline.MAX_AUTH_RETRIES
        assert test_event in run_pipeline.preserved_events
        assert run_pipeline.event_queue.empty()

    @patch("requests.post")
    @patch("time.sleep", return_value=None)
    def test_worker_queue_bookkeeping_no_deadlock(self, mock_sleep, mock_post):
        """Ensure event_queue.join() never deadlocks on auth failures or mixed outcomes."""
        import threading
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        run_pipeline.preserved_events.clear()
        run_pipeline.running = True
        events = [{"event_id": f"evt-{i}", "track_id": i} for i in range(3)]
        for evt in events:
            run_pipeline.event_queue.put(evt)

        worker_thread = threading.Thread(target=run_pipeline.event_worker, daemon=True)
        worker_thread.start()

        # queue.join() must complete without hanging
        run_pipeline.event_queue.join()
        run_pipeline.running = False
        worker_thread.join(timeout=1.0)

        assert len(run_pipeline.preserved_events) == 3
        assert run_pipeline.event_queue.empty()


class TestProductionWorkerAcknowledgementHardening:
    """Regression test suite for Phase 5.8.1B: Strict validation of backend acknowledgement contract.

    Exercises the actual production delivery worker (run_pipeline.event_worker and main.event_worker)
    and validate_acknowledgement helper against fresh, isolated SQLite spools under tmp_path.
    Verifies that unexpected HTTP 200 responses, malformed JSON, HTML, non-dict payloads,
    and HTTP/network errors never trigger spool.mark_delivered() and preserve events in SQLite.
    """

    @pytest.fixture(autouse=True)
    def setup_isolated_spool(self, tmp_path, monkeypatch):
        import run_pipeline
        from spool import EventSpool

        self.db_path = tmp_path / "worker_test_spool.db"
        self.spool = EventSpool(self.db_path)
        monkeypatch.setattr(run_pipeline, "spool", self.spool)
        run_pipeline.preserved_events.clear()

        while not run_pipeline.event_queue.empty():
            try:
                run_pipeline.event_queue.get_nowait()
                run_pipeline.event_queue.task_done()
            except Exception:
                pass

        yield

        run_pipeline.running = False
        try:
            self.spool.close()
        except Exception:
            pass

    def _sample_payload(self, event_id: str = "evt-ack-test-001"):
        return {
            "event_id": event_id,
            "timestamp": "2026-10-21T00:00:00Z",
            "track_id": 42,
            "qr_status": "VALID_QR",
            "qr_payload": "INV|PROD-001",
            "count_direction": "A_TO_B",
        }

    def _run_worker_with_event(self, event_payload, stop_on_backoff=True):
        import threading
        import run_pipeline

        self.spool.enqueue(event_payload)
        run_pipeline.event_queue.put(event_payload)
        run_pipeline.running = True

        def sleep_hook(seconds):
            if stop_on_backoff:
                run_pipeline.running = False

        with patch("time.sleep", side_effect=sleep_hook):
            worker_thread = threading.Thread(target=run_pipeline.event_worker, daemon=True)
            worker_thread.start()
            run_pipeline.event_queue.join()
            run_pipeline.running = False
            worker_thread.join(timeout=2.0)

    # 1. Valid acknowledgements
    @patch("requests.post")
    def test_worker_valid_event_recorded_marks_delivered(self, mock_post):
        """HTTP 200 with {'msg': 'Event recorded'} removes event from spool."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"msg": "Event recorded"}
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-valid-recorded-01")
        self._run_worker_with_event(payload)

        assert self.spool.get_event("evt-valid-recorded-01") is None
        assert self.spool.get_pending_count() == 0
        assert payload not in run_pipeline.preserved_events
        assert run_pipeline.event_queue.empty()

    @patch("requests.post")
    def test_worker_valid_event_already_processed_marks_delivered(self, mock_post):
        """HTTP 200 with {'msg': 'Event already processed'} preserves idempotent delivery."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"msg": "Event already processed"}
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-valid-duplicate-02")
        self._run_worker_with_event(payload)

        assert self.spool.get_event("evt-valid-duplicate-02") is None
        assert self.spool.get_pending_count() == 0
        assert payload not in run_pipeline.preserved_events
        assert run_pipeline.event_queue.empty()

    # 2. Invalid HTTP 200 acknowledgements
    @patch("requests.post")
    def test_worker_http_200_error_payload_does_not_mark_delivered(self, mock_post):
        """HTTP 200 with {'error': 'failure'} must NOT mark delivered and keep event in spool."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"error": "failure"}
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-err-payload-03")
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event("evt-err-payload-03")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Unexpected acknowledgement body" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in run_pipeline.preserved_events
        assert run_pipeline.event_queue.empty()

    @patch("requests.post")
    def test_worker_http_200_unexpected_msg_does_not_mark_delivered(self, mock_post):
        """HTTP 200 with unexpected msg text must NOT mark delivered."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"msg": "Batch queued"}
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-unexpected-msg-04")
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event("evt-unexpected-msg-04")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Unexpected acknowledgement body" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in run_pipeline.preserved_events

    @patch("requests.post")
    def test_worker_http_200_malformed_json_does_not_mark_delivered(self, mock_post):
        """HTTP 200 with malformed JSON body must NOT mark delivered."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-malformed-json-05")
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event("evt-malformed-json-05")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Invalid JSON in backend response" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in run_pipeline.preserved_events

    @patch("requests.post")
    def test_worker_http_200_html_or_empty_body_does_not_mark_delivered(self, mock_post):
        """HTTP 200 with HTML or empty string body must NOT mark delivered."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.text = "<html><body>502 Bad Gateway</body></html>"
        mock_resp.json.side_effect = ValueError("No JSON object could be decoded")
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-html-body-06")
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event("evt-html-body-06")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Invalid JSON in backend response" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in run_pipeline.preserved_events

    @pytest.mark.parametrize("invalid_json_value", [
        ["Event recorded"],
        "Event recorded",
        None,
        123,
    ])
    @patch("requests.post")
    def test_worker_http_200_non_dict_json_does_not_mark_delivered(self, mock_post, invalid_json_value):
        """HTTP 200 with non-object JSON values (list, string, null, int) must NOT mark delivered."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = invalid_json_value
        mock_post.return_value = mock_resp

        evt_id = f"evt-non-dict-{type(invalid_json_value).__name__}"
        payload = self._sample_payload(evt_id)
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event(evt_id)
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Unexpected acknowledgement body" in record["last_error"]
        assert self.spool.get_pending_count() == 1

    @patch("requests.post")
    def test_worker_http_200_missing_or_non_string_msg_does_not_mark_delivered(self, mock_post):
        """HTTP 200 with integer or missing msg field must NOT mark delivered."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"msg": 12345}
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-int-msg-07")
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event("evt-int-msg-07")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Unexpected acknowledgement body" in record["last_error"]
        assert self.spool.get_pending_count() == 1

    # 3. HTTP errors and retry behavior
    @patch("requests.post")
    def test_worker_http_401_preserves_auth_failed_and_does_not_mark_delivered(self, mock_post):
        """HTTP 401 preserves AUTH_FAILED status and never marks delivered."""
        import run_pipeline

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-auth-failed-08")
        self._run_worker_with_event(payload, stop_on_backoff=False)

        record = self.spool.get_event("evt-auth-failed-08")
        assert record is not None
        assert record["status"] == "AUTH_FAILED"
        assert record["attempts"] == run_pipeline.MAX_AUTH_RETRIES
        assert "401" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in run_pipeline.preserved_events

    @pytest.mark.parametrize("status_code,err_title", [
        (422, "422 Unprocessable Entity"),
        (500, "500 Internal Server Error"),
    ])
    @patch("requests.post")
    def test_worker_http_errors_preserve_event_for_retry(self, mock_post, status_code, err_title):
        """HTTP 422 and 500 errors must leave event in PENDING status in spool."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(err_title, response=mock_resp)
        mock_post.return_value = mock_resp

        evt_id = f"evt-http-{status_code}-09"
        payload = self._sample_payload(evt_id)
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event(evt_id)
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert str(status_code) in record["last_error"]
        assert self.spool.get_pending_count() == 1

    @pytest.mark.parametrize("exception_cls,err_msg", [
        (requests.exceptions.ConnectTimeout, "Connection timed out"),
        (requests.exceptions.ConnectionError, "Failed to establish a new connection"),
    ])
    @patch("requests.post")
    def test_worker_network_errors_preserve_event_and_stable_id(self, mock_post, exception_cls, err_msg):
        """Network timeouts and connection errors preserve the exact event ID and payload."""
        mock_post.side_effect = exception_cls(err_msg)

        evt_id = f"evt-network-{exception_cls.__name__}-10"
        payload = self._sample_payload(evt_id)
        self._run_worker_with_event(payload, stop_on_backoff=True)

        record = self.spool.get_event(evt_id)
        assert record is not None
        assert record["event_id"] == evt_id
        assert record["payload"]["track_id"] == 42
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert self.spool.get_pending_count() == 1

    # 4. Consistency across both production files
    @patch("requests.post")
    def test_main_pipeline_worker_acknowledgement_validation(self, mock_post, monkeypatch):
        """cv_pipeline/main.py event_worker also validates acknowledgement body and preserves spool."""
        import threading
        import main

        monkeypatch.setattr(main, "spool", self.spool)
        main.preserved_events.clear()
        while not main.event_queue.empty():
            try:
                main.event_queue.get_nowait()
                main.event_queue.task_done()
            except Exception:
                pass

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"status": "ok"}  # Missing expected 'msg'
        mock_post.return_value = mock_resp

        payload = self._sample_payload("evt-main-worker-11")
        self.spool.enqueue(payload)
        main.event_queue.put(payload)
        main.running = True

        def sleep_hook(seconds):
            main.running = False

        with patch("time.sleep", side_effect=sleep_hook):
            worker_thread = threading.Thread(target=main.event_worker, daemon=True)
            worker_thread.start()
            main.event_queue.join()
            main.running = False
            worker_thread.join(timeout=2.0)

        record = self.spool.get_event("evt-main-worker-11")
        assert record is not None
        assert record["status"] == "PENDING"
        assert record["attempts"] == 1
        assert "Unexpected acknowledgement body" in record["last_error"]
        assert self.spool.get_pending_count() == 1
        assert payload in main.preserved_events
        assert main.event_queue.empty()

    # 5. Direct unit test of validate_acknowledgement helper
    def test_validate_acknowledgement_contract_matrix(self):
        """Direct unit verification of validate_acknowledgement edge cases."""
        from run_pipeline import validate_acknowledgement

        # Valid cases
        for valid_msg in ("Event recorded", "Event already processed"):
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status.return_value = None
            r.json.return_value = {"msg": valid_msg}
            res = validate_acknowledgement(r)
            assert res["msg"] == valid_msg

        # Invalid cases raise RequestException
        invalid_bodies = [
            {"error": "failure"},
            {"msg": "Unknown"},
            {"msg": 123},
            {},
            ["Event recorded"],
            "Event recorded",
            None,
        ]
        for invalid_body in invalid_bodies:
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status.return_value = None
            r.json.return_value = invalid_body
            with pytest.raises(requests.exceptions.RequestException):
                validate_acknowledgement(r)

        # JSON decode failure raises RequestException
        r_malformed = MagicMock()
        r_malformed.status_code = 200
        r_malformed.raise_for_status.return_value = None
        r_malformed.json.side_effect = ValueError("Malformed JSON")
        with pytest.raises(requests.exceptions.RequestException):
            validate_acknowledgement(r_malformed)

        # HTTP error status raises HTTPError (RequestException subclass)
        r_http_err = MagicMock()
        r_http_err.status_code = 500
        r_http_err.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Error")
        with pytest.raises(requests.exceptions.RequestException):
            validate_acknowledgement(r_http_err)
