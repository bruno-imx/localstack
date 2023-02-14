# FIXME: move these tests into respective util tests
import asyncio
import concurrent.futures
import datetime
import time
import unittest

import yaml

from localstack import config
from localstack.utils import async_utils, config_listener
from localstack.utils.aws import aws_stack
from localstack.utils.common import json_safe, now_utc
from localstack.utils.container_utils.container_client import PortMappings
from localstack.utils.http import create_chunked_data, parse_chunked_data


class TestMisc(unittest.TestCase):
    def test_environment(self):
        env = aws_stack.Environment.from_json({"prefix": "foobar1"})
        self.assertEqual("foobar1", env.prefix)
        env = aws_stack.Environment.from_string("foobar2")
        self.assertEqual("foobar2", env.prefix)

    def test_parse_chunked_data(self):
        # See: https://en.wikipedia.org/wiki/Chunked_transfer_encoding
        chunked = "4\r\nWiki\r\n5\r\npedia\r\nE\r\n in\r\n\r\nchunks.\r\n0\r\n\r\n"
        expected = "Wikipedia in\r\n\r\nchunks."

        # test parsing
        parsed = parse_chunked_data(chunked)
        self.assertEqual(expected.strip(), parsed.strip())

        # test roundtrip
        chunked_computed = create_chunked_data(expected)
        parsed = parse_chunked_data(chunked_computed)
        self.assertEqual(expected.strip(), parsed.strip())

    def test_convert_yaml_date_strings(self):
        yaml_source = "Version: 2012-10-17"
        obj = yaml.safe_load(yaml_source)
        self.assertIn(type(obj["Version"]), (datetime.date, str))
        if isinstance(obj["Version"], datetime.date):
            obj = json_safe(obj)
            self.assertEqual(str, type(obj["Version"]))
            self.assertEqual("2012-10-17T00:00:00.000Z", obj["Version"])

    def test_timstamp_millis(self):
        t1 = now_utc()
        t2 = now_utc(millis=True) / 1000
        self.assertAlmostEqual(t1, t2, delta=1)

    def test_port_mappings(self):
        map = PortMappings()
        map.add(123)
        self.assertEqual("-p 123:123", map.to_str())
        map.add(124)
        self.assertEqual("-p 123-124:123-124", map.to_str())
        map.add(234)
        self.assertEqual("-p 123-124:123-124 -p 234:234", map.to_str())
        map.add(345, 346)
        self.assertEqual("-p 123-124:123-124 -p 234:234 -p 345:346", map.to_str())
        map.add([456, 458])
        self.assertEqual(
            "-p 123-124:123-124 -p 234:234 -p 345:346 -p 456-458:456-458", map.to_str()
        )

        map = PortMappings()
        map.add([123, 124])
        self.assertEqual("-p 123-124:123-124", map.to_str())
        map.add([234, 237], [345, 348])
        self.assertEqual("-p 123-124:123-124 -p 234-237:345-348", map.to_str())

    def test_update_config_variable(self):
        config_listener.update_config_variable("foo", "bar")
        self.assertEqual("bar", config.foo)

    def test_async_parallelization(self):
        def handler():
            time.sleep(0.1)
            results.append(1)

        async def run():
            await async_utils.run_sync(handler, thread_pool=thread_pool)

        loop = asyncio.get_event_loop()
        thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=100)
        results = []
        num_items = 1000
        handlers = [run() for i in range(num_items)]
        loop.run_until_complete(asyncio.gather(*handlers))
        self.assertEqual(num_items, len(results))
        thread_pool.shutdown()
