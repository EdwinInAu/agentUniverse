# !/usr/bin/env python3
# -*- coding:utf-8 -*-

"""Regression tests for ComponentBase.create_copy isolation.

See https://github.com/agentuniverse-ai/agentUniverse/issues/1189.
When pydantic ``model_copy(deep=True)`` fails, the copy must still isolate
mutable fields. A shallow ``model_copy()`` is not an acceptable fallback.
"""

import threading
from typing import Any
from unittest.mock import patch

import pytest
from loguru import logger
from pydantic import ConfigDict, Field

from agentuniverse.base.component.component_base import ComponentBase
from agentuniverse.base.component.component_enum import ComponentEnum
from agentuniverse.base.component.component_manager_base import ComponentManagerBase


class _DummyComponent(ComponentBase):
    """Minimal component with a mutable field used to check isolation."""

    name: str = "dummy"
    tags: list = Field(default_factory=list)


class _MarkedComponent(_DummyComponent):
    """Override that records whether ``create_copy`` produced the instance."""

    name: str = "marked"

    def create_copy(self):
        copied = super().create_copy()
        copied.tags.append("from-create-copy")
        return copied


class _LockHoldingComponent(ComponentBase):
    """Holds a runtime resource that neither deep-copy path can duplicate."""

    model_config = ConfigDict(protected_namespaces=(), arbitrary_types_allowed=True)

    name: str = "lock_holder"
    tags: list = Field(default_factory=list)
    lock: Any = Field(default_factory=threading.Lock)


def _register(component: ComponentBase, appname: str = "testapp") -> ComponentManagerBase:
    manager = ComponentManagerBase(component.component_type)
    instance_code = f"{appname}.{component.component_type.value.lower()}.{component.name}"
    manager.register(instance_code, component)
    return manager


def test_create_copy_isolates_mutable_fields():
    component = _DummyComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])

    copied = component.create_copy()

    assert copied is not component
    assert copied.tags == ["alpha"]
    copied.tags.append("beta")
    assert component.tags == ["alpha"]
    assert copied.tags == ["alpha", "beta"]


def test_create_copy_fallback_isolates_when_deep_model_copy_fails():
    """Deep ``model_copy`` failure must not share mutable fields with the original."""
    component = _DummyComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])

    def fail_deep_model_copy(self, *args, **kwargs):
        if kwargs.get("deep"):
            raise RuntimeError("simulated deep model_copy failure")
        raise AssertionError("shallow model_copy must not be used as fallback")

    with patch.object(ComponentBase, "model_copy", fail_deep_model_copy):
        copied = component.create_copy()

    assert copied is not component
    assert copied.tags is not component.tags
    copied.tags.append("gamma")
    assert component.tags == ["alpha"]
    assert copied.tags == ["alpha", "gamma"]


def test_create_copy_logs_and_propagates_when_both_deep_paths_fail():
    component = _DummyComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])
    warnings = []

    def fail_deep_model_copy(self, *args, **kwargs):
        if kwargs.get("deep"):
            raise RuntimeError("simulated deep model_copy failure")
        raise AssertionError("shallow model_copy must not be used as fallback")

    handler_id = logger.add(lambda message: warnings.append(str(message)), level="WARNING")
    try:
        with patch.object(ComponentBase, "model_copy", fail_deep_model_copy), patch(
            "copy.deepcopy", side_effect=TypeError("simulated deepcopy failure")
        ):
            with pytest.raises(TypeError, match="simulated deepcopy failure"):
                component.create_copy()
    finally:
        logger.remove(handler_id)

    assert any("deep model_copy failed" in message for message in warnings)
    assert component.tags == ["alpha"]


def test_create_copy_raises_for_non_copyable_runtime_resource():
    component = _LockHoldingComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])

    with pytest.raises(TypeError):
        component.create_copy()

    assert component.tags == ["alpha"]


def test_get_instance_obj_new_instance_uses_create_copy():
    component = _MarkedComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])
    manager = _register(component)

    copied = manager.get_instance_obj("marked", appname="testapp", new_instance=True)

    assert copied is not component
    assert copied.tags == ["alpha", "from-create-copy"]
    assert component.tags == ["alpha"]
    copied.tags.append("beta")
    assert component.tags == ["alpha"]


def test_get_instance_obj_missing_returns_none():
    manager = ComponentManagerBase(ComponentEnum.DEFAULT)

    assert manager.get_instance_obj("missing", appname="testapp", new_instance=True) is None
    assert manager.get_instance_obj("missing", appname="testapp") is None


def test_get_instance_obj_without_new_instance_returns_registered_object():
    component = _DummyComponent(component_type=ComponentEnum.DEFAULT, tags=["alpha"])
    manager = _register(component)

    assert manager.get_instance_obj("dummy", appname="testapp") is component
    assert manager.get_instance_obj("dummy", appname="testapp", new_instance=False) is component
