from totalimpact.config import Configuration
from totalimpact.cache import Cache
import requests, os, time, threading

from totalimpact.tilogging import logging
logger = logging.getLogger(__name__)

class ProviderFactory(object):

    @classmethod
    def get_provider(cls, provider_definition, config):
        """ Create an instance of a Provider object
        
            provider_definition is a dictionary which states the class and config file
            which should be used to create this provider. See totalimpact.conf.json 

            config is the application configuration
        """
        cpath = provider_definition['config']
        if not os.path.isabs(cpath):
            cwd = os.getcwd()
            cpaths = []
            
            # directly beneath the working directory
            cpaths.append(os.path.join(cwd, cpath))
            
            # in a config directory below the current one
            cpaths.append(os.path.join(cwd, "config", cpath))
            
            # in the directory as per the base_dir configuration
            if config.base_dir is not None:
                cpaths.append(os.path.join(config.base_dir, cpath))
            
            for p in cpaths:
                if os.path.isfile(p):
                    cpath = p
                    break
        if not os.path.isfile(cpath):
            raise ProviderConfigurationError()

        conf = Configuration(cpath, False)
        provider_class = config.get_class(provider_definition['class'])
        inst = provider_class(conf, config)
        return inst
        
    @classmethod
    def get_providers(cls, config):
        """ config is the application configuration """
        providers = []
        for p in config.providers:
            try:
                prov = ProviderFactory.get_provider(p, config)
                providers.append(prov)
            except ProviderConfigurationError:
                log.error("Unable to configure provider ... skipping " + str(p))
        return providers
        
class Provider(object):

    def __init__(self, config, app_config):
        self.config = config
        self.app_config = app_config

    def provides_metrics(self): return False
    def member_items(self, query_string, query_type): raise NotImplementedError()
    def aliases(self, item): raise NotImplementedError()
    def metrics(self, item): raise NotImplementedError()
    def biblio(self, item): raise NotImplementedError()
    
    def error(self, error, item):
        # FIXME: not yet implemented
        # all errors are handled by an incremental back-off and ultimate
        # escalation policy
        print "ERROR", type(error), item
    
    def sleep_time(self, dead_time=0):
        return 0
    
    def http_get(self, url, headers=None, timeout=None, error_conf=None):
        retry = 0
        while True:
            try:
                return self.do_get(url, headers, timeout)
            except ProviderTimeout as e:
                self._snooze_or_raise("timeout", error_conf, e, retry)
            except ProviderHttpError as e:
                self._snooze_or_raise("http_error", error_conf, e, retry)
            
            retry += 1
    
    def _snooze_or_raise(self, error_type, error_conf, exception, retry_count):
        if error_conf is None:
            raise exception
        
        conf = error_conf.get(error_type)
        if conf is None:
            raise exception
        
        retries = conf.get("retries")
        if retries is None or retries == 0:
            raise exception
        
        delay = conf.get("retry_delay", 0)
        delay_cap = conf.get("delay_cap", -1)
        retry_type = conf.get("retry_type", "linear")
        
        if retries > retry_count or retries == -1:
            snooze = self._retry_wait(retry_type, delay, delay_cap, retry_count + 1)
            self._interruptable_sleep(snooze)
            return
        
        raise exception
    
    def _interruptable_sleep(self, duration, increment=0.5):
        thread = threading.current_thread()
        if hasattr(thread, "_interruptable_sleep"):
            thread._interruptable_sleep(duration, increment)
        else:
            # NOTE: for testing purposes, this may happen, but in
            # normal operation it should not, so raise an exception
            raise Exception("Thread does not support interruptable sleep")
    
    def _retry_wait(self, type, delay, delay_cap, attempt):
        if type == "incremental_back_off":
            return self._incremental_back_off(delay, delay_cap, attempt)
        else:
            return self._linear_delay(delay, delay_cap, attempt)
    
    def _linear_delay(self, delay, delay_cap, attempt):
        return delay if (delay < delay_cap and delay_cap > -1) or delay_cap == -1 else delay_cap
        
    def _incremental_back_off(self, delay, delay_cap, attempt):
        proposed_delay = delay * 2**(attempt-1)
        return proposed_delay if proposed_delay < delay_cap else delay_cap
    
    def do_get(self, url, headers=None, timeout=None):
        # first thing is to try to retrieve from cache
        c = Cache(
            self.config.cache['max_cache_duration']
        )
        cache_data = c.get_cache_entry(url)
        if cache_data:
            return cache_data
            
        # ensure that a user-agent string is set
        if headers is None:
            headers = {}

        if self.app_config:
            headers['User-Agent'] = self.app_config.user_agent
        
        # make the request
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            logger.debug("Attempt to connect to provider timed out during GET on " + url)
            raise ProviderTimeout()
        except requests.exceptions.RequestException as e:
            # general network error
            logger.info("RequestException during GET on: " + url)
            raise ProviderHttpError()

        # cache the response and return
        c.set_cache_entry(url, r)
        return r
    

