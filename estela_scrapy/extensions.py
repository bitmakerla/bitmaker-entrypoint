import json
import os
import sys
from datetime import datetime, timedelta

import redis
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.exporters import PythonItemExporter
from twisted.internet import task

from estela_scrapy.producer import connect_kafka_producer, on_kafka_send_error

from .utils import json_serializer, update_job

RUNNING_STATUS = "RUNNING"
COMPLETED_STATUS = "COMPLETED"
INCOMPLETE_STATUS = "INCOMPLETE"
FINISHED_REASON = "finished"


class BaseExtension:
    def __init__(self, stats, *args, **kwargs):
        self.stats = stats
        self.auth_token = os.getenv("ESTELA_AUTH_TOKEN")
        job = os.getenv("ESTELA_SPIDER_JOB")
        host = os.getenv("ESTELA_API_HOST")
        self.job_jid, spider_sid, project_pid = job.split(".")
        self.job_url = "{}/api/projects/{}/spiders/{}/jobs/{}".format(
            host, project_pid, spider_sid, self.job_jid
        )
        self.producer = connect_kafka_producer()


class ItemStorageExtension(BaseExtension):
    def __init__(self, stats):
        super().__init__(stats)
        exporter_kwargs = {"binary": False}
        self.exporter = PythonItemExporter(**exporter_kwargs)

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler.stats)
        crawler.signals.connect(ext.item_scraped, signals.item_scraped)
        crawler.signals.connect(ext.spider_opened, signals.spider_opened)
        return ext

    def spider_opened(self, spider):
        update_job(self.job_url, self.auth_token, status=RUNNING_STATUS)

    def item_scraped(self, item, spider):
        item = self.exporter.export_item(item)

        self.stats.inc_value("database_size_sys", sys.getsizeof(item))
        self.stats.inc_value("database_size_json", len(json.dumps(item, default=str)))

        data = {
            "jid": os.getenv("ESTELA_COLLECTION"),
            "payload": dict(item),
            "unique": os.getenv("ESTELA_UNIQUE_COLLECTION"),
        }
        self.producer.send("job_items", value=data).add_errback(on_kafka_send_error)


class RedisStatsCollector(BaseExtension):
    def __init__(self, stats):
        super().__init__(stats)

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise NotConfigured("REDIS_URL not found in the settings")
        self.redis_conn = redis.from_url(redis_url)

        self.stats_key = os.getenv("REDIS_STATS_KEY")
        self.interval = float(os.getenv("REDIS_STATS_INTERVAL"))

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler.stats)

        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)

        return ext

    def spider_opened(self, spider):
        self.task = task.LoopingCall(self.store_stats, spider)
        self.task.start(self.interval)

    def spider_closed(self, spider, reason):
        if self.task.running:
            self.task.stop()
        try:
            self.redis_conn.delete(self.stats_key)
        except Exception:
            pass

        stats = self.stats.get_stats()
        update_job(
            self.job_url,
            self.auth_token,
            status=COMPLETED_STATUS if reason == FINISHED_REASON else INCOMPLETE_STATUS,
            lifespan=int(stats.get("elapsed_time_seconds", 0)),
            total_bytes=stats.get("downloader/response_bytes", 0),
            item_count=stats.get("item_scraped_count", 0),
            request_count=stats.get("downloader/request_count", 0),
        )

        parsed_stats = json.dumps(stats, default=json_serializer)
        data = {
            "jid": os.getenv("ESTELA_SPIDER_JOB"),
            "payload": json.loads(parsed_stats),
        }
        self.producer.send("job_stats", value=data).add_errback(on_kafka_send_error)
        self.producer.flush()

    def store_stats(self, spider):
        stats = self.stats.get_stats()
        elapsed_time = int((datetime.now() - stats.get("start_time")).total_seconds())
        database_size_sys = stats.get("database_size_sys", 0)
        database_size_json = stats.get("database_size_json", 0)
        stats.update(
            {
                "elapsed_time_seconds": elapsed_time,
                "database_size_sys": database_size_sys,
                "database_size_json": database_size_json,
            }
        )

        parsed_stats = json.dumps(stats, default=json_serializer)
        self.redis_conn.hmset(self.stats_key, json.loads(parsed_stats))
