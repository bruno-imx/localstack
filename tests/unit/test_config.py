import os
import sys
from contextlib import contextmanager
from typing import Any, Dict

import pytest

from localstack import config


@contextmanager
def temporary_env(env: Dict[str, Any]):
    old = os.environ.copy()
    try:
        os.environ.update(env)
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(old)


class TestProviderConfig:
    def test_provider_default_value(self):
        default_value = "default_value"
        override_value = "override_value"
        provider_config = config.ServiceProviderConfig(default_value=default_value)
        assert provider_config.get_provider("ec2") == default_value
        provider_config.set_provider("ec2", override_value)
        assert provider_config.get_provider("ec2") == override_value

    def test_provider_set_if_not_exists(self):
        default_value = "default_value"
        override_value = "override_value"
        provider_config = config.ServiceProviderConfig(default_value=default_value)
        provider_config.set_provider("ec2", default_value)
        provider_config.set_provider_if_not_exists("ec2", override_value)
        assert provider_config.get_provider("ec2") == default_value

    def test_provider_config_overrides(self, monkeypatch):
        default_value = "default_value"
        override_value = "override_value"
        provider_config = config.ServiceProviderConfig(default_value=default_value)
        monkeypatch.setenv("PROVIDER_OVERRIDE_EC2", override_value)
        provider_config.load_from_environment()
        assert provider_config.get_provider("ec2") == override_value
        assert provider_config.get_provider("sqs") == default_value
        monkeypatch.setenv("PROVIDER_OVERRIDE_SQS", override_value)
        provider_config.load_from_environment()
        assert provider_config.get_provider("sqs") == override_value

    def test_bulk_set_if_not_exists(self):
        default_value = "default_value"
        custom_value = "custom_value"
        override_value = "override_value"
        override_services = ["sqs", "sns", "lambda", "ec2"]
        provider_config = config.ServiceProviderConfig(default_value=default_value)
        provider_config.set_provider("ec2", default_value)
        provider_config.set_provider("lambda", custom_value)
        provider_config.bulk_set_provider_if_not_exists(override_services, override_value)
        assert provider_config.get_provider("sqs") == override_value
        assert provider_config.get_provider("sns") == override_value
        assert provider_config.get_provider("lambda") == custom_value
        assert provider_config.get_provider("ec2") == default_value
        assert provider_config.get_provider("kinesis") == default_value


class TestParseServicePorts:
    def test_returns_default_service_ports(self):
        result = config.parse_service_ports()
        assert result == config.DEFAULT_SERVICE_PORTS

    def test_with_service_subset(self):
        with temporary_env({"SERVICES": "s3,sqs", "EAGER_SERVICE_LOADING": "1"}):
            result = config.parse_service_ports()

        assert len(result) == 2
        assert "s3" in result
        assert "sqs" in result
        assert result["s3"] == 4566
        assert result["sqs"] == 4566

    def test_custom_service_default_port(self):
        with temporary_env({"SERVICES": "foobar", "EAGER_SERVICE_LOADING": "1"}):
            result = config.parse_service_ports()

        assert len(result) == 1
        assert "foobar" not in config.DEFAULT_SERVICE_PORTS
        assert "foobar" in result
        # foobar is not a default service so it is assigned 0
        assert result["foobar"] == 0

    def test_custom_port_mapping(self):
        with temporary_env(
            {"SERVICES": "foobar", "FOOBAR_PORT": "1234", "EAGER_SERVICE_LOADING": "1"}
        ):
            result = config.parse_service_ports()

        assert len(result) == 1
        assert "foobar" not in config.DEFAULT_SERVICE_PORTS
        assert "foobar" in result
        assert result["foobar"] == 1234

    def test_custom_illegal_port_mapping(self):
        with temporary_env(
            {"SERVICES": "foobar", "FOOBAR_PORT": "asdf", "EAGER_SERVICE_LOADING": "1"}
        ):
            result = config.parse_service_ports()

        assert len(result) == 1
        assert "foobar" not in config.DEFAULT_SERVICE_PORTS
        assert "foobar" in result
        # FOOBAR_PORT cannot be parsed
        assert result["foobar"] == 0

    def test_custom_port_mapping_in_services_env(self):
        with temporary_env({"SERVICES": "foobar:1235", "EAGER_SERVICE_LOADING": "1"}):
            result = config.parse_service_ports()

        assert len(result) == 1
        assert "foobar" not in config.DEFAULT_SERVICE_PORTS
        assert "foobar" in result
        # FOOBAR_PORT cannot be parsed
        assert result["foobar"] == 1235


