"""
Room Light Control integration for Home-Assistant.

Room Light Control is a smart home integration designed to automatically control the lights in a specific room of your house. 
Using a combination of sensors and logic, the automation creates a natural and convenient experience when you enter and exit the room.

------------

Version: 1.0.2

"""

from email.policy import default
import hashlib
import logging
import math
import re
from datetime import date, datetime, time, timedelta
from threading import Timer
import pprint
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_NAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import HomeAssistant, callback, Context
from homeassistant.helpers import entity, event, service
from homeassistant.helpers.template import Template
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt
import homeassistant.util.uuid as uuid_util
from transitions import Machine
from transitions.extensions import HierarchicalMachine as Machine
from homeassistant.helpers.service import async_call_from_config

from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from homeassistant.helpers import area_registry, device_registry, entity_registry

## --> Workaround because colormath is build upon old version of numpy numpy droped support for 'patch_asscalar'
import numpy

def patch_asscalar(a):
    return a.item()

setattr(numpy, "asscalar", patch_asscalar)
## <-- Workaround because colormath is build upon old version of numpy numpy droped support for 'patch_asscalar'

DEPENDENCIES = ["light", "sensor", "binary_sensor"]
from .const import (
    DOMAIN,
    DOMAIN_SHORT,
    STATES,

    DEFAULT_DELAY,
    DEFAULT_ILLUMINANCE_THRESHOLD,
    CONF_TURN_ON_LIGHT,
    CONF_TURN_OFF_LIGHT,
    CONF_ROOM,
    CONF_ROOMS,
    CONF_MOTION_SENSOR,
    CONF_MOTION_SENSORS,
    CONF_TURN_OFF_SENSOR,
    CONF_ILLUMINANCE_SENSOR,
    CONF_ILLUMINANCE_SENSOR_THRESHOLD,
    CONF_TURN_OFF_BLOCKING_ENTITY,
    CONF_TURN_OFF_BLOCKING_ENTITIES,
    CONF_TURN_OFF_DELAY,
    CONF_MOTION_SENSOR_RESETS_TIMER,

    CONTEXT_ID_CHARACTER_LIMIT
)

_LOGGER = logging.getLogger(__name__)

devices = []
MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TURN_OFF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
    }
)

ENTITY_SCHEMA = vol.Schema(
    cv.has_at_least_one_key(
        CONF_TURN_ON_LIGHT
    ),
    {
        vol.Required(CONF_ROOM, default=[]): cv.entity_ids,
        vol.Required(CONF_ROOMS, default=[]): cv.entity_ids,
        vol.Optional(CONF_TURN_OFF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
        vol.Optional(CONF_MOTION_SENSOR_RESETS_TIMER, default=False): cv.boolean,
        vol.Required(CONF_MOTION_SENSOR, default=[]): cv.entity_ids,
        vol.Required(CONF_MOTION_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_TURN_OFF_SENSOR, default=[]): cv.entity_ids,
        vol.Optional(CONF_TURN_OFF_BLOCKING_ENTITY, default=[]): cv.entity_ids,
        vol.Optional(CONF_TURN_OFF_BLOCKING_ENTITIES, default=[]): cv.entity_ids,
        vol.Optional(CONF_ILLUMINANCE_SENSOR, default=None): cv.entity_id,
        vol.Optional(CONF_ILLUMINANCE_SENSOR_THRESHOLD, default=DEFAULT_ILLUMINANCE_THRESHOLD): cv.small_float,
        vol.Required(CONF_TURN_ON_LIGHT, default=None): cv.entity_ids,
        vol.Optional(CONF_TURN_OFF_LIGHT, default=None): cv.entity_ids,
    },
)

PLATFORM_SCHEMA = cv.schema_with_slug_keys(ENTITY_SCHEMA)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:   
    machine = setup_state_machine()

    async def activate_on_start(_):
        """Activate automation."""
        await activate_automation(hass, config, machine)

    if hass.is_running:
        await activate_on_start(None)
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, activate_on_start)

    return True

