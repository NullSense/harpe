from harpe import rank
from harpe.models import Candidate


def test_relevance_beats_resolution():
    # A huge but irrelevant scan must rank below a smaller exact match.
    big_wrong = Candidate(area=10**9, title="Mona Lisa", artist="Leonardo")
    small_right = Candidate(area=10**6, title="The Last Day of Pompeii",
                            artist="Karl Bryullov")
    out = rank.rank("the last day of pompeii bryullov", [big_wrong, small_right])
    assert out[0] is small_right


def test_strong_match_trims_noise():
    good = Candidate(area=10**6, title="Moses Breaketh the Tables",
                     artist="John Martin", spec="url:a")
    noise = Candidate(area=10**9, title="Nude on a Table", artist="John Currin",
                      spec="url:b")
    out = rank.rank("moses breaketh the tables john martin", [good, noise])
    assert good in out
    assert noise not in out          # floor drops the zero/low-relevance item


def test_weak_query_keeps_everything():
    a = Candidate(area=10**6, title="Sunset", spec="url:a")
    b = Candidate(area=10**5, title="Sunrise", spec="url:b")
    out = rank.rank("art", [a, b])   # single weak token -> floor 0
    assert len(out) == 2


def test_dedup_by_spec():
    a = Candidate(area=10**6, title="X", spec="url:same")
    b = Candidate(area=10**5, title="X", spec="url:same")
    out = rank.rank("x", [a, b])
    assert out == [a]                # larger kept, duplicate dropped


def test_bigger_scan_of_same_work_first():
    small = Candidate(area=10**6, title="The Deluge", artist="Martin", spec="url:s")
    large = Candidate(area=10**8, title="The Deluge", artist="Martin", spec="url:l")
    out = rank.rank("the deluge martin", [small, large])
    assert out[0] is large


def test_tokens_drops_stopwords_and_short_words():
    assert rank.tokens("The Last Day of Pompeii") == ["last", "day", "pompeii"]


def test_tokens_lowercases_and_splits_punctuation():
    assert rank.tokens("Moses-Breaketh: Tables!") == ["moses", "breaketh", "tables"]