class TestEdgeVariablesDerivedCorrectly:
    """
    Post-v2 we are deriving

    * EDGE_PORT
    * EDGE_PORT_HTTP
    * EDGE_BIND_HOST

    from EDGE_BIND (name TBD). We are also ensuring the configuration behaves
    well with LOCALSTACK_HOST, i.e. if LOCALSTACK_HOST is supplied and
    EDGE_BIND is not, then we should propagate LOCALSTACK_HOST configuration
    into EDGE_BIND.

    Implementation note: monkeypatching the config module is hard, and causes
    tests run after these ones to import the wrong config. Instead, we test the
    function that populates the configuration variables.
    """

    @pytest.fixture
    def configure_environment(self, monkeypatch):
        def inner(**envars):
            import importlib

            for name, value in envars.items():
                monkeypatch.setenv(name, value)

            del sys.modules["localstack.config"]
            cfg = importlib.import_module("localstack.config")

            return cfg

        return inner

    @pytest.fixture
    def default_ip(self):
        if config.is_in_docker:
            return "0.0.0.0"
        else:
            return "127.0.0.1"

    def test_defaults(self, default_ip):
        (
            ls_host,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw=None,
            edge_bind_raw=None,
        )

        assert ls_host == "localhost.localstack.cloud:4566"
        assert edge_bind == f"{default_ip}:4566"
        assert edge_port == 4566
        assert edge_port_http == 4566
        assert edge_bind_host == default_ip

    def test_custom_hostname(self):
        (
            _,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw=None,
            edge_bind_raw="192.168.0.1",
        )

        assert edge_bind == "192.168.0.1:4566"
        assert edge_port == 4566
        assert edge_port_http == 4566
        assert edge_bind_host == "192.168.0.1"

    def test_custom_port(self, default_ip):
        (
            _,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw=None,
            edge_bind_raw=":9999",
        )

        assert edge_bind == f"{default_ip}:9999"
        assert edge_port == 9999
        assert edge_port_http == 9999
        assert edge_bind_host == default_ip

    def test_custom_host_and_port(self):
        (
            _,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw=None,
            edge_bind_raw="192.168.0.1:9999",
        )

        assert edge_bind == "192.168.0.1:9999"
        assert edge_port == 9999
        assert edge_port_http == 9999
        assert edge_bind_host == "192.168.0.1"

    def test_localstack_host_overrides_edge_variables(self, default_ip):
        (
            ls_host,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw="hostname:9999",
            edge_bind_raw=None,
        )

        assert ls_host == "hostname:9999"
        assert edge_bind == f"{default_ip}:9999"
        assert edge_port == 9999
        assert edge_port_http == 9999
        assert edge_bind_host == default_ip

    def test_edge_bind_multiple_addresses(self):
        (
            _,
            edge_bind,
            edge_bind_host,
            edge_port,
            edge_port_http,
        ) = config.populate_legacy_edge_configuration(
            localstack_host_raw=None,
            edge_bind_raw="0.0.0.0:9999,0.0.0.0:443",
        )

        assert edge_bind == "0.0.0.0:9999,0.0.0.0:443"
        # take the first value
        assert edge_port == 9999
        assert edge_port_http == 9999
        assert edge_bind_host == "0.0.0.0"

    @pytest.mark.parametrize(
        "input,hosts_and_ports",
        [
            ("0.0.0.0:9999", [("0.0.0.0", 9999)]),
            (
                "0.0.0.0:9999,127.0.0.1:443",
                [
                    ("0.0.0.0", 9999),
                    ("127.0.0.1", 443),
                ],
            ),
            (
                "0.0.0.0:9999,127.0.0.1:443",
                [
                    ("0.0.0.0", 9999),
                    ("127.0.0.1", 443),
                ],
            ),
        ],
    )
    def test_edge_bind_parsed(self, input, hosts_and_ports):
        res = config.get_edge_bind(input)

        expected = [config.HostAndPort(host=host, port=port) for (host, port) in hosts_and_ports]
        assert res == expected
