from components.data_analyzer.analyzer import analyze, is_national_park, offers, percent, summary_lines
from components.test_support.fakes import ALERTS, PARKS


def test_percent_rounds_and_handles_zero_total():
    assert percent(1, 3) == 33
    assert percent(2, 3) == 67
    assert percent(5, 0) == 0


def test_offers_matches_activity_keywords_case_insensitively():
    redwood = next(p for p in PARKS if p["park_code"] == "redw")
    assert offers(redwood, "camping")
    assert offers(redwood, "HIKING")
    assert not offers(redwood, "boating")


def test_is_national_park_includes_joint_designations_only():
    designations = {p["park_code"]: is_national_park(p) for p in PARKS}
    assert designations == {"yell": True, "grte": True, "redw": True, "stli": False}


def test_analyze_computes_percentages_and_most_common_activity():
    result = analyze(PARKS, ALERTS)

    assert result["total_parks"] == 4
    assert result["camping_count"] == 3
    assert result["camping_percent"] == 75
    assert result["hiking_percent"] == 75
    assert result["alerts_count"] == 2
    assert result["alerts_percent"] == 50
    assert result["total_alerts"] == 3
    assert result["most_common_activity"] == "Hiking"
    assert result["top_activities"][0] == {"name": "Hiking", "count": 3, "percent": 75}
    assert result["top_states"][0] == {"state": "WY", "count": 2}
    assert result["average_activities"] == 2.8


def test_analyze_ignores_alerts_for_parks_outside_the_results():
    yellowstone_only = [p for p in PARKS if p["park_code"] == "yell"]
    result = analyze(yellowstone_only, ALERTS)
    assert result["alerts_count"] == 1
    assert result["total_alerts"] == 2
    assert {c["category"] for c in result["alert_categories"]} == {"Park Closure", "Caution"}


def test_analyze_empty_list():
    result = analyze([])
    assert result["total_parks"] == 0
    assert result["camping_percent"] == 0
    assert result["most_common_activity"] is None
    assert result["top_activities"] == []
    assert summary_lines(result) == ["No parks found."]


def test_summary_lines_reads_like_a_report():
    lines = summary_lines(analyze(PARKS, ALERTS))
    assert lines == [
        "4 parks found",
        "75% offer camping",
        "75% offer hiking",
        "50% have current alerts",
        "Most common activity: hiking",
    ]


def test_summary_lines_singular():
    assert summary_lines(analyze(PARKS[:1]))[0] == "1 park found"
