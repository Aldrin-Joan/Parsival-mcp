import asyncio
import importlib
import sys
import types


def test_app_parse_path_calls_initialize_without_on_startup(monkeypatch):
    # Fake fastmcp module with no on_startup API.
    fake_fastmcp = types.ModuleType("fastmcp")

    class FakeMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    fake_fastmcp.FastMCP = FakeMCP

    monkeypatch.setitem(sys.modules, "fastmcp", fake_fastmcp)

    # Reload the app module with the fake FastMCP backend.
    import src.app as app

    app = importlib.reload(app)

    # Verify mcp has no on_startup attr but app starts anyway.
    assert not hasattr(app.mcp, "on_startup")

    # Monkeypatch runtime dependencies.
    dummy_result = types.SimpleNamespace(
        status=types.SimpleNamespace(name="OK"),
        metadata=types.SimpleNamespace(file_format="text"),
        sections=[],
        images=[],
        tables=[],
        errors=[],
        raw_text="ok",
        cache_hit=False,
        request_id="",
    )

    class DummyParser:
        async def parse(self, path, options=None):
            return dummy_result

        async def stream_chunks(self, path, options=None):
            raise AssertionError("unexpected stream path")

    class DummyRouter:
        def detect(self, path):
            from src.models.enums import FileFormat

            return FileFormat.TEXT

    monkeypatch.setattr(app, "FormatRouter", DummyRouter)
    monkeypatch.setattr(app, "get_parser", lambda fmt: DummyParser())

    async def fake_run_parse_in_pool(path, options=None):
        return dummy_result

    async def fake_cache_get(key):
        return None

    async def fake_cache_set(key, value):
        return None

    monkeypatch.setattr(app, "run_parse_in_pool", fake_run_parse_in_pool)
    monkeypatch.setattr(app, "PostProcessingPipeline", types.SimpleNamespace(run=lambda x: x))
    monkeypatch.setattr(app.cache_store, "make_cache_key", lambda path, opts: "dummykey")
    monkeypatch.setattr(app.cache_store, "get", fake_cache_get)
    monkeypatch.setattr(app.cache_store, "set", fake_cache_set)

    initialize_called = False

    async def fake_initialize():
        nonlocal initialize_called
        initialize_called = True

    app.cache_store.initialize = fake_initialize

    result = asyncio.run(app.parse_file("irrelevant", output_format=app.OutputFormat.TEXT))

    assert initialize_called
    assert result.raw_text == "ok"


def test_contenthashstore_initialize_idempotent_and_concurrent():
    from src.core.cache import ContentHashStore

    store = ContentHashStore(max_bytes=1024 * 1024)

    async def run():
        await asyncio.gather(store.initialize(), store.initialize(), store.initialize())

    asyncio.run(run())
    assert store._initialized

    # repeated call should also succeed immediately
    asyncio.run(store.initialize())
    assert store._initialized
