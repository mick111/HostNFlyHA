from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HostNFlyApi, HostNFlyAuthError
from .const import (
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_SCAN_INTERVAL,
    DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HostNFlyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api: HostNFlyApi, entry) -> None:
        self.api = api
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self.scan_interval),
        )

    @property
    def scan_interval(self) -> int:
        return int(self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    @property
    def lookback_days(self) -> int:
        return int(self.entry.options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS))

    @property
    def lookahead_days(self) -> int:
        return int(self.entry.options.get(CONF_LOOKAHEAD_DAYS, DEFAULT_LOOKAHEAD_DAYS))

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._async_fetch_data()
        except HostNFlyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Erreur API HostNFly: {err}") from err

    async def _async_fetch_data(self) -> dict[str, Any]:
        today = dt_util.now().date()
        min_date = today - timedelta(days=self.lookback_days)
        max_date = today + timedelta(days=self.lookahead_days)

        listings = await self.api.async_get_listings()
        reservations = await self.api.async_get_reservations(min_date.isoformat(), max_date.isoformat())
        amount_by_reservation_id: dict[str, Any] = {}
        try:
            transfers = await self.api.async_get_transfers(min_date, max_date)
            amount_by_reservation_id = _amounts_by_reservation_id(transfers)
        except Exception as err:
            _LOGGER.debug("Impossible de charger les transferts: %s", err)

        reservations_by_listing: dict[str, list[dict[str, Any]]] = {}
        for reservation in reservations:
            if _is_cancelled(reservation):
                continue
            listing_id = _reservation_listing_id(reservation)
            if not listing_id:
                continue
            reservations_by_listing.setdefault(listing_id, []).append(reservation)

        data: dict[str, Any] = {}
        for listing in listings:
            listing_id = _listing_id(listing)
            if not listing_id:
                continue
            listing_reservations = reservations_by_listing.get(listing_id, [])
            current_reservation = _current_reservation(
                listing_reservations,
                today,
                amount_by_reservation_id,
            )
            data[listing_id] = {
                "listing": listing,
                "occupancy": current_reservation is not None,
                "current_reservation": current_reservation,
                "next_reservation": _next_reservation(
                    listing_reservations,
                    today,
                    current_reservation,
                    amount_by_reservation_id,
                ),
            }

        return data


def _listing_id(listing: dict[str, Any]) -> str | None:
    for key in ("id", "listing_id", "uid", "uuid"):
        value = listing.get(key)
        if value is not None:
            return str(value)
    return None


def _reservation_listing_id(reservation: dict[str, Any]) -> str | None:
    listing_id = reservation.get("listing_id")
    if listing_id is not None:
        return str(listing_id)
    listing = reservation.get("listing")
    if isinstance(listing, dict):
        nested_id = listing.get("id")
        if nested_id is not None:
            return str(nested_id)
    return None


def _reservation_id(reservation: dict[str, Any]) -> str | None:
    for key in ("id", "reservation_id", "uid", "uuid"):
        value = reservation.get(key)
        if value is not None:
            return str(value)
    return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            parsed = dt_util.parse_datetime(value)
            if parsed:
                return parsed.date()
    return None


def _reservation_dates(reservation: dict[str, Any]) -> tuple[date | None, date | None]:
    start_value = reservation.get("start_date") or reservation.get("check_in")
    end_value = reservation.get("end_date") or reservation.get("check_out")
    return _parse_date(start_value), _parse_date(end_value)


def _reservation_guest_name(reservation: dict[str, Any]) -> str | None:
    for key in ("guest_name", "guest_full_name"):
        if reservation.get(key):
            return str(reservation[key])
    guest = reservation.get("guest")
    if isinstance(guest, str):
        return guest
    if isinstance(guest, dict):
        for key in ("name", "full_name", "first_name"):
            if guest.get(key):
                return str(guest[key])
    return None


def _reservation_guest_profile_url(reservation: dict[str, Any]) -> str | None:
    for key in ("airbnb_url", "profile_url", "guest_profile_url"):
        if reservation.get(key):
            return str(reservation[key])
    guest = reservation.get("guest")
    if isinstance(guest, dict):
        for key in ("airbnb_url", "profile_url", "guest_profile_url"):
            if guest.get(key):
                return str(guest[key])
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _sum_guest_parts(container: dict[str, Any]) -> int | None:
    total = 0
    found = False
    for key in ("adults", "children", "infants", "babies", "kids"):
        for candidate in (key, f"{key}_count", f"guest_{key}", f"guest_{key}_count"):
            if candidate in container:
                value = _coerce_int(container.get(candidate))
                if value is not None:
                    total += value
                    found = True
    return total if found else None