class ProviderState(object):
    def __init__(self, rate_period=3600, rate_limit=350, 
                    time_fixture=None, last_request_time=None, request_count=0,
                    throttled=True):
        self.throttled = throttled
        self.time_fixture = time_fixture
        self.last_request_time = last_request_time
        self.rate_period = rate_period
        # scale the rate limit to avoid double counting
        self.rate_limit = rate_limit + 1
        self.request_count = request_count
    
    def register_unthrottled_hit(self):
        self.request_count += 1
    
    def _get_seconds(self, remaining_time, remaining_requests, request_time):
        if remaining_requests <= 0:
            # wait until the reset time
            return self._get_reset_time(request_time) - request_time
        return remaining_time / float(remaining_requests)
    
    # get the timestamp which represents when the rate counter will reset
    def _get_reset_time(self, request_time):
        # The reset time is at the start of the next rating period
        # after the time fixture.  If there is no time fixture,
        # then that time starts now
        if self.time_fixture is None:
            return request_time
        return self.time_fixture + self.rate_period
    
    def _rate_limit_expired(self, request_time):
        return self.time_fixture + self.rate_period <= request_time
    
    def _get_remaining_time(self, request_time):
        remaining_time = (self.time_fixture + self.rate_period) - request_time
        #since_last = request_time - self.last_request_time
        #remaining_time = self.rate_period - since_last
        return remaining_time
    
    def sleep_time(self):
        # some providers might have set themselves to be unthrottled
        if not self.throttled:
            return 0.0
        
        # set ourselves a standard time entity to use in all our
        # calculations
        request_time = time.time()
        
        # always pre-increment the request count, since we assume that we
        # are being called after the request, not before
        self.request_count += 1
        
        if self.last_request_time is None or self.time_fixture is None:
            # if there have been no previous requests, set the current last_request
            # time and the time_fixture to now
            self.time_fixture = request_time
            self.last_request_time = request_time
        
        # has the rate limiting period expired?  If so, set the new fixture
        # to now, and reset the request counter (which we start from 1,
        # for reasons noted above), and allow the caller to just go
        # right ahead by returning a 0.0
        if self._rate_limit_expired(request_time):
            self.time_fixture = request_time
            self.last_request_time = request_time
            self.request_count = 1
            return 0.0
        
        # calculate how many requests we have left in the current period
        # this number could be negative if the caller is ignoring our sleep
        # time suggestions
        remaining_requests = self.rate_limit - self.request_count
        
        # get the time remaining in this rate_period.  This does not take
        # into account whether the caller has obeyed our sleep time suggestions
        remaining_time = self._get_remaining_time(request_time)
        
        # NOTE: this will always return a number less than or equal to the time
        # until the next rate limit period is up.  It does not attempt to deal
        # with rate limit excessions
        #
        # calculate the amount of time to sleep for
        sleep_for = self._get_seconds(remaining_time, remaining_requests, request_time)
        
        # remember the time of /this/ request, so that it can be re-used 
        # on next call
        self.last_request_time = request_time
        
        # tell the caller how long to sleep for
        return sleep_for

class ProviderError(Exception):
    def __init__(self, response=None):
        self.response = response

class ProviderConfigurationError(ProviderError):
    pass

class ProviderTimeout(ProviderError):
    pass

class ProviderHttpError(ProviderError):
    pass

class ProviderClientError(ProviderError):
    pass

class ProviderServerError(ProviderError):
    pass

class ProviderContentMalformedError(ProviderError):
    pass
    
class ProviderValidationFailedError(ProviderError):
    pass
