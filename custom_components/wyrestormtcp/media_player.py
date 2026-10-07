import logging
import asyncio
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
)
from homeassistant.const import CONF_HOST, CONF_NAME, STATE_OFF, STATE_ON
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "WyreStorm Matrix"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the WyreStorm platform dynamically creating 4 Zone entities."""
    host = config.get(CONF_HOST)
    base_name = config.get(CONF_NAME)

    # Automatically map out 4 separate media player entities for the 4 Outputs
    entities = []
    for zone_id in range(1, 5):
        entities.append(WyreStormOutputZone(host, base_name, zone_id))
        
    async_add_entities(entities, True)


class WyreStormOutputZone(MediaPlayerEntity):
    """Representation of an isolated output zone on the WyreStorm Matrix."""

    def __init__(self, host, base_name, zone_id):
        """Initialize the single zone handler."""
        self._host = host
        self._base_name = base_name
        self._zone_id = zone_id
        self._state = STATE_ON  # Typically matrices stay physically powered on
        self._current_source = None
        
        # Human-friendly source maps exposed to UI dropdown selects
        self._source_map = {
            "Input 1": "hdmiin1",
            "Input 2": "hdmiin2",
            "Input 3": "hdmiin3",
            "Input 4": "hdmiin4",
        }

    @property
    def name(self):
        """Return distinct zone names like 'WyreStorm Matrix Zone 1'."""
        return f"{self._base_name} Zone {self._zone_id}"

    @property
    def unique_id(self):
        """Unique ID to allow configuration modifications inside the HA UI."""
        return f"wyrestorm_{self._host.replace('.', '_')}_zone_{self._zone_id}"

    @property
    def state(self):
        """Return running capability state tracker."""
        return self._state

    @property
    def supported_features(self):
        """Flag input distribution control permissions."""
        return SUPPORT_SELECT_SOURCE | SUPPORT_TURN_ON | SUPPORT_TURN_OFF

    @property
    def source(self):
        """Return the current active input source parsing identifier string."""
        return self._current_source

    @property
    def source_list(self):
        """List of available input source tags."""
        return list(self._source_map.keys())

    async def async_update(self):
        """Query the matrix to find out what source this specific zone is viewing."""
        # Query format syntax: GET status system parameters or read matrix state
        # For WyreStorm H2A, reading current state can be polled or left to optimistic state
        pass

    async def async_turn_on(self):
        """optimistic tracking wrapper state handling."""
        self._state = STATE_ON

    async def async_turn_off(self):
        """optimistic tracking wrapper state handling."""
        self._state = STATE_OFF

    async def async_select_source(self, source):
        """Route chosen hardware inputs to this Zone's corresponding Output slot."""
        if source not in self._source_map:
            _LOGGER.error("Selected source %s is not valid", source)
            return

        input_cmd = self._source_map[source]
        
        # WyreStorm syntax: SET SW hdmiin<X> hdbtout<Y> (or hdmiout depending on topology)
        # We target both video paths or base out output ID parameters
        command = f"SET SW {input_cmd} hdbtout{self._zone_id}"
        
        success = await self._send_telnet_command(command)
        if success:
            self._current_source = source

    async def _send_telnet_command(self, command):
        """Raw thread-safe Telnet wrapper communicating on TCP 23."""
        try:
            # Enforce short execution connection cutoffs to protect HA Loop
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, 23), timeout=2.5
            )
            
            # Format requires exact Carriage Return + Line Feed execution frame sequence
            payload = f"{command}\r\n"
            writer.write(payload.encode("ascii"))
            await writer.drain()
            
            # Read confirmation feedback buffer frame response
            response = await reader.read(128)
            _LOGGER.debug("WyreStorm Matrix response: %s", response.decode().strip())
            
            writer.close()
            await writer.wait_closed()
            return True
            
        except Exception as err:
            _LOGGER.error("Telnet connection error on WyreStorm %s: %s", self._host, err)
            return False
