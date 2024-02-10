""" Constants used by other files """

DOMAIN = "room_light_control"
DOMAIN_SHORT = "rlc"

#-> Input Variables
CONF_ROOM = "room"
CONF_ROOMS = "rooms"

CONF_MOTION_SENSOR = "motion_sensor"
CONF_MOTION_SENSORS = "motion_sensors"
CONF_MOTION_SENSOR_RESETS_TIMER = "motion_sensor_resets_timer"

CONF_TURN_OFF_SENSOR = "turn_off_sensor"

CONF_ILLUMINANCE_SENSOR = "illuminance_sensor"
CONF_ILLUMINANCE_SENSOR_THRESHOLD = "illuminance_sensor_threshold"
DEFAULT_ILLUMINANCE_THRESHOLD = 5.0

DEFAULT_DELAY = 180

# turn_on_light (either script or scene)
CONF_TURN_ON_LIGHT = "turn_on_light"
# turn_off_light (script)
CONF_TURN_OFF_LIGHT = "turn_off_light"
# timeout
CONF_TURN_OFF_DELAY = "turn_off_delay"

CONF_TURN_OFF_BLOCKING_ENTITY = "turn_off_blocking_entity"
CONF_TURN_OFF_BLOCKING_ENTITIES = "turn_off_blocking_entities"

STATES = ['idle', 'blocked',
          {'name': 'active', 'children': ['control'],
           'initial': False}]
CONF_IGNORE_STATE_CHANGES_UNTIL = "grace_period"


CONTEXT_ID_CHARACTER_LIMIT = 26