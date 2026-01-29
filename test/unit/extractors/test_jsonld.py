
import pytest
from core import JsonLdExtractor

def test_extract_basic():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Software Engineer"
        }
        </script>
    </head>
    </html>
    """
    ld_list = JsonLdExtractor.extract(html)
    assert len(ld_list) == 1
    assert ld_list[0]["title"] == "Software Engineer"

def test_find_job_posting():
    ld_list = [
        {"@type": "Organization", "name": "Google"},
        {"@type": "JobPosting", "title": "AI Researcher"}
    ]
    job = JsonLdExtractor.find_job_posting(ld_list)
    assert job is not None
    assert job["title"] == "AI Researcher"

def test_extract_cdata():
    html = """
    <script type="application/ld+json">
    <![CDATA[
    {
        "@type": "JobPosting",
        "title": "CDATA Engineer"
    }
    ]]>
    </script>
    """
    ld_list = JsonLdExtractor.extract(html)
    assert len(ld_list) == 1
    assert ld_list[0]["title"] == "CDATA Engineer"
