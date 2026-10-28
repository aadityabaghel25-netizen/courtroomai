"""Full-text fetch for citations outside the library. Extractors and search are MOCKS; the verifier is real."""

from core.audit import ExtractedCitation, audit_one
from core.webfetch import clean_markdown, is_trusted, looks_like_the_judgment
from tests.helpers import stub_judge

HOLDING = "Arrest cannot be made in a routine manner merely because the offence is non-bailable and cognizable."
JUDGMENT = ("Mock Kumar vs State Of Example on 2 July, 2014. IN THE SUPREME COURT. " + "Background facts. " * 300
            + HOLDING + " The appeal is allowed.")
CITE = ExtractedCitation(case_name="Mock Kumar v. State of Example", citation="(2014) 8 SCC 999",
                         proposition="Police should not arrest routinely just because an offence is non-bailable.")


def search_with(urls):
    return lambda q: [{"url": u, "title": "Mock Kumar v State of Example", "content": "Mock Kumar State Example"} for u in urls]


def test_only_full_judgment_pages_on_trusted_hosts():
    assert is_trusted("https://indiankanoon.org/doc/2982624/")
    assert is_trusted("https://main.sci.gov.in/judgment/x.pdf")
    assert not is_trusted("https://indiankanoon.org/search/?formInput=x")
    assert not is_trusted("https://blog.ipleaders.in/arnesh-kumar")
    assert not is_trusted("https://evil-indiankanoon.org.example.com/doc/1/")


def test_markdown_is_cleaned_for_quote_matching():
    assert clean_markdown("[**Section 41**](https://x) of the Code") == "Section 41 of the Code"


def test_fetched_judgment_goes_through_the_same_checks():
    v = audit_one(0, CITE, store=_empty(), judge=stub_judge("supports", HOLDING),
                  web_search=search_with(["https://indiankanoon.org/doc/123/"]), extractor=lambda u: JUDGMENT)
    assert v.verdict == "verified" and v.fetched_from == "indiankanoon.org"
    assert "fetched from indiankanoon.org" in v.reason


def test_blog_page_is_never_fetched_or_trusted():
    calls = []
    v = audit_one(0, CITE, store=_empty(), judge=stub_judge("supports", HOLDING),
                  web_search=search_with(["https://someblog.example.com/mock-kumar"]),
                  extractor=lambda u: calls.append(u) or JUDGMENT)
    assert calls == [] and v.verdict == "found_online_unverified"


def test_judge_quote_missing_from_fetched_text_is_unverified():
    v = audit_one(0, CITE, store=_empty(), judge=stub_judge("supports", "Every accused must be released at once."),
                  web_search=search_with(["https://indiankanoon.org/doc/123/"]), extractor=lambda u: JUDGMENT)
    assert v.verdict == "unverified"


def test_page_that_is_not_the_cited_case_is_rejected():
    other = "Someone Else vs Another State on 1 Jan, 2010. " + "text " * 2000
    assert not looks_like_the_judgment(other, [["mock", "kumar"], ["example"]])
    v = audit_one(0, CITE, store=_empty(), judge=stub_judge("supports", HOLDING),
                  web_search=search_with(["https://indiankanoon.org/doc/123/"]), extractor=lambda u: other)
    assert v.verdict == "found_online_unverified"


def _empty():
    from core.judgments import JudgmentStore
    return JudgmentStore([])
