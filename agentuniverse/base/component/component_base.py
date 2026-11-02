# !/usr/bin/env python3
# -*- coding:utf-8 -*-

# @Time    : 2024/3/14 15:35
# @Author  : jerry.zzw 
# @Email   : jerry.zzw@antgroup.com
# @FileName: component_base.py
import copy
from abc import ABC

from pydantic import BaseModel, ConfigDict

from agentuniverse.base.component.component_enum import ComponentEnum
from agentuniverse.base.config.application_configer.application_config_manager import ApplicationConfigManager
from agentuniverse.base.config.component_configer.component_configer import ComponentConfiger
from agentuniverse.base.util.logging.logging_util import LOGGER


class ComponentBase(BaseModel):
    """The ComponentBase class, which is used to define the base class of the component."""

    component_type: ComponentEnum
    # pydantic protected_namespaces config
    model_config = ConfigDict(protected_namespaces=())

    def get_instance_code(self) -> str:
        """Return the full name of the component."""
        appname = ApplicationConfigManager().app_configer.base_info_appname
        return f'{appname}.{self.component_type.value.lower()}.{self.name}'

    def initialize_by_component_configer(self, component_configer: ComponentConfiger) -> 'ComponentBase':
        """Initialize the component by the ComponentConfiger object.

        Args:
            component_configer(ComponentConfiger): the ComponentConfiger object
        Returns:
            ComponentBase: the component object
        """
        pass

    def create_copy(self) -> 'ComponentBase':
        """Return an isolated copy of this component.

        ``ComponentManagerBase.get_instance_obj(..., new_instance=True)`` uses
        this so a caller cannot mutate the registered instance.

        Prefer ``model_copy(deep=True)``. If that fails, fall back to
        ``copy.deepcopy`` and log the original error. A shallow
        ``model_copy()`` is not used: it would share mutable fields with the
        original. If both deep-copy paths fail, the ``copy.deepcopy`` error
        propagates.

        Returns:
            ComponentBase: an independent copy of this component.
        """
        try:
            return self.model_copy(deep=True)
        except Exception as e:
            # Broad catch by design: deep model_copy can fail for varied field
            # types. Log it, then try stdlib deepcopy before giving up.
            LOGGER.warn(f"deep model_copy failed ({e}); using deepcopy fallback")
            return copy.deepcopy(self)
