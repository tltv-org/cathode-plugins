"""Test that all plugins return valid register() dicts per PLUGIN-CONTRACT.md."""

from __future__ import annotations

import pytest

from tests.conftest import PLUGIN_DIRS, FakeApp, _load_plugin

# Valid top-level keys per the contract
VALID_KEYS = {
    "category",
    "shutdown",
    "services",
    "tasks",
    "settings",
    "on_settings_changed",
    "source_types",
    "output_types",
    "block_types",
    "overlay_elements",
    "layers",
    "playlist_tools",
    "presets",
    "generate",
    "system_deps",
}

VALID_CATEGORIES = {
    "source",
    "content",
    "schedule",
    "graphics",
    "output",
    "integration",
}

PLUGINS_WITH_REGISTER = ["html-source", "script-source", "gstreamer-source", "overlay"]


@pytest.fixture(params=PLUGINS_WITH_REGISTER)
def plugin_result(request):
    """Load each plugin and call register(), returning (name, result)."""
    name = request.param
    mod = _load_plugin(name)
    app = FakeApp()
    result = mod.register(app, {})
    return name, result


class TestContractKeys:
    """Every register() result must only contain known keys."""

    def test_returns_dict(self, plugin_result):
        name, result = plugin_result
        assert isinstance(result, dict), f"{name}: register() must return a dict"

    def test_no_unknown_keys(self, plugin_result):
        name, result = plugin_result
        unknown = set(result.keys()) - VALID_KEYS
        assert not unknown, f"{name}: unknown keys in register() result: {unknown}"

    def test_has_category(self, plugin_result):
        name, result = plugin_result
        assert "category" in result, f"{name}: missing 'category'"

    def test_valid_categories(self, plugin_result):
        name, result = plugin_result
        cats = {c.strip() for c in result["category"].split(",")}
        invalid = cats - VALID_CATEGORIES
        assert not invalid, f"{name}: invalid categories: {invalid}"


class TestSourceTypes:
    """Plugins declaring source_types must follow the factory interface."""

    def test_source_type_has_factory(self, plugin_result):
        name, result = plugin_result
        for st_name, st in result.get("source_types", {}).items():
            assert "factory" in st, f"{name}: source_type '{st_name}' missing 'factory'"
            assert hasattr(st["factory"], "build"), (
                f"{name}: factory for '{st_name}' missing build() method"
            )

    def test_source_type_has_description(self, plugin_result):
        name, result = plugin_result
        for st_name, st in result.get("source_types", {}).items():
            assert "description" in st, (
                f"{name}: source_type '{st_name}' missing 'description'"
            )


class TestBlockTypes:
    """Plugins declaring block_types must have a handler with dispatch()."""

    def test_block_type_has_handler(self, plugin_result):
        name, result = plugin_result
        for bt_name, bt in result.get("block_types", {}).items():
            assert "handler" in bt, f"{name}: block_type '{bt_name}' missing 'handler'"
            assert hasattr(bt["handler"], "dispatch"), (
                f"{name}: handler for '{bt_name}' missing dispatch() method"
            )


class TestPresets:
    """Plugins declaring presets must provide a store with list/get/save/delete."""

    def test_preset_store_interface(self, plugin_result):
        name, result = plugin_result
        if "presets" not in result:
            pytest.skip(f"{name} has no presets")
        store = result["presets"]
        for method in ("list", "get", "save", "delete"):
            assert hasattr(store, method), (
                f"{name}: preset store missing {method}() method"
            )

    def test_presets_not_empty(self, plugin_result):
        name, result = plugin_result
        if "presets" not in result:
            pytest.skip(f"{name} has no presets")
        presets = result["presets"].list()
        assert len(presets) > 0, f"{name}: preset store is empty"


class TestGenerate:
    """Plugins declaring generate must provide an async callable."""

    def test_generate_is_callable(self, plugin_result):
        name, result = plugin_result
        if "generate" not in result:
            pytest.skip(f"{name} has no generate")
        assert callable(result["generate"]), f"{name}: generate is not callable"


class TestOverlayElements:
    """Overlay plugins must declare valid element tuples."""

    def test_overlay_element_tuples(self, plugin_result):
        name, result = plugin_result
        if "overlay_elements" not in result:
            pytest.skip(f"{name} has no overlay_elements")
        for elem in result["overlay_elements"]:
            assert isinstance(elem, (list, tuple)), (
                f"{name}: overlay_element must be a tuple"
            )
            assert len(elem) == 3, (
                f"{name}: overlay_element must be (factory, name, props)"
            )
            factory_name, elem_name, props = elem
            assert isinstance(factory_name, str)
            assert isinstance(elem_name, str)
            assert isinstance(props, dict)


class TestSettings:
    """Plugins declaring settings must use the correct schema."""

    def test_settings_schema(self, plugin_result):
        name, result = plugin_result
        if "settings" not in result:
            pytest.skip(f"{name} has no settings")
        for key, setting in result["settings"].items():
            assert "type" in setting, f"{name}: setting '{key}' missing 'type'"
            assert setting["type"] in ("str", "int", "float", "bool"), (
                f"{name}: setting '{key}' has invalid type '{setting['type']}'"
            )
            assert "value" in setting, f"{name}: setting '{key}' missing 'value'"
            assert "description" in setting, (
                f"{name}: setting '{key}' missing 'description'"
            )
