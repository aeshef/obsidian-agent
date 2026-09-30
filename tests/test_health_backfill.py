from datetime import date
import pytest
from planning_bot.services.iphone_health_fields import extract_raw_fields, normalize_raw_fields, is_valid_health_snapshot
from planning_bot.services.snapshot_query import latest_per_calendar_day
from planning_bot.services.iphone_context_parser import week_numeric_aggregates, parse_iphone_file
from planning_bot.tools.iphone_mail_sync import _snap_filename, _snap_to_txt


def revision(captured="2026-09-12T12:00:00+03:00", group="nutrition", **fields):
    body = dict(ts="2026-09-01T00:00:00+03:00", schema_version="2", measurement_day="2026-09-01",
                captured_at=captured, metric_group=group, read_status="ok", **fields)
    snap = normalize_raw_fields({k:str(v) for k,v in body.items()})
    # Loader normalizes ts for shared queries.
    snap["ts"] = "2026-09-01T00:00:00"
    return snap


def test_revisions_are_per_group_and_order_independent():
    old = {"ts":"2026-09-01T22:00:00", "calories_kcal":900,"steps":1234,"weight_kg":70,"hrv_ms":40}
    new = revision(calories_kcal=2200)
    earlier = revision(captured="2026-09-11T12:00:00+03:00", calories_kcal=1800)
    for rows in ([old,new,earlier], [earlier,new,old]):
        day = latest_per_calendar_day(rows)[date(2026,9,1)]
        assert day["calories_kcal"] == 2200
        assert day["steps"] == 1234
        assert day["captured_at"] == new["captured_at"]


def test_empty_is_unknown_failed_read_does_not_erase():
    old=revision(calories_kcal=2200)
    newer=revision(captured="2026-09-13T12:00:00+03:00",empty_fields="calories_kcal")
    assert is_valid_health_snapshot(newer)
    assert latest_per_calendar_day([old,newer])[date(2026,9,1)]["calories_kcal"] is None
    newer["read_status"]="failed"
    assert not is_valid_health_snapshot(newer)
    assert latest_per_calendar_day([old,newer])[date(2026,9,1)]["calories_kcal"] == 2200


def test_week_stats_do_not_weight_repeated_exports():
    a=revision(calories_kcal=1000)
    b=revision(captured="2026-09-13T12:00:00+03:00",calories_kcal=2000)
    c={"ts":"2026-09-02T22:00:00","calories_kcal":3000}
    assert week_numeric_aggregates([a,b,c])["calories_kcal"]["avg"] == 2500


def test_mail_disk_roundtrip_keeps_measurement_day_and_revisions(tmp_path):
    texts=[]
    for captured,value in [("2026-09-12T12:00:00+03:00",1000),("2026-09-13T12:00:00+03:00",2000)]:
        snap=revision(captured=captured,calories_kcal=value)
        snap["ts"]="01.09.2026, 00:00"
        path=tmp_path/_snap_filename(snap)
        path.write_text(_snap_to_txt(snap)); texts.append(parse_iphone_file(path))
    assert len(list(tmp_path.glob('*.txt'))) == 2
    assert latest_per_calendar_day(texts)[date(2026,9,1)]["calories_kcal"] == 2000


def test_unknown_group_or_clear_is_rejected():
    assert not is_valid_health_snapshot(revision(group="other",calories_kcal=1))
    assert not is_valid_health_snapshot(revision(empty_fields="steps"))


def test_partial_revisions_preserve_fields_in_any_arrival_order():
    earlier=revision(calories_kcal=1000, proteins_g=100)
    newer=revision(captured="2026-09-13T12:00:00+03:00",calories_kcal=2000)
    for rows in ([earlier,newer], [newer,earlier]):
        day=latest_per_calendar_day(rows)[date(2026,9,1)]
        assert day['calories_kcal']==2000
        assert day['proteins_g']==100


@pytest.mark.parametrize('value',['nan','inf',-1])
def test_invalid_numeric_correction_is_rejected(value):
    assert not is_valid_health_snapshot(revision(calories_kcal=value))


def test_conflicting_empty_and_numeric_is_rejected():
    assert not is_valid_health_snapshot(revision(calories_kcal=1,empty_fields='calories_kcal'))


def test_latest_view_uses_merged_revision_and_actual_capture_time():
    from planning_bot.services.snapshot_query import latest_snapshot,captured_at_dt
    old={"ts":"2026-09-01T23:00:00","calories_kcal":500,"steps":1000,"hrv_ms":30,"weight_kg":70}
    new=revision(calories_kcal=2000)
    snap=latest_snapshot([old,new])
    assert snap['calories_kcal']==2000
    assert snap['steps']==1000
    assert captured_at_dt(snap).isoformat()==new['captured_at']
