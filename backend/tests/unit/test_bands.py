from app.domain.bands import band_ranges, level_for_score
from app.domain.states import Level


def test_bands_use_percentage_of_rubric_maximum() -> None:
    assert level_for_score(28, 30) == Level.HD
    assert level_for_score(85, 100) == Level.HD
    assert level_for_score(84.9, 100) == Level.DI
    assert level_for_score(13, 20) == Level.CR
    assert level_for_score(10, 20) == Level.PS
    assert level_for_score(4, 9) == Level.FL
    assert level_for_score(0, 0) == Level.FL


def test_band_ranges_cover_zero_to_hundred() -> None:
    ranges = band_ranges()
    assert ranges[0][2] == 100.0 and ranges[-1][1] == 0.0
    assert [level for level, _low, _high in ranges] == [Level.HD, Level.DI, Level.CR, Level.PS, Level.FL]
