from app.config import Settings
from app.models import FieldReportSubmission
from app.providers import field_report_store as store
from app.services import submit_field_report, _load_field_reports


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _enabled_settings() -> Settings:
    return Settings(supabase_url="https://demo.supabase.co", supabase_service_role_key="svc-key")


def _submission() -> FieldReportSubmission:
    return FieldReportSubmission(
        forest_id="cf-mae-chaem-001",
        village_id="ban-mae-pan",
        reporter_hash="op-101",
        patrol_count=3,
        firebreak_km=1.5,
        no_burn_agreement=True,
    )


def test_supabase_enabled_requires_url_and_key():
    assert store.supabase_enabled(_enabled_settings()) is True
    assert store.supabase_enabled(Settings(supabase_url="https://x.supabase.co")) is False
    assert store.supabase_enabled(Settings()) is False


def test_submit_in_demo_mode_does_not_pretend_to_store():
    result = submit_field_report(Settings(), _submission())
    assert result.accepted is False
    assert result.stored is False
    assert result.source_mode == "UNAVAILABLE"
    assert "สาธิต" in result.message


def test_submit_rejects_unknown_forest_id(monkeypatch):
    # Validation happens before any network call, so no httpx mock is needed.
    def _no_network(*a, **k):  # pragma: no cover
        raise AssertionError("must reject unknown forest before touching the store")

    monkeypatch.setattr(store.httpx, "get", _no_network)
    monkeypatch.setattr(store.httpx, "post", _no_network)

    bad = FieldReportSubmission(
        forest_id="cf-not-a-real-forest",
        village_id="ban-x",
        reporter_hash="op-1",
    )
    result = submit_field_report(_enabled_settings(), bad)
    assert result.accepted is False
    assert result.stored is False
    assert "ทะเบียน" in result.message


def test_submit_inserts_when_no_report_today(monkeypatch):
    posted: dict = {}

    monkeypatch.setattr(store.httpx, "get", lambda *a, **k: _Resp([]))  # none today

    def _fake_post(url, json=None, headers=None, timeout=None):
        posted.update(json or {})
        return _Resp({}, status=201)

    monkeypatch.setattr(store.httpx, "post", _fake_post)

    result = submit_field_report(_enabled_settings(), _submission())
    assert result.accepted is True
    assert result.stored is True
    assert result.source_mode == "LIVE"
    # The persisted row carries the submission fields and a generated id/time.
    assert posted["forest_id"] == "cf-mae-chaem-001"
    assert posted["no_burn_agreement"] is True
    assert posted["id"].startswith("rpt-")
    assert "submitted_at" in posted


def test_submit_rejected_by_daily_rate_limit(monkeypatch):
    monkeypatch.setattr(store.httpx, "get", lambda *a, **k: _Resp([{"id": "rpt-existing"}]))

    def _post_should_not_run(*a, **k):  # pragma: no cover
        raise AssertionError("must not insert when a report already exists today")

    monkeypatch.setattr(store.httpx, "post", _post_should_not_run)

    result = submit_field_report(_enabled_settings(), _submission())
    assert result.accepted is False
    assert result.stored is False
    assert "1 ครั้ง" in result.message


def test_submit_409_from_db_unique_index_maps_to_rate_limit(monkeypatch):
    import httpx

    # Pre-check finds nothing, but the DB unique index rejects the insert with 409
    # (another report landed today). Must map to the friendly rate-limit message,
    # never bubble the raw HTTP error.
    monkeypatch.setattr(store.httpx, "get", lambda *a, **k: _Resp([]))

    def _conflict(url, json=None, headers=None, timeout=None):
        raise httpx.HTTPStatusError(
            "conflict",
            request=httpx.Request("POST", url),
            response=httpx.Response(409, request=httpx.Request("POST", url)),
        )

    monkeypatch.setattr(store.httpx, "post", _conflict)

    result = submit_field_report(_enabled_settings(), _submission())
    assert result.accepted is False
    assert result.stored is False
    assert "1 ครั้ง" in result.message


def test_load_field_reports_is_unavailable_without_supabase_by_default():
    reports, mode = _load_field_reports(Settings())
    assert mode == "UNAVAILABLE"
    assert reports == []


def test_load_field_reports_can_use_seed_when_prototypes_are_enabled():
    reports, mode = _load_field_reports(Settings(allow_prototype_data=True))
    assert mode == "PROTOTYPE"
    assert reports


def test_load_field_reports_uses_supabase_rows_when_configured(monkeypatch):
    rows = [
        {
            "id": "rpt-real-1",
            "forest_id": "cf-samoeng-001",
            "village_id": "ban-mae-sap",
            "reporter_hash": "op-900",
            "submitted_at": "2026-06-20T09:00:00+07:00",
            "patrol_count": 2,
            "committee_meeting": True,
            "no_burn_agreement": True,
        }
    ]
    monkeypatch.setattr(store.httpx, "get", lambda *a, **k: _Resp(rows))
    reports, mode = _load_field_reports(_enabled_settings())
    assert mode == "LIVE"
    assert reports[0].report_id == "rpt-real-1"
    assert reports[0].committee_meeting is True
