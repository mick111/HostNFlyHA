from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HostNFlyCoordinator

OCCUPANCY_SENSOR = SensorEntityDescription(
    key="occupancy",
    name="Occupation",
    icon="mdi:home-account",
)

NEXT_RESERVATION_SENSOR = SensorEntityDescription(
    key="next_reservation",
    name="Réservation suivante",
    icon="mdi:calendar-arrow-right",
)

CURRENT_RESERVATION_SENSOR = SensorEntityDescription(
    key="current_reservation",
    name="Réservation en cours",
    icon="mdi:calendar-check",
)

CURRENT_GUEST_SENSOR = SensorEntityDescription(
    key="current_guest",
    name="Occupant courant",
    icon="mdi:account",
)

CURRENT_GUEST_COUNT_SENSOR = SensorEntityDescription(
    key="current_guest_count",
    name="Nombre d'occupants",
    icon="mdi:account-multiple",
)

SENSOR_TYPES = (
    OCCUPANCY_SENSOR,
    CURRENT_GUEST_SENSOR,
    CURRENT_GUEST_COUNT_SENSOR,
    CURRENT_RESERVATION_SENSOR,
    NEXT_RESERVATION_SENSOR,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    coordinator: HostNFlyCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[HostNFlySensor] = []
    for listing_id in coordinator.data:
        for description in SENSOR_TYPES:
            entities.append(HostNFlySensor(coordinator, entry, listing_id, description))
    async_add_entities(entities)


class HostNFlySensor(CoordinatorEntity[HostNFlyCoordinator], SensorEntity):
    def __init__(
        self,
        coordinator: HostNFlyCoordinator,
        entry: ConfigEntry,
        listing_id: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._listing_id = listing_id
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{listing_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_name = description.name

        listing = coordinator.data.get(listing_id, {}).get("listing", {})
        listing_name = str(listing.get("name") or listing.get("title") or f"Listing {listing_id}")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, listing_id)},
            name=listing_name,
            manufacturer="HostNFly",
        )

    @property
    def _listing_data(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._listing_id, {})

    @property
    def native_value(self) -> Any:
        data = self._listing_data
        if self.entity_description.key == "occupancy":
            return "occupied" if data.get("occupancy") else "free"
        if self.entity_description.key == "current_guest":
            reservation = data.get("current_reservation")
            if not reservation:
                return None
            return reservation.get("guest_name")
        if self.entity_description.key == "current_guest_count":
            reservation = data.get("current_reservation")
            if not reservation:
                return None
            return reservation.get("guest_count")
        if self.entity_description.key == "current_reservation":
            return _reservation_range(data.get("current_reservation"))
        if self.entity_description.key == "next_reservation":
            return _reservation_range(data.get("next_reservation"))
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key not in {"current_guest", "current_reservation", "next_reservation"}:
            return None
        key = self.entity_description.key
        reservation_key = "current_reservation" if key == "current_guest" else key
        reservation = self._listing_data.get(reservation_key)
        if not reservation:
            return None
        attrs: dict[str, Any] = {}
        if reservation.get("reservation_id") is not None:
            attrs["reservation_id"] = reservation["reservation_id"]
        if reservation.get("guest_name"):
            attrs["guest_name"] = reservation["guest_name"]
        if reservation.get("guest_count") is not None:
            attrs["guest_count"] = reservation["guest_count"]
        if reservation.get("guest_profile_url"):
            attrs["guest_profile_url"] = reservation["guest_profile_url"]
        if reservation.get("source"):
            attrs["source"] = reservation["source"]
        if reservation.get("amount") is not None:
            attrs["amount"] = reservation["amount"]
        if reservation.get("start_date"):
            attrs["start_date"] = reservation["start_date"].isoformat()
        if reservation.get("end_date"):
            attrs["end_date"] = reservation["end_date"].isoformat()
        return attrs


def _reservation_range(reservation: dict[str, Any] | None) -> str | None:
    if not reservation:
        return None
    start_date = reservation.get("start_date")
    end_date = reservation.get("end_date")
    if start_date and end_date:
        return f"{start_date.isoformat()} - {end_date.isoformat()}"
    if start_date:
        return start_date.isoformat()
    return None
