from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HostNFlyApi, HostNFlyApiError, HostNFlyAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT,
    CONF_EMAIL,
    CONF_HOST,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_UID,
    DEFAULT_HOST,
    DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class HostNFlyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = HostNFlyApi(
                session=session,
                host=user_input[CONF_HOST],
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
            except HostNFlyAuthError:
                errors["base"] = "invalid_auth"
            except HostNFlyApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - sécurité
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_EMAIL]}@{api.host}")
                self._abort_if_unique_id_configured()
                tokens = api.tokens
                if not tokens:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_EMAIL],
                        data={
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_HOST: api.host,
                            CONF_ACCESS_TOKEN: tokens.access_token,
                            CONF_CLIENT: tokens.client,
                            CONF_UID: tokens.uid,
                        },
                    )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_HOST, default=DEFAULT_HOST): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_reauth(self, user_input: dict[str, str] | None = None) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = HostNFlyApi(
                session=session,
                host=entry.data[CONF_HOST],
                email=entry.data[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
            except HostNFlyAuthError:
                errors["base"] = "invalid_auth"
            except HostNFlyApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - sécurité
                errors["base"] = "unknown"
            else:
                tokens = api.tokens
                if not tokens:
                    errors["base"] = "cannot_connect"
                else:
                    data = {
                        **entry.data,
                        CONF_ACCESS_TOKEN: tokens.access_token,
                        CONF_CLIENT: tokens.client,
                        CONF_UID: tokens.uid,
                    }
                    self.hass.config_entries.async_update_entry(entry, data=data)
                    return self.async_abort(reason="reauth_successful")

        data_schema = vol.Schema({vol.Required(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=data_schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return HostNFlyOptionsFlowHandler(config_entry)


class HostNFlyOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, int] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_LOOKBACK_DAYS,
                    default=options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_LOOKAHEAD_DAYS,
                    default=options.get(CONF_LOOKAHEAD_DAYS, DEFAULT_LOOKAHEAD_DAYS),
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
