import re
from collections import defaultdict

run_post_file = False

if run_post_file:
    # zgrep "key=" 2012-*.gz | grep method=POST | grep -v "key=VANWIJIKc233acaa" | grep -v "key=EXAMPLE" | grep -v "key=Heather" | grep -v embed | grep -v GREEK_YOGURT | grep -v "key=KEY" | grep -v YOURKEY > registers_by_post.txt
    #2012-11-20.gz:207432773781471232   2012-11-20T06:30:49Z    2012-11-20T06:30:49Z    1075101 ti-core 67.202.23.119   User    Notice  heroku/router   at=info method=POST path=/v1/doi/10.1039/b704980c?key=87e02f1090c3438db9ac5b48d3dc3c1c host=api.impactstory.org fwd= dyno=web.1 queue=0 wait=0ms connect=2ms service=5ms status=404 bytes=238
    filename = "/Users/hpiwowar/Dropbox/ti/papertrail archives/registers_by_post.txt"
    contents = open(filename, "r").read()
    register_pattern = re.compile("2012.*\t(?P<timestamp>2012-.*)Z\t.*/v1/item/(?P<namespace>[a-z]*?)/(?P<id>.*?)\?key=(?P<apikey>.*?) host")
    all_registrations = register_pattern.findall(contents)
else:
    #zgrep "key=" 2012-*.gz | grep method=GET | grep -v "key=VANWIJIKc233acaa" | grep -v "key=EXAMPLE" | grep -v "key=Heather" | grep -v embed | grep -v GREEK_YOGURT | grep register > registers_by_get.txt
    # 2012-12-16.gz:216792413250023424  2012-12-16T02:22:41Z    2012-12-16T02:22:41Z    1075101 ti-core 107.21.167.86   User    Notice  heroku/router   at=info method=GET path=/v1/item/doi/10.3897/zookeys.57.477?key=pensoft-127b7fd8&register=true&_=1355624578069 host=total-impact-core.herokuapp.com fwd=201.141.18.134 dyno=web.1 queue=0 wait=0ms connect=2ms service=170ms status=200 bytes=5953
    filename = "/Users/hpiwowar/Dropbox/ti/papertrail archives/registers_by_get.txt"
    contents = open(filename, "r").read()
    register_pattern = re.compile("2012.*\t(?P<timestamp>2012-.*)Z\t.*/v1/item/(?P<namespace>[a-z]*?)/(?P<id>.*?)\?key=(?P<apikey>.*?)&")
    all_registrations = register_pattern.findall(contents)


from totalimpact import models
from totalimpact import dao
from totalimpact import api_user

mydao = dao.Dao(os.environ["CLOUDANT_URL"], os.environ["CLOUDANT_DB"])


registration_dict = defaultdict(dict)
for registration in all_registrations:
    (timestamp, namespace, nid, api_key) = registration

    if api_key in ["test", "api-docs"]:
        continue
    if len(api_key) > 20:
        continue

    alias = (namespace, nid)
    registration_dict[api_key][alias] = {"registered":timestamp}


    tiid = models.ItemFactory.get_tiid_by_alias(namespace, nid, None, mydao)
    if not tiid:
        print "****************** no tiid, skipping"
        continue

    api_user.register_item(alias, tiid, api_key, mydao)



