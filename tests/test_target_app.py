"""
Tests for ApexCore 9.4 Legacy Banking Console Server.
"""

import urllib.request
import urllib.parse
import pytest
from src.target_app.server import ApexCoreServer


@pytest.fixture(scope="module")
def server():
    srv = ApexCoreServer(port=8091)
    url = srv.start()
    yield url
    srv.stop()


def test_search_page_served(server):
    with urllib.request.urlopen(f"{server}") as resp:
        content = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "ApexCore Enterprise Banking System" in content
        assert "ctl00$MainContent$txtMemberId" in content
        assert "Execute Inquiry" in content


def test_member_lookup_found(server):
    req = urllib.request.Request(
        f"{server}/member/search?ctl00$MainContent$txtMemberId=MEM-7701",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    # The server redirects with 302, urllib follows redirect
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "Alice Smith" in content
        assert "SAV-4091-88" in content
        assert "$14,250.80" in content


def test_member_lookup_not_found_business_outcome(server):
    req = urllib.request.Request(
        f"{server}/member/search?ctl00$MainContent$txtMemberId=MEM-9999",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "AC-404: Member Record [MEM-9999] not found" in content
