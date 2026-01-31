from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HostNFlyApi, HostNFlyTokens
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT,
    CONF_EMAIL,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_UID,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HostNFlyCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    tokens = None
    if (
        entry.data.get(CONF_ACCESS_TOKEN)
        and entry.data.get(CONF_CLIENT)
        and entry.data.get(CONF_UID)
    ):
        tokens = HostNFlyTokens(
            access_token=entry.data[CONF_ACCESS_TOKEN],
            client=entry.data[CONF_CLIENT],
            uid=entry.data[CONF_UID],
        )
    api = HostNFlyApi(
        session=session,
        host=entry.data[CONF_HOST],
        email=entry.data[CONF_EMAIL],
        password=entry.data.get(CONF_PASSWORD),
        tokens=tokens,
    )
    coordinator = HostNFlyCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    if api.tokens and (
        CONF_PASSWORD in entry.data or CONF_ACCESS_TOKEN not in entry.data
    ):
        data = {**entry.data}
        data[CONF_ACCESS_TOKEN] = api.tokens.access_token
        data[CONF_CLIENT] = api.tokens.client
        data[CONF_UID] = api.tokens.uid
        data.pop(CONF_PASSWORD, None)
        hass.config_entries.async_update_entry(entry, data=data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
