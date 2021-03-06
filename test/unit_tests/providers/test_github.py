from test.unit_tests.providers import common
from test.unit_tests.providers.common import ProviderTestCase
from totalimpact.providers.provider import Provider, ProviderContentMalformedError
from test.utils import http

import os
import collections
from nose.tools import assert_equals, raises

datadir = os.path.join(os.path.split(__file__)[0], "../../../extras/sample_provider_pages/github")
SAMPLE_EXTRACT_METRICS_PAGE = os.path.join(datadir, "metrics")
SAMPLE_EXTRACT_ALIASES_PAGE = os.path.join(datadir, "aliases")
SAMPLE_EXTRACT_MEMBER_ITEMS_PAGE = os.path.join(datadir, "members")
SAMPLE_EXTRACT_BIBLIO_PAGE = os.path.join(datadir, "biblio")

class TestGithub(ProviderTestCase):

    provider_name = "github"

    testitem_members = "egonw"
    testitem_aliases = ("url", "https://github.com/egonw/cdk")
    testitem_metrics = ("url", "https://github.com/egonw/cdk")
    testitem_biblio = ("url", "https://github.com/egonw/cdk")
    testitem_biblio_org = ("url", "https://github.com/openphacts/BridgeDb")

    def setUp(self):
        ProviderTestCase.setUp(self) 

    def test_is_relevant_alias(self):
        # ensure that it matches an appropriate ids
        assert_equals(self.provider.is_relevant_alias(self.testitem_aliases), True)

        assert_equals(self.provider.is_relevant_alias(("doi", "NOT A GITHUB ID")), False)
  
    def test_extract_metrics_success(self):
        f = open(SAMPLE_EXTRACT_METRICS_PAGE, "r")
        metrics_dict = self.provider._extract_metrics(f.read())
        print metrics_dict
        assert_equals(metrics_dict["github:stars"], 33)

    def test_extract_members_success(self):        
        f = open(SAMPLE_EXTRACT_MEMBER_ITEMS_PAGE, "r")
        members = self.provider._extract_members(f.read(), self.testitem_members)
        assert len(members) >= 30, (len(members), members)

    def test_provenance_url(self):
        provenance_url = self.provider.provenance_url("github:forks", [self.testitem_aliases])
        assert_equals(provenance_url, "https://github.com/egonw/cdk/network/members")

        # Not the same as above
        provenance_url = self.provider.provenance_url("github:stars", [self.testitem_aliases])
        assert_equals(provenance_url, "https://github.com/egonw/cdk/stargazers")

    @http
    def test_metrics(self):
        metrics_dict = self.provider.metrics([self.testitem_metrics])
        print metrics_dict
        expected = {'github:forks': (20, 'https://github.com/egonw/cdk/network/members'), 'github:stars': (25, 'https://github.com/egonw/cdk/stargazers')}
        for key in expected:
            assert metrics_dict[key][0] >= expected[key][0], [key, metrics_dict[key], expected[key]]
            assert metrics_dict[key][1] == expected[key][1], [key, metrics_dict[key], expected[key]]

    @http
    def test_metrics_github_namespace_deprecated_after_v1(self):
        metrics_dict = self.provider.metrics([("github", "egonw,cdk")])
        print metrics_dict
        expected = {'github:forks': (20, 'https://github.com/egonw/cdk/network/members'), 'github:stars': (25, 'https://github.com/egonw/cdk/stargazers')}
        for key in expected:
            assert metrics_dict[key][0] >= expected[key][0], [key, metrics_dict[key], expected[key]]
            assert metrics_dict[key][1] == expected[key][1], [key, metrics_dict[key], expected[key]]

    @http
    def test_biblio(self):
        biblio_dict = self.provider.biblio([self.testitem_biblio_org])
        print biblio_dict
        expected = {'last_push_date': u'2013-01-08T06:09:29Z', 'create_date': u'2012-01-18T10:49:04Z', 'title': u'BridgeDb', 'url': u'https://github.com/openphacts/BridgeDb', 'year': u'2012', 'owner': u'openphacts'}
        assert_equals(biblio_dict.keys(), expected.keys())
        for key in ["url", "owner", "title", "create_date", "year"]:
            assert_equals(biblio_dict[key], expected[key])

