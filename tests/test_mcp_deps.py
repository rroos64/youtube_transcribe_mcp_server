from mcp_server.deps import build_services, get_services, set_services


def test_build_services_default_config():
    services = build_services()
    assert services.config is not None
    assert services.store is not None


def test_get_services_initializes_singleton():
    set_services(None)
    try:
        services = get_services()
        assert services.config is not None
    finally:
        set_services(None)
