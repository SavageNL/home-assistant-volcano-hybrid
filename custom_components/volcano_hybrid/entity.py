"""Base entity for the Volcano Hybrid integration."""

from __future__ import annotations

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import VolcanoHybridCoordinator


class VolcanoHybridEntity(CoordinatorEntity[VolcanoHybridCoordinator]):
    """Base class for Volcano Hybrid entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VolcanoHybridCoordinator,
        description: EntityDescription,
        *,
        always_available: bool = False,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._key = description.key
        self._attr_unique_id = f"{coordinator.address}-{description.key}"
        self._attr_device_info = coordinator.device_info
        self._always_available = always_available

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._always_available or super().available