def setup_state_machine():
    machine = Machine(
        states=STATES,
        initial="idle",
        finalize_event="finalize"
    )

    # Idle
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_off", "is_illuminance_equal_or_below_threshold"],
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="blocked",
        conditions=["is_state_entities_on"],
    )
    machine.add_transition(
        trigger="shouldClearBlock", 
        source="idle", 
        dest=None, 
        conditions=["is_state_entities_off"]
    )

    # Blocked
    machine.add_transition(
        trigger="shouldClearBlock", 
        source="blocked", 
        dest="idle", 
        conditions=["is_state_entities_off"],
    )

    machine.add_transition(
        trigger="sensor_on", 
        source="blocked", 
        dest="blocked"
    )  # re-entering self-transition (on_enter callback executed.)

    # Active
    machine.add_transition(
        trigger="enter", 
        source="active", 
        dest="active_control", 
    )

    # Active Control
    machine.add_transition(
        trigger="sensor_on", 
        source="active_control", 
        dest=None, 
        after="_reset_timer"
    )
    
    machine.add_transition(
        trigger="motion_sensor_off",
        source="active_control",
        dest="idle",
        conditions=["is_timer_expired"],
        unless=["is_turn_off_blocked"]
    )

    machine.add_transition(
        trigger="motion_sensor_off",
        source="active_control",
        dest="blocked",
        conditions=["is_turn_off_blocked"],
    )
    
    # Active control
    machine.add_transition(
        trigger="shouldBlock",
        source="active_control",
        dest="idle",
        conditions=["is_state_entities_off"],
        unless=["is_turn_off_blocked"]
    )

    machine.add_transition(
        trigger="shouldBlock", 
        source="active_control",
        dest='blocked', 
        conditions=['is_state_entities_on']
    )

    machine.add_transition(
        trigger="timer_expires",
        source="active_control",
        dest="idle",
        conditions=["is_motion_sensor_off", "is_turn_off_sensor_off"],
        unless=["is_turn_off_blocked"]
    )

    machine.add_transition(
        trigger="timer_expires",
        source="active_control",
        dest="blocked",
        conditions=["is_turn_off_blocked"],
    )    

    machine.add_transition(
        trigger="turn_off_sensor_on",
        source="active_control",
        dest="idle",
        unless=["is_turn_off_blocked"]
    )

    machine.add_transition(
        trigger="turn_off_sensor_on",
        source="active_control",
        dest="blocked",
        conditions=["is_turn_off_blocked"],
    )
    
    return machine

async def activate_automation(hass, config, machine):
    """Activate the automation."""

    component = EntityComponent(_LOGGER, DOMAIN, hass)

    for myconfig in config[DOMAIN]:
        _LOGGER.info("Domain Configuration: " + str(myconfig))
        for key, config in myconfig.items():
            if not config:
                config = {}

            config["name"] = key
            m = None
            m = RoomLightController(hass, config, machine)
            devices.append(m)

    await component.async_add_entities(devices)

    _LOGGER.info("The %s component is ready!", DOMAIN)

class RoomLightController(entity.Entity):

    def __init__(self, hass, config, machine):
        self.attributes = {}
        self.may_update = False
        self.model = None
        self.friendly_name = config.get(CONF_NAME, "Motion Light")
        if "friendly_name" in config:
            self.friendly_name = config.get("friendly_name")
        try:
            self.model = Model(hass, config, machine, self)
        except AttributeError as e:
            _LOGGER.error(
                "Configuration error! Please ensure you use plural keys for lists. e.g. sensors, entities." + e
            )
        event.async_call_later(hass, 1, self.do_update)

    @property
    def state(self):
        """Return the state of the entity."""
        return self.model.state

    @property
    def name(self):
        """Return the state of the entity."""
        return self.friendly_name

    @property
    def icon(self):
        """Return the entity icon."""
        if self.model.state == "idle":
            return "mdi:circle-outline"
        if self.model.state == "active":
            return "mdi:check-circle"
        if self.model.state == "active_control":
            return "mdi:timer-outline"
        if self.model.state == "blocked":
            return "mdi:close-circle"
        return "mdi:eye"

    @property
    def state_attributes(self):
        """Return the state of the entity."""
        return self.attributes.copy()

    def reset_state(self):
        """ Reset state attributes by removing any state specific attributes when returning to idle state """
        _LOGGER.debug("Resetting state")
        att = {}

        # These will be kept after the state returns to idle
        PERSISTED_STATE_ATTRIBUTES = [
            "last_triggered_by",
            "last_triggered_at",
            "room_lights",
            "sensor_entities",
            CONF_ILLUMINANCE_SENSOR,
            CONF_ILLUMINANCE_SENSOR_THRESHOLD,
            CONF_TURN_OFF_DELAY,
        ]
        for k, v in self.attributes.items():
            if k in PERSISTED_STATE_ATTRIBUTES:
                att[k] = v

        _LOGGER.debug(att)

        self.attributes = att
        self.do_update()

    @callback
    def do_update(self, wait=False, **kwargs):
        """ Schedules an entity state update with HASS """
        if self.may_update:
            self.async_schedule_update_ha_state(True)

    def set_attr(self, k, v):
        if k == CONF_TURN_OFF_DELAY:
            v = str(v) + "s"
        self.attributes[k] = v

    # HA Callbacks
    async def async_added_to_hass(self):
        """Register update dispatcher."""
        self.may_update = True

    @property
    def should_poll(self) -> bool:
        """RoomLightController will push its state to HA"""
        return False

