from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.community_field import field_check_evaluation, summarize_field_checks


def check(id, outcome, method='on_site', match='matched', source='NASA VIIRS', **extra):
    data = {'outcome': outcome, 'method': method, 'satellite_match': match,
            'satellite_source': source if match == 'matched' else '', **extra}
    if match == 'matched':
        data['satellite_detected_at'] = '2026-10-10T10:00:00+00:00'
    return {'id': id, 'corrects_id': None, 'data': data}


def test_metrics_only_include_current_paired_on_site_records_and_no_ids():
    rows = [
        check('old', 'fire_found'),
        {**check('correction', 'no_fire_found'), 'corrects_id': 'old'},
        check('missed', 'fire_found', match='not_found'),
        check('phone', 'fire_found', method='phone'),
        check('unknown', 'unverified', match='not_checked'),
    ]
    result = summarize_field_checks(rows, now=datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert result['status'] == 'exploratory_pairs_available'
    assert result['record_count'] == 5
    assert result['active_record_count'] == 4
    assert result['paired_on_site_count'] == 2
    assert result['confusion_matrix'] == {'true_positive': 0, 'false_positive': 1, 'false_negative': 1, 'true_negative': 0}
    assert result['metrics_percent']['precision'] == 0
    assert result['metrics_percent']['recall'] == 0
    assert 'id' not in result and 'by_source' in result


def test_latency_uses_only_ordered_timestamps_and_empty_accuracy_stays_null():
    row = check('timing', 'unverified', match='not_checked',
                satellite_detected_at='2026-10-10T10:00:00+00:00',
                web_received_at='2026-10-10T10:05:00+00:00',
                email_delivered_at='2026-10-10T10:10:00+00:00',
                message_seen_at='2026-10-10T10:12:00+00:00')
    result = summarize_field_checks([row])
    assert result['paired_on_site_count'] == 0
    assert result['metrics_percent']['accuracy'] is None
    assert result['latency']['satellite_to_web'] == {'samples': 1, 'median_seconds': 300}
    assert result['latency']['email_delivered_to_seen'] == {'samples': 1, 'median_seconds': 120}


def test_accuracy_summary_is_admin_only_and_returns_aggregates_only():
    class Store:
        settings = object()
        def __init__(self, admin): self.admin=admin
        def rpc(self, action, payload, token): return {'is_admin':self.admin}
        def rows(self, table, **params):
            assert table == 'cme_field_checks'
            assert params['limit'] == '10000'
            return [check('private-id', 'fire_found')]
    with pytest.raises(HTTPException) as denied:
        field_check_evaluation((Store(False), 'fixture-token', {}))
    assert denied.value.status_code == 403
    result=field_check_evaluation((Store(True), 'fixture-token', {}))
    assert result['record_count'] == 1
    assert 'private-id' not in str(result)
