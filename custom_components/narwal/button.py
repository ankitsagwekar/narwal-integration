"""Button entities for Narwal robot vacuum."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NarwalConfigEntry
from .coordinator import NarwalCoordinator
from .entity import NarwalEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Narwal button entities."""
    coordinator = entry.runtime_data
    async_add_entities([
        NarwalLocateButton(coordinator),
        NarwalWakeButton(coordinator),
        NarwalRebootButton(coordinator),
        NarwalShutdownButton(coordinator),
    ])


class NarwalLocateButton(NarwalEntity, ButtonEntity):
    """Makes the vacuum beep so you can find it."""

    _attr_translation_key = "locate"
    _attr_icon = "mdi:map-marker-question"

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data['device_name']}_locate"
        )

    async def async_press(self) -> None:
        """Send the yell/locate command to the vacuum."""
        resp = await self.coordinator.client.locate()
        if not resp.success:
            _LOGGER.warning("Locate returned code=%s", resp.result_code)


class NarwalWakeButton(NarwalEntity, ButtonEntity):
    """Wake the vacuum from sleep by sending an active_robot notification."""

    _attr_translation_key = "wake"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data['device_name']}_wake"
        )

    async def async_press(self) -> None:
        """Send active_robot_publish to wake the vacuum."""
        await self.coordinator.client.notify_active()
        _LOGGER.info("Sent wake (active_robot) notification")


class NarwalRebootButton(NarwalEntity, ButtonEntity):
    """Reboot the vacuum."""

    _attr_translation_key = "reboot"
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data['device_name']}_reboot"
        )

    async def async_press(self) -> None:
        """Send common/reboot to restart the vacuum."""
        resp = await self.coordinator.client.reboot()
        if resp is not None and not resp.success:
            raise HomeAssistantError(
                f"Vacuum refused reboot (code={resp.result_code})."
            )


class NarwalShutdownButton(NarwalEntity, ButtonEntity):
    """Power off the vacuum (counterpart to the wake button).

    After shutdown the robot leaves MQTT entirely; it must be powered on
    again with its physical power button — the wake button cannot revive it.
    """

    _attr_translation_key = "shutdown"
    _attr_icon = "mdi:power-off"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data['device_name']}_shutdown"
        )

    async def async_press(self) -> None:
        """Send common/shutdown to power off the vacuum."""
        resp = await self.coordinator.client.shutdown()
        if resp is not None and not resp.success:
            raise HomeAssistantError(
                f"Vacuum refused shutdown (code={resp.result_code}). "
                "It may not power off while docked or charging."
            )