def _count_from_value(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("count", "guests_count", "guest_count", "number_of_guests"):
            nested = _count_from_value(value.get(key))
            if nested is not None:
                return nested
        return _sum_guest_parts(value)
    return _coerce_int(value)


def _reservation_guest_count(reservation: dict[str, Any]) -> int | None:
    for key in ("guests_count", "guest_count", "number_of_guests", "guests", "occupants", "occupancy"):
        count = _count_from_value(reservation.get(key))
        if count is not None:
            return count

    guest = reservation.get("guest")
    if isinstance(guest, dict):
        for key in ("count", "guests_count", "guest_count", "number_of_guests"):
            count = _count_from_value(guest.get(key))
            if count is not None:
                return count

    guests = reservation.get("guests")
    if isinstance(guests, dict):
        count = _sum_guest_parts(guests)
        if count is not None:
            return count

    return _sum_guest_parts(reservation)


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return None
    return None


def _reservation_amount(reservation: dict[str, Any]) -> float | None:
    return _coerce_float(reservation.get("amount"))


def _reservation_amount_from_map(
    reservation: dict[str, Any],
    amount_by_reservation_id: dict[str, Any] | None,
) -> float | None:
    if not amount_by_reservation_id:
        return None
    reservation_id = _reservation_id(reservation)
    if not reservation_id:
        return None
    return _coerce_float(amount_by_reservation_id.get(reservation_id))


def _amounts_by_reservation_id(transfers: list[dict[str, Any]]) -> dict[str, Any]:
    amounts: dict[str, Any] = {}
    for transfer in transfers:
        if not isinstance(transfer, dict):
            continue
        reservations = transfer.get("reservations")
        if not isinstance(reservations, list):
            continue
        for reservation in reservations:
            if not isinstance(reservation, dict):
                continue
            reservation_id = _reservation_id(reservation)
            if not reservation_id:
                continue
            if "amount" in reservation:
                amounts[reservation_id] = reservation.get("amount")
    return amounts


def _is_cancelled(reservation: dict[str, Any]) -> bool:
    status = str(reservation.get("status", "")).lower()
    return status in {"cancelled", "canceled", "void", "refused"}


def _is_occupied(reservations: list[dict[str, Any]], today: date) -> bool:
    for reservation in reservations:
        start_date, end_date = _reservation_dates(reservation)
        if not start_date:
            continue
        if end_date:
            if start_date <= today < end_date:
                return True
        elif start_date <= today:
            return True
    return False


def _next_reservation(
    reservations: list[dict[str, Any]],
    today: date,
    current_reservation: dict[str, Any] | None,
    amount_by_reservation_id: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    threshold = today
    if current_reservation:
        end_date = current_reservation.get("end_date")
        if isinstance(end_date, date):
            threshold = end_date

    upcoming: list[tuple[date, dict[str, Any], date | None]] = []
    for reservation in reservations:
        start_date, end_date = _reservation_dates(reservation)
        if not start_date or start_date < threshold:
            continue
        upcoming.append((start_date, reservation, end_date))
    if not upcoming:
        return None

    start_date, reservation, end_date = min(upcoming, key=lambda item: item[0])
    amount = _reservation_amount(reservation)
    if amount is None:
        amount = _reservation_amount_from_map(reservation, amount_by_reservation_id)
    return {
        "reservation_id": reservation.get("id"),
        "guest_name": _reservation_guest_name(reservation),
        "guest_count": _reservation_guest_count(reservation),
        "guest_profile_url": _reservation_guest_profile_url(reservation),
        "source": reservation.get("source"),
        "amount": amount,
        "start_date": start_date,
        "end_date": end_date,
    }


def _current_reservation(
    reservations: list[dict[str, Any]],
    today: date,
    amount_by_reservation_id: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    active: list[tuple[date, dict[str, Any], date | None]] = []
    for reservation in reservations:
        start_date, end_date = _reservation_dates(reservation)
        if not start_date:
            continue
        if end_date:
            if start_date <= today < end_date:
                active.append((start_date, reservation, end_date))
        elif start_date <= today:
            active.append((start_date, reservation, end_date))
    if not active:
        return None
    start_date, reservation, end_date = min(active, key=lambda item: item[0])
    amount = _reservation_amount(reservation)
    if amount is None:
        amount = _reservation_amount_from_map(reservation, amount_by_reservation_id)
    return {
        "reservation_id": reservation.get("id"),
        "guest_name": _reservation_guest_name(reservation),
        "guest_count": _reservation_guest_count(reservation),
        "guest_profile_url": _reservation_guest_profile_url(reservation),
        "source": reservation.get("source"),
        "amount": amount,
        "start_date": start_date,
        "end_date": end_date,
    }
