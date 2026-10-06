from components.data_analyzer.suggestions import suggest

PARKS = [
    {"park_code": "grca", "name": "Grand Canyon National Park", "designation": "National Park", "states": ["AZ"]},
    {"park_code": "grte", "name": "Grand Teton National Park", "designation": "National Park", "states": ["WY"]},
    {"park_code": "glca", "name": "Glen Canyon National Recreation Area", "designation": "", "states": ["AZ", "UT"]},
    {"park_code": "pore", "name": "Point Reyes National Seashore", "designation": "", "states": ["CA"]},
    {"park_code": "bica", "name": "Bighorn Canyon National Recreation Area", "designation": "", "states": ["MT"]},
    {"park_code": "rigr", "name": "Rio Grande Wild & Scenic River", "designation": "", "states": ["TX"]},
    {"park_code": "pagr", "name": "Pagrand Test Site", "designation": "", "states": []},
]


def codes(results):
    return [r["park_code"] for r in results]


def test_matches_name_prefix_then_word_prefix_then_substring():
    assert codes(suggest(PARKS, "grand")) == ["grca", "grte", "rigr", "pagr"]


def test_is_case_and_whitespace_insensitive():
    assert codes(suggest(PARKS, "  GRAND   teton ")) == ["grte"]


def test_word_prefix_matches_inside_names():
    assert codes(suggest(PARKS, "canyon")) == ["bica", "glca", "grca"]


def test_short_queries_return_nothing():
    assert suggest(PARKS, "g") == []
    assert suggest(PARKS, " ") == []


def test_limit_and_returned_fields():
    results = suggest(PARKS, "national", limit=2)
    assert len(results) == 2
    assert set(results[0]) == {"park_code", "name", "designation", "states"}


def test_no_matches():
    assert suggest(PARKS, "zzz") == []
