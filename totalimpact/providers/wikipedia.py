import time
from provider import Provider, ProviderError, ProviderTimeout, ProviderServerError, ProviderClientError, ProviderHttpError, ProviderState, ProviderContentMalformedError, ProviderValidationFailedError
from BeautifulSoup import BeautifulStoneSoup
import requests

from totalimpact.tilogging import logging

class Wikipedia(Provider):  
    """ Gets numbers of citations for a DOI document from wikipedia using
        the Wikipedia search interface.
    """

    provider_name = "wikipedia"
    metric_names = ['wikipedia:mentions']
    metric_namespaces = ["doi"]
    alias_namespaces = ["doi"]

    member_types = None

    provides_members = False
    provides_aliases = False
    provides_metrics = True

    def __init__(self, config):
        super(Wikipedia, self).__init__(config)

    def metrics(self, aliases, logger):
        if len(aliases) != 1:
            logger.warn("More than 1 DOI alias found, this should not happen. Will process first item only.")
        
        (ns,val) = aliases[0] 

        logger.debug("looking for mentions of alias %s" % val)
        new_metrics = self.get_metrics_for_id(val, logger)

        return new_metrics
    
    def get_metrics_for_id(self, id, logger):
        # FIXME: urlencoding?
        url = self.config.metrics['url'] % id 
        logger.debug("attempting to retrieve metrics from " + url)
        
        # try to get a response from the data provider        
        response = self.http_get(url, timeout=self.config.metrics['timeout'], error_conf=self.config.errors)
        
        # client errors and server errors are not retried, as they usually 
        # indicate a permanent failure
        if response.status_code != 200:
            if response.status_code >= 500:
                raise ProviderServerError(response)
            else:
                raise ProviderClientError(response)
                    
        return self._extract_stats(response.text)

    
    def _extract_stats(self, content):
        try:
            soup = BeautifulStoneSoup(content)
        except:
            # seems this pretty much never gets called, as soup will happily
            # try to parse just about anything you throw at it.
            raise ProviderContentMalformedError("Content cannot be parsed into soup")
        
        try:
            articles = soup.search.findAll(title=True)
            val = len(articles)
        except AttributeError:
            # NOTE: this does not raise a ProviderValidationError, because missing
            # articles are not indicative of a formatting failure - there just might
            # not be any articles
            val = 0

        return {"wikipedia:mentions": val}
            
