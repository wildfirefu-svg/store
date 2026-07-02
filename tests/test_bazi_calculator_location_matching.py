import bazi_calculator as bc


def test_malaysia_chinese_location_matches_kuala_lumpur():
    hour, minute, delta, method = bc.calculate_true_solar_time(8, 12, "马来西亚", 1)

    assert (hour, minute) == (6, 50)
    assert delta == -81
    assert method == "longitude_correction"
    assert bc._solar_time_last_info["longitude"] == 101.687
    assert bc._solar_time_last_info["tz_offset"] == 8


def test_malaysia_english_location_does_not_match_la_alias():
    bc.calculate_true_solar_time(8, 12, "Malaysia", 1)

    assert bc._solar_time_last_info["longitude"] == 101.687
    assert bc._solar_time_last_info["tz_offset"] == 8


def test_la_short_alias_still_matches_los_angeles():
    bc.calculate_true_solar_time(8, 12, "LA", 1)

    assert bc._solar_time_last_info["longitude"] == -118.244
    assert bc._solar_time_last_info["tz_offset"] == -8
