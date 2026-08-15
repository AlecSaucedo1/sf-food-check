import time

from backend.taxonomy import parse_grouped_findings


HOUSE_OF_PRIME_RIB = (
    "114067(h), 114123, 114143(a, b), 114256-114256.2, 114256.4, "
    "114257-114257.1, 114259, 114259.2-114259.3, 114279, 114281, 114282 - "
    "Keep clean and free of litter or rubbish the premises of each food facility; "
    "the facility shall be kept vermin proof., "
    "114143(d), 114266, 114268, 114268.1, 114271, 114272 - "
    "Provide walls / ceilings using materials that are durable, smooth, nonabsorbent, "
    "light-colored, and washable surfaces."
)


def test_bounded_parser_preserves_current_datasf_grouping():
    items = parse_grouped_findings(HOUSE_OF_PRIME_RIB)
    assert len(items) == 2
    assert items[0]["code"].startswith("114067(h), 114123")
    assert "vermin proof" in items[0]["official_description"]
    assert items[1]["code"].startswith("114143(d), 114266")
    assert "walls / ceilings" in items[1]["official_description"]


def test_malformed_long_code_string_is_bounded():
    # Deliberately resembles a grouped finding but never supplies the ` - ` delimiter.
    # The former nested look-ahead parser could spend seconds backtracking across this.
    malformed = "114067(h), " + ("114123, " * 6000) + "unfinished finding"
    started = time.perf_counter()
    items = parse_grouped_findings(malformed)
    elapsed = time.perf_counter() - started

    assert items == []
    assert elapsed < 1.0, f"parser took {elapsed:.3f}s"
