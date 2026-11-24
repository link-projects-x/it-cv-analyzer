import json

from scraper.dou import VacancyRef, _collect
from scraper.run import scrape
from scraper.stores import LocalRawStore

LIST_HTML = """
<a class="vt" href="https://jobs.dou.ua/companies/acme/vacancies/111/?from=list_hot">A</a>
<a class="vt" href="https://jobs.dou.ua/companies/acme/vacancies/111/">A again</a>
<a class="vt" href="https://jobs.dou.ua/companies/beta-co/vacancies/222/">B</a>
"""


class FakeClient:
    def __init__(self, refs, broken=()):
        self.refs = refs
        self.broken = set(broken)
        self.fetched = []

    def list_vacancies(self, category):
        return self.refs

    def fetch_vacancy(self, ref):
        self.fetched.append(ref.id)
        if ref.id in self.broken:
            raise OSError("timeout")
        return f"<html>{ref.id}</html>".encode()


REFS = [VacancyRef(f"dou-{i}", f"https://jobs.dou.ua/companies/x/vacancies/{i}/") for i in (1, 2, 3)]


def test_collect_dedupes_and_strips_query():
    refs = {}
    _collect(LIST_HTML, refs)
    assert list(refs) == ["dou-111", "dou-222"]
    assert refs["dou-111"].url == "https://jobs.dou.ua/companies/acme/vacancies/111/"


def test_scrape_stores_new_and_writes_metadata(tmp_path):
    store = LocalRawStore(tmp_path)
    result = scrape(FakeClient(REFS), store, "AI/ML", max_new=10)
    assert result.stored == ["dou-1", "dou-2", "dou-3"]
    meta = json.loads((tmp_path / "raw" / "dou-1.meta.json").read_text())
    assert meta["url"] == REFS[0].url and meta["category"] == "AI/ML" and meta["scraped-at"]


def test_scrape_skips_existing(tmp_path):
    store = LocalRawStore(tmp_path)
    scrape(FakeClient(REFS[:2]), store, "AI/ML", max_new=10)
    client = FakeClient(REFS)
    result = scrape(client, store, "AI/ML", max_new=10)
    assert result.skipped_existing == 2
    assert client.fetched == ["dou-3"]


def test_scrape_respects_max_new_and_time(tmp_path):
    result = scrape(FakeClient(REFS), LocalRawStore(tmp_path), "AI/ML", max_new=1)
    assert result.stored == ["dou-1"] and result.stopped_early

    result = scrape(FakeClient(REFS), LocalRawStore(tmp_path / "t"), "AI/ML", max_new=10, time_left_seconds=lambda: 5)
    assert result.stored == [] and result.stopped_early


def test_scrape_continues_after_fetch_error(tmp_path):
    result = scrape(FakeClient(REFS, broken={"dou-2"}), LocalRawStore(tmp_path), "AI/ML", max_new=10)
    assert result.stored == ["dou-1", "dou-3"]
    assert "dou-2" in result.failed
