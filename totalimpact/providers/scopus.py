from totalimpact.providers import provider
from totalimpact.providers.provider import Provider, ProviderContentMalformedError

import simplejson, re, os, random, string, urllib

import logging
logger = logging.getLogger('ti.providers.scopus')

class Scopus(Provider):  

    example_id = ("doi", "10.1371/journal.pone.0000308")

    url = "http://www.info.sciverse.com/scopus/about"
    descr = "The world's largest abstract and citation database of peer-reviewed literature."
    # template urls below because they need a freshly-minted random string
    metrics_url_template = None
    provenance_url_template = "http://www.scopus.com/inward/record.url?partnerID=HzOxMe3b&scp=%s"

    static_meta_dict =  { 
        "citations": {
            "display_name": "citations",
            "provider": "Scopus",
            "provider_url": "http://www.info.sciverse.com/scopus/about",
            "description": "Number of times the item has been cited",
            "icon": "http://www.info.sciverse.com/sites/all/themes/sciverse/favicon.ico" ,
        }
    }
    

    def __init__(self):
        super(Scopus, self).__init__()

    def is_relevant_alias(self, alias):
        (namespace, nid) = alias
        return (namespace in ["doi", "biblio"])


    def _get_json(self, fullpage):
        try:
            # extract json from inside the first and last parens
            # from http://codereview.stackexchange.com/questions/2561/converting-jsonp-to-json-is-this-regex-correct
            page = fullpage[ fullpage.index("(")+1 : fullpage.rindex(")") ]
        except (AttributeError, ValueError):
            raise ProviderContentMalformedError()

        data = provider._load_json(page)
        return(data)



    def _extract_metrics(self, record, status_code=200, id=None):
        try:
            citations = int(record["citedby-count"])    
        except (KeyError, TypeError, ValueError):
            return {}

        if citations:
            metrics_dict = {"scopus:citations": citations}
        else:
            metrics_dict = {}                    
        return metrics_dict

    def _extract_provenance_url(self, record, status_code=200, id=None):
        try:
            api_url = record["prism:url"] 
            match = re.findall("scopus_id:([\dA-Z]+)", api_url)
            scopus_id = match[0]
            provenance_url = self._get_templated_url(self.provenance_url_template, scopus_id)
        except (KeyError, TypeError):
            provenance_url = ""
        return provenance_url

    def _get_page(self, url, headers={}):
        response = self.http_get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            if response.status_code == 404:
                return None
            else:
                raise(self._get_error(response.status_code, response))
        page = response.text
        if not page:
            raise ProviderContentMalformedError()
        return page

    def _extract_relevant_record(self, fullpage, id):
        data = provider._load_json(fullpage)
        response = None
        try:
            response = data["search-results"]["entry"][0]
        except (KeyError, ValueError):
            # not in Scopus database
            return None
        return response

    def _get_scopus_page(self, url):
        headers = {}
        headers["accept"] = "application/json"

        page = self._get_page(url, headers)
        if not page:
            logger.info(u"empty page with id {id}".format(id=id))
            return None
        if "Result set was empty" in page:
            #logger.warning(u"empty result set with doi {id}".format(id=id))
            return None
        return page


    def _get_relevant_record_with_doi(self, id):
        # pick a new random string so don't time out.  Unfort, url now can't cache.
        random_string = "".join(random.sample(string.letters, 10))
        url_template = "https://api.elsevier.com/content/search/index:SCOPUS?query=DOI(%s)&field=citedby-count&apiKey="+os.environ["SCOPUS_KEY"]+"&insttoken="+os.environ["SCOPUS_INSTTOKEN"]
        url = self._get_templated_url(url_template, id)

        page = self._get_scopus_page(url)

        if not page:
            return None  # empty result set

        relevant_record = self._extract_relevant_record(page, id)
        return relevant_record


    def _get_relevant_record_with_biblio(self, biblio_dict):
        random_string = "".join(random.sample(string.letters, 10))
        url_template = "https://api.elsevier.com/content/search/index:SCOPUS?query=AUTHOR-NAME({first_author})%20AND%20TITLE({title})%20AND%20SRCTITLE({journal})&field=citedby-count&apiKey="+os.environ["SCOPUS_KEY"]+"&insttoken="+os.environ["SCOPUS_INSTTOKEN"]
        try:        
            if not "first_author" in biblio_dict:
                biblio_dict["first_author"] = biblio_dict["authors"].split(" ")[0]
            url = url_template.format(
                    first_author=urllib.quote(biblio_dict["first_author"]), 
                    title=urllib.quote(biblio_dict["title"]), 
                    journal=urllib.quote(biblio_dict["journal"]))
        except KeyError:
            logger.debug("tried _get_relevant_record_with_biblio but leaving because KeyError")
            return None
        page = self._get_scopus_page(url)
        if not page:
            return None  # empty result set

        relevant_record = self._extract_relevant_record(page, biblio_dict)
        return relevant_record


    def _get_metrics_and_drilldown_from_metrics_page(self, provider_url_template, namespace, id):
        relevant_record = None
        if namespace=="doi":
            relevant_record = self._get_relevant_record_with_doi(id)
        elif namespace=="biblio":
            relevant_record = self._get_relevant_record_with_biblio(id)

        if not relevant_record:
            logger.info(u"no scopus page with id {id}".format(id=id))
            return {}

        metrics_dict = self._extract_metrics(relevant_record)
        
        metrics_and_drilldown = {}
        for metric_name in metrics_dict:
            drilldown_url = self._extract_provenance_url(relevant_record)
            metrics_and_drilldown[metric_name] = (metrics_dict[metric_name], drilldown_url)
        return metrics_and_drilldown  


    def get_best_alias(self, aliases_dict):
        for namespace in ["doi", "biblio"]:
            if namespace in aliases_dict:
                return (namespace, aliases_dict[namespace][0])
        return (None, None)

    # custom, because uses doi if available, else biblio
    def metrics(self, 
            aliases,
            provider_url_template=None,
            cache_enabled=True):

        aliases_dict = provider.alias_dict_from_tuples(aliases)
        (namespace, nid) = self.get_best_alias(aliases_dict)
        if not nid:
            #self.logger.debug(u"%s not checking metrics, no relevant alias" % (self.provider_name))
            return {}

        metrics_and_drilldown = self._get_metrics_and_drilldown_from_metrics_page(provider_url_template, 
                namespace=namespace, 
                id=nid)

        return metrics_and_drilldown