class Model:
    """ Represents the transitions state machine model """

    def __init__(self, hass, config, machine, entity):
        self.hass = hass  
        self.entity = entity

        self.config = (
            {}
        )  
        self.config = config
        self.room = []
        self.roomLightEntities = []
        self.motionSensorEntities = []
        self.turnOffSensorEntities = []
        self.turnOffBlockingEntities = []
        self.illuminanceSensorEntity = None
        self.illuminanceSensorThreshold = None
        self.turnOffDelay = None
        self.turnOffScript = []
        self.turnOnScene = []
        self.timer_handle = None
        self.name = None
        self.log = logging.getLogger(__name__ + "." + config.get(CONF_NAME))
        self.context = None

        self.log.debug(
            "Initialising RoomLightController entity with this configuration: "
        )
        self.log.debug(
            pprint.pformat(config)
        )
        self.name = config.get(CONF_NAME, "NoName")

        machine.add_model(
            self
        )  # add here because machine generated methods are being used in methods below.
        self.setup_area_entities(config)
        self.config_static_strings(config)
        self.config_sensor_entities(config)
        self.config_illuminance_sensor_entity(config)
        self.config_turn_off_script(config)
        self.config_turn_on_scene(config)
        self.config_turn_off_delay(config)
        self.config_other(config)
        self.prepare_service_data()

        self.log_config()

    def update(self, wait=False, **kwargs):
        """ Called from different methods to report a state attribute change """
        self.log.debug("Update called with {}".format(str(kwargs)))
        for k, v in kwargs.items():
            if v is not None:
                self.entity.set_attr(k, v)

        if wait == False:
            self.entity.do_update()

    def finalize(self):
        self.entity.do_update()

    # =====================================================
    # S T A T E   C H A N G E   C A L L B A C K S
    # =====================================================

    @callback
    def motion_sensor_state_change(self, entity, old, new):
        """ State change callback for motion sensor entities """
        self.log.debug("motion_sensor_state_change :: %10s Sensor state change to: %s" % ( pprint.pformat(entity), new.state))
        self.log.debug("motion_sensor_state_change :: state: " +  pprint.pformat(self.state))

        try:
            if new.state == old.state:
                self.log.debug("motion_sensor_state_change :: Ignore attribute only change")
                return
        except AttributeError:
            self.log.debug("motion_sensor_state_change :: old NoneType")
            pass

        if self.matches(new.state, self.SENSOR_ON_STATE) and (self.is_idle() or self.is_active_control() or self.is_blocked()):
            self.log.debug("motion_sensor_state_change :: motion sensor turned on")
            self.set_context(new.context)
            self.update(last_triggered_by=entity)
            if self.is_illuminance_sensor_available() :
                self.update(illuminance_sensor_on_last_motion=self.hass.states.get(self.illuminanceSensorEntity).state)
            self.sensor_on()

        if self.matches(new.state, self.SENSOR_OFF_STATE) and self.is_active_control():
            self.log.debug("motion_sensor_state_change :: motion sensor turned off")
            self.set_context(new.context)

            # If configured, reset timer when sensor goes off
            if self.config[CONF_MOTION_SENSOR_RESETS_TIMER]:
                self.log.debug("motion_sensor_state_change :: CONF_MOTION_SENSOR_RESETS_TIMER")
                self.update(notes="The sensor turned off and reset the timeout. Timer started.")
                self._reset_timer()
            else: 
                self.motion_sensor_off()

    @callback
    def turn_off_sensor_state_change(self, entity, old, new):
        """ State change callback for turn off sensor entities """
        self.log.debug("turn_off_sensor_state_change :: %10s Sensor state change to: %s" % ( pprint.pformat(entity), new.state))
        self.log.debug("turn_off_sensor_state_change :: state: " +  pprint.pformat(self.state))       

        # prevent any errors while initializing entities. e.g. during startup
        if old is None:
            return

        if self.matches(old.state, self.SENSOR_ON_STATE) and self.matches(new.state, self.SENSOR_OFF_STATE) and (
            self.is_active_control() or self.is_blocked()):
            self.log.debug("The turn off sensor turned to off, so let's try going back to idle.")
            self.turn_off_sensor_on()


    @callback
    def illuminance_sensor_state_change(self, entity, old, new):      
        """ State change callback for the illuminance sensor"""       
        self.log.debug("illuminance_sensor_state_change :: %10s Sensor state change to: %s" % ( pprint.pformat(entity), new.state))
        self.log.debug("illuminance_sensor_state_change :: state: " +  pprint.pformat(self.state))           

    def has_significant_color_change(self, old_state, new_state, rel_tol):
        color_mode = new_state.attributes.get('color_mode', None)

        # Check for significant xy_color change if the light is in xy color mode
        if color_mode == 'xy':
            old_xy = old_state.attributes.get('xy_color')
            new_xy = new_state.attributes.get('xy_color')
            if old_xy and new_xy:
                # Calculate the Euclidean distance for xy_color
                xy_distance = math.sqrt((old_xy[0] - new_xy[0]) ** 2 + (old_xy[1] - new_xy[1]) ** 2)
                max_distance = max(math.sqrt(old_xy[0] ** 2 + old_xy[1] ** 2), math.sqrt(new_xy[0] ** 2 + new_xy[1] ** 2))
                significant_change = xy_distance / max_distance > rel_tol
                if significant_change:
                    return True

        # Check for significant color_temp change if the light is in color_temp mode
        elif color_mode == 'color_temp':
            old_ct = old_state.attributes.get('color_temp')
            new_ct = new_state.attributes.get('color_temp')
            if old_ct is not None and new_ct is not None:
                # Use math.isclose for color_temp with a relative tolerance
                if not math.isclose(old_ct, new_ct, rel_tol=rel_tol):
                    return True
                
        # check rgb color attribute if available
        if "rgb_color" in old_state.attributes and "rgb_color" in new_state.attributes:
            old_rgb_r, old_rgb_g, old_rgb_b = old_state.attributes["rgb_color"]
            new_rgb_r, new_rgb_g, new_rgb_b = new_state.attributes["rgb_color"]

            # We need to apply some tolerance to ignore oscillating values reported by the device
            delta_e = self.calc_delta_e(old_rgb_r, old_rgb_g, old_rgb_b, new_rgb_r, new_rgb_g, new_rgb_b)
            self.log.debug("%s: Delta-E Color difference = %s", str(entity), str(delta_e))

            if delta_e > 1.0:
                self.log.info("state_entity_state_change :: Significant rgb color change old = %s, new = %s", old_state.attributes["rgb_color"], new_state.attributes["rgb_color"])
                return True              

        # No significant change detected
        return False


    @callback
    def state_entity_state_change(self, entity, old, new):
        """ State change callback for state entities. This can be called with either a state change or an attribute change. """
        self.log.debug(
            "state_entity_state_change :: [ Entity: %s, Context: %s ]\n\tOld state: %s\n\tNew State: %s",
            str(entity),
            str(new.context),
            str(old),
            str(new)
        )

        if self.is_ignored_context(new.context) or self.is_within_grace_period() or old is None:
            self.log.debug("state_entity_state_change :: Ignoring this state change.")
            return

        # If the state changed, we definitely want to handle the transition. If only attributes changed, 
        # we'll check if the new attributes are significant (i.e., not being ignored).
        if old.state != new.state:  # State changed
            self.handle_state_change(new)
        else:  # Only attributes changed
            changed_attributes = []

            # check brightness attribute if available
            if "brightness" in old.attributes and "brightness" in new.attributes:
                old_b = old.attributes["brightness"]
                new_b = new.attributes["brightness"]
                if not math.isclose(old_b, new_b, rel_tol=0.02): # We need to apply some tolerance to ignore oscillating values reported by the device
                    self.log.info("state_entity_state_change :: Significant brightness change old = %s, new = %s", old_b, new_b)
                    changed_attributes.append("brightness")

            if self.has_significant_color_change(old, new, 0.02):
                self.log.info("state_entity_state_change :: Significant color change detected for %s.", entity)      
                changed_attributes.append("color")      

            if len(changed_attributes) > 0:
                self.log.info("state_entity_state_change :: We have significant attribute change and will handle it: %s", changed_attributes)
                self.handle_state_change(new)

    def handle_state_change(self, new):
        self.set_context(new.context)

        if self.is_active_control():
            self.log.info("handle_state_change :: We are in active control and the state of observed state entities changed.")
            self.shouldBlock()

        if self.is_blocked():
            self.log.info("handle_state_change :: We are in blocked state and the state of observed state entities changed.")
            self.shouldClearBlock()

    def _start_timer(self):
        self.log.info("_start_timer :: Delay: " + str(self.turnOffDelay))
        expiry_time = datetime.now() + timedelta(seconds=self.turnOffDelay)

        self.timer_handle = Timer(self.turnOffDelay, self.timer_expire)
        self.timer_handle.start()
        self.update(turn_off_delay=self.turnOffDelay, expires_at=expiry_time)

    def _cancel_timer(self):
        if self.timer_handle.is_alive():
            self.timer_handle.cancel()

    def _reset_timer(self):
        self.log.debug("_reset_timer :: Resetting timer")
        self._cancel_timer()
        self.update(reset_at=datetime.now())
        self._start_timer()

        return True


    def timer_expire(self):
        self.log.debug("timer_expire :: Timer expired")
        if self.is_motion_sensor_on():
            self.update(expires_at="waiting for motion sensor off event")
        else:
            self.log.debug("timer_expire :: Trigger timer_expires event")
            
            if self.is_turn_off_sensor_off():
                self.log.debug("Turn_off_sensor timeout reached")

            self.timer_expires()            

    # =====================================================
    # S T A T E   M A C H I N E   C O N D I T I O N S
    # =====================================================
    def is_within_grace_period(self):
        """ This is important or else we will react to state changes caused by ourselve which results in going into blocked state."""
        return datetime.now() < self.ignore_state_changes_until

    def _motion_sensor_entity_state(self):
        for e in self.motionSensorEntities:
            s = self.hass.states.get(e)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: Motion Sensor Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                return None

            if self.matches(state, self.SENSOR_ON_STATE):
                self.log.debug("Sensor entities are ON. [%s]", e)
                return e
        self.log.debug("Sensor entities are OFF.")
        return None
    
    def _turn_off_sensor_entity_state(self):
        for e in self.turnOffSensorEntities:
            s = self.hass.states.get(e)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: Turn Off Sensor Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                return None

            if self.matches(state, self.SENSOR_ON_STATE):
                self.log.debug("Turn Off Sensor entities are ON. [%s]", e)
                return e
        self.log.debug("Turn Off Sensor entities are OFF.")
        return None    

    def is_motion_sensor_off(self):
        return self._motion_sensor_entity_state() is None

    def is_motion_sensor_on(self):
        return self._motion_sensor_entity_state() is not None
    
    def is_turn_off_sensor_off(self):
        if not self.is_turn_off_sensor_available():
            return True
        
        return self._turn_off_sensor_entity_state() is None

    def _state_entity_state(self):
        for e in self.roomLightEntities:
            s = self.hass.states.get(e)
            self.log.info(s)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: State Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                state = 'off'
                return None

            if self.matches(state, self.STATE_ON_STATE):
                self.log.debug("State entities are ON. [%s]", e)
                return e
        self.log.debug("State entities are OFF.")
        return None

    def _turn_off_blocking_entity_state(self):
        for e in self.turnOffBlockingEntities:
            s = self.hass.states.get(e)
            self.log.info(s)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: State Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                state = 'off'
                return None

            if self.matches(state, self.STATE_ON_STATE):
                self.log.debug("Blocking entities are ON. [%s]", e)
                return e
        self.log.debug("Blocking entities are OFF.")
        return None        

    def is_illuminance_equal_or_below_threshold(self)  -> bool:
        if not self.is_illuminance_sensor_available() :
            self.log.debug("Illuminance Sensor is not configured, so below_threshold always triggered")
            return True

        s = self.hass.states.get(self.illuminanceSensorEntity)
        self.log.debug("Current light level: {}, Threshold: {} (lux)".format(s.state, self.illuminanceSensorThreshold))
        isBelow = float(s.state) < float(self.illuminanceSensorThreshold)
        self.log.info("Illuminance threshold reached: {}".format(isBelow))

        return isBelow

    def is_illuminance_sensor_available(self) -> bool:
        return self.illuminanceSensorEntity is not None

    def is_state_entities_off(self):
        return self._state_entity_state() is None

    def is_state_entities_on(self):
        return self._state_entity_state() is not None

    def is_turn_off_blocked(self) -> bool:
        for e in self.turnOffBlockingEntities:
            s = self.hass.states.get(e)
            state = s.state

            if self.matches(state, self.STATE_ON_STATE):
                self.log.debug("Blocking entities are ON. [%s]", e)
                return True
        
        self.log.debug("Blocking entities are OFF.")
        return False

    def is_timer_expired(self):
        expired = self.timer_handle.is_alive() == False
        return expired

    def does_sensor_reset_timer(self):
        return self.config[CONF_MOTION_SENSOR_RESETS_TIMER]

    def calc_delta_e(self, color1_r, color1_g, color1_b, color2_r, color2_g, color2_b) -> float:
        self.log.info("ColorMath")

        color1_rgb = sRGBColor(color1_r, color1_g, color1_b)
        color2_rgb = sRGBColor(color2_r, color2_g, color2_b)

        # Convert from RGB to Lab Color Space
        color1_lab = convert_color(color1_rgb, LabColor)
        color2_lab = convert_color(color2_rgb, LabColor)

        # Find the color difference
        delta_e = delta_e_cie2000(color1_lab, color2_lab)

        return delta_e

    # =====================================================
    # S T A T E   M A C H I N E   C A L L B A C K S
    # =====================================================
    def on_enter_idle(self):
        self.log.debug("Entering idle")

        # Entering idle due to no events, set a new context with no parent
        self.set_context(None)
        self.log.debug("Turning off Light Entities")
        self.turnOffLightEntities()

        self.entity.reset_state()

    def on_exit_idle(self):
        self.log.debug("Exiting idle")

    def on_enter_active(self):
        self.log.debug("Entering active")
        self.update(last_triggered_at=str(datetime.now()))
        self.prepare_service_data()

        # we start the timer in any case, also if a turn off sensor is configured. In later case it acts as timeout timer.
        self._start_timer()

        self.log.debug("Turning on Light Entities")
        self.turnOnLightEntities()

        self.enter()

    def on_exit_active(self):
        self.log.debug("Exiting active")
        self.log.debug("on_exit_active :: cancelling timer")

        self._cancel_timer()  # cancel previous timer

    def on_enter_blocked(self):
        self.log.debug("Entering blocked")
        self.update(blocked_at=datetime.now())
        if self.is_turn_off_blocked():
            self.update(blocked_by=self._turn_off_blocking_entity_state())
        else:
            self.update(blocked_by=self._state_entity_state())

    def on_exit_blocked(self):
        self.log.debug("Exiting blocked")

    # =====================================================
    #    C O N F I G U R A T I O N  &  V A L I D A T I O N
    # =====================================================
        
    def setup_area_entities(self, config):
        self.add(self.room, config, CONF_ROOM)
        self.add(self.room, config, CONF_ROOMS)

        self.log.debug("Setting up room: %s", self.room)

        if len(self.room) == 0:
            self.log.error(
                "No rooms defined. You must define at least one room."
            )
            return

        self.roomLightEntities = []    

        for x in self.room:
            area_id = self.get_area_id(x.lower())
            self.log.debug("area_id: %s", area_id)
        
            room_lights = self.get_entities_for_area(area_id, 'light')
            self.log.debug("room_lights: %s", room_lights)
            self.roomLightEntities.extend(room_lights)

        self.update(room_lights=self.roomLightEntities)

        event.async_track_state_change(
        self.hass, self.roomLightEntities, self.state_entity_state_change)

    def get_area_name(self, area_id):
        area_reg = area_registry.async_get(self.hass)
        area = area_reg.async_get_area(area_id)
        if area is not None:
            return area.name

    def get_area_id(self, area_name):
        area_reg = area_registry.async_get(self.hass)
        area = area_reg.async_get_area_by_name(area_name.lower())

        if area is not None:
            return area.id        

    def get_entities_for_area(self, area_id, domain=None, device_class=None):
        device_reg = device_registry.async_get(self.hass)
        entity_reg = entity_registry.async_get(self.hass)
        entities = []

        area_devices = device_registry.async_entries_for_area(device_reg, area_id)

        device_entities_by_device = []
        [device_entities_by_device.extend(entity_registry.async_entries_for_device(entity_reg, x.id)) for x in area_devices]   
        
        entities.extend(device_entities_by_device)

        #self.log.info("room entities: %s", entities)   
        
        if domain is not None:
            entities=[e for e in entities if e.entity_id.startswith(domain)]
        if device_class is not None:
            entities=[e for e in entities if e.device_class==device_class]
        if entities==[]:
            return []
        else:
            return [e.entity_id for e in (entities or [])]                                

    def config_turn_off_script(self, config):

        self.turnOffScript = []
        self.add(self.turnOffScript, config, CONF_TURN_OFF_LIGHT)
        if len(self.turnOffScript) > 0:
            self.log.info("Turn Off Scripts: " +  pprint.pformat(self.turnOffScript))

    def config_turn_on_scene(self, config):
        self.turnOnScene = []
        self.add(self.turnOnScene, config, CONF_TURN_ON_LIGHT)
        if len(self.turnOnScene) > 0:
            self.log.info("Turn On Scenes: " +  pprint.pformat(self.turnOnScene))

    def config_sensor_entities(self, config):
        self.motionSensorEntities = []
        self.add(self.motionSensorEntities, config, CONF_MOTION_SENSOR)
        self.add(self.motionSensorEntities, config, CONF_MOTION_SENSORS)

        if len(self.motionSensorEntities) == 0:
            self.log.error(
                "No sensor entities defined. You must define at least one sensor entity."
            )

        self.log.debug("Motion Sensor Entities: " +  pprint.pformat(self.motionSensorEntities))

        event.async_track_state_change(
            self.hass, self.motionSensorEntities, self.motion_sensor_state_change
        )

        self.turnOffSensorEntities = []
        self.add(self.turnOffSensorEntities, config, CONF_TURN_OFF_SENSOR)
        if self.is_turn_off_sensor_available() :
            self.log.info("Using turn off sensor entities to turn off light, instead of timer")
            event.async_track_state_change(
                self.hass, self.turnOffSensorEntities, self.turn_off_sensor_state_change
            )

    def is_turn_off_sensor_available(self) -> bool:
        return len(self.turnOffSensorEntities) > 0

    def config_illuminance_sensor_entity(self, config):
        self.illuminanceSensorEntity = config.get(CONF_ILLUMINANCE_SENSOR, None)
        self.illuminanceSensorThreshold = config.get(CONF_ILLUMINANCE_SENSOR_THRESHOLD)

        self.log.debug("Illuminance Sensor Entity: {}".format(self.illuminanceSensorEntity))
        self.log.debug("Illuminance Sensor Threshold: {}".format(self.illuminanceSensorThreshold))
        
        if self.illuminanceSensorEntity is not None :
            event.async_track_state_change(
                self.hass, self.illuminanceSensorEntity, self.illuminance_sensor_state_change
            )

    def config_static_strings(self, config):
        DEFAULT_ON = ["on", "playing", "home", "True"]
        DEFAULT_OFF = ["off", "idle", "paused", "away", "False"]
        self.SENSOR_ON_STATE = config.get("sensor_states_on", DEFAULT_ON)
        self.SENSOR_OFF_STATE = config.get("sensor_states_off", DEFAULT_OFF)
        self.STATE_ON_STATE = config.get("state_states_on", DEFAULT_ON)
        self.STATE_OFF_STATE = config.get("state_states_off", DEFAULT_OFF)

        on = config.get("state_strings_on", False)
        if on:
            self.SENSOR_ON_STATE.extend(on)
            self.STATE_ON_STATE.extend(on)

        off = config.get("state_strings_off", False)
        if off:
            self.SENSOR_OFF_STATE.extend(off)
            self.STATE_OFF_STATE.extend(off)

    def config_turn_off_delay(self, config):
        self.turnOffDelay = config.get(CONF_TURN_OFF_DELAY, DEFAULT_DELAY)

    def config_other(self, config):
        self.ignore_state_changes_until = datetime.now()

        self.config[CONF_MOTION_SENSOR_RESETS_TIMER] = config.get(CONF_MOTION_SENSOR_RESETS_TIMER)

        self.turnOffBlockingEntities = []
        self.add(self.turnOffBlockingEntities, config, CONF_TURN_OFF_BLOCKING_ENTITY)
        self.add(self.turnOffBlockingEntities, config, CONF_TURN_OFF_BLOCKING_ENTITIES)

    # =====================================================
    #    H E L P E R   F U N C T I O N S        
    # =====================================================

    # turnOffScript (either a script or directly light entities)
    def turnOffLightEntities(self):
        if len(self.turnOffScript) > 0:
            self.log.info("turnOffLightEntities :: Turning Off the Lights! (%s)", self.turnOffScript)
            for e in self.turnOffScript:
                self.call_service(e, "turn_on")
        else:
            self.log.info("turnOffLightEntities :: Turning Off the Lights! (%s)", self.roomLightEntities)
            for e in self.roomLightEntities:
                self.call_service(e, "turn_off")

    # turnOnScene (either a script or a scene)
    def turnOnLightEntities(self):
        if len(self.turnOnScene) > 0:
            self.log.info("turnOnLightEntities :: Turning On the Lights!")
            for e in self.turnOnScene:
                self.call_service(e, "turn_on")


    # =====================================================
    #    H E L P E R   F U N C T I O N S    ( C U S T O M )
    # =====================================================

    def prepare_service_data(self):
        """
            Called when entering active state and on initial set up to set
            correct service parameters.
        """
        if self.is_turn_off_sensor_available():
            self.update(turn_off_delay="Controlled by turn off sensor (%d)" % self.turnOffDelay)
        else:
            self.update(turn_off_delay=self.turnOffDelay)


        self.update(illuminance_sensor=self.illuminanceSensorEntity)
        self.update(illuminance_sensor_threshold=self.illuminanceSensorThreshold)

    def call_service(self, entity, service, **service_data):
        self.log.debug("call_service :: Calling service " + service + " on " + entity)
        self.ignore_state_changes_until = datetime.now() + timedelta(seconds=2)
        self.log.debug("call_service :: Setting ignore_state_changes_until to " + str(self.ignore_state_changes_until))

        domain, e = entity.split(".")
        params = {}
        if service_data is not None:
            params = service_data

        params["entity_id"] = entity        
        self.hass.async_create_task(
            self.hass.services.async_call(domain, service, service_data, context=self.context)
        )

    def set_context(self, parent: Optional[Context] = None) -> None:
        """Set the context used when calling other services.

        The new ID is linked to the context (`parent`) of the triggering event
        and will be unique per trigger.
        """
        # Unique name per EC instance, but short enough to fit within id length
        name_hash = hashlib.sha1(self.name.encode("UTF-8")).hexdigest()[:6]
        unique_id = uuid_util.random_uuid_hex()
        context_id = f"{DOMAIN_SHORT}_{name_hash}_{unique_id}"
        # Restrict id length to database field size
        context_id = context_id[:CONTEXT_ID_CHARACTER_LIMIT]
        # parent_id only exists for a non-None parent
        parent_id = parent.id if parent else None
        self.context = Context(parent_id=parent_id, id=context_id)
        # Set the EC entity's context so the logbook can identify the source of
        # events that will be generated by this object.
        self.entity.async_set_context(self.context)

    def is_ignored_context(self, context: Context) -> bool:
        if context.id.startswith(f"{DOMAIN_SHORT}_"):
            return True
        return False

    def matches(self, value, list):
        """
            Checks whether a string is contained in a list (used for matching state strings)
        """
        try:
            index = list.index(value)
            return True
        except ValueError:
            return False

    def add(self, list, config, key=None):
        if key in config:
            value = config[key]
            if isinstance(value, str):
                value = [value]  # Wrap the single string in a list
            list.extend(value)

    def log_config(self):
        self.log.debug("--------------------------------------------------")
        self.log.debug("       C O N F I G U R A T I O N   D U M P        ")
        self.log.debug("--------------------------------------------------")
        self.log.debug("Room Light Control              %s", self.name)
        self.log.debug("Room                            %s", str(self.room))        
        self.log.debug("Room Lights:                    %s", str(self.roomLightEntities))        
        self.log.debug("Motion Sensors                  %s", str(self.motionSensorEntities))
        self.log.debug("Turn Off Sensors                %s", str(self.turnOffSensorEntities))
        self.log.debug("Illuminance Sensor              %s", str(self.illuminanceSensorEntity))
        self.log.debug("Illuminance Sensor Threshold    %s", str(self.illuminanceSensorThreshold))
        self.log.debug("Turn On - Scene or Script:      %s", str(self.turnOnScene))
        self.log.debug("Turn Off - Script:              %s", str(self.turnOffScript))
        self.log.debug("Turn Off - Blocking Entities    %s", str(self.turnOffBlockingEntities))        
        self.log.debug("Turn Off - Delay:               %s", str(self.turnOffDelay))
        self.log.debug("--------------------------------------------------")