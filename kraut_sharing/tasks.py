# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

from django.core.management import call_command

from kraut_sharing.models import TAXII_Remote_Collection, TAXII_Remote_Server
from kraut_sharing.feed import CollectionRequest, CollectionPoll

from celery import Celery
import datetime, pytz
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

app = Celery(broker='amqp://')


@app.task(ignore_result=True)
def poll_collection(collection):
    server_url = collection.server.get_url()
    begin_ts = datetime.datetime.now(pytz.utc) - datetime.timedelta(hours = collection.poll_period)
    logger.info('Calculated starting TS: %s' % (begin_ts.strftime('%Y-%m-%dT%H:%M:%S.%f%z')))
    collection.begin_timestamp = begin_ts
    collection.save()
    logger.info('Polling collection: %s' % (collection.name))
    # store information in import directory
    script = CollectionPoll(url=server_url, collection_name=collection.name, begin_timestamp=begin_ts.strftime('%Y-%m-%dT%H:%M:%S.%f%z'))
    script.run()
    # run load_stix command on imported data
    with open('/tmp/last_import_command', 'w') as f:
        call_command('load_stix', 'imports/', stdout=f)
    return True


@app.task(ignore_result=True)
def refresh_collection_task(server_id):
    try:
        remote_server = TAXII_Remote_Server.objects.get(id=server_id)
    except TAXII_Remote_Server.DoesNotExist:
        print "taxii server does not exist!"
        return False
    url = remote_server.get_url()
    script = CollectionRequest(url)
    result = script.run()
    for item in result['collection_informations']:
        if 'available' in item and item['available']:
            collection, created = TAXII_Remote_Collection.objects.get_or_create(name=item['collection_name'], server=remote_server, collection_type=item['collection_type'])
    return True
