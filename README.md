# Room Light Control (1.0.5-beta)

Room Light Control is a Home Assistant integration designed to automatically control the lights in a specific room of your house. Using a combination of sensors and logic, the automation creates a natural and convenient experience when you enter and exit the room.

## Features

- **Automatic Light Control**: Lights in a room are automatically discovered and controlled without any additional configuration. The integration uses the lights assigned to a room (a.k.a area) to seamlessly manage turning them on and off based on motion or presence sensors.
- **Simplified Setup**: No need to manually configure individual lights — just assign your lights to a room in Home Assistant, and Room Light Control takes care of the rest.
- **Scene or Script Activation**: Optionally, specify a scene or script to activate for more complex lighting setups. When configured, these scenes or scripts can define exactly how the lights turn on, providing full control over the lighting atmosphere.
- **Human Presence Detection**: Supports advanced sensors like the Aqara FP1 (mmWave sensors) to detect human presence and control lights accordingly.
- **Automatic Lights-Off Logic**: Lights turn off based on a timer after no motion is detected, or by using occupancy sensors. The timer resets if motion is detected again.
- **Illuminance-Based Lighting**: Optionally use an illuminance sensor to only turn on the lights when the natural light level is below a defined threshold.
- **Manual Interference Handling**: Automatically pauses auto-control if manual actions are detected, WHEN
  -  ... lights are already on
  -  ... a scene is activated while auto-control is running (e.g. Philips Hue Scene turned on with your Smartphone)
- **Turn-Off Blocking Entities**: Configure entities that, when active, prevent the lights from being turned off (e.g., if a specific device is running or a condition is met).
- **Flexible Configuration for Advanced Users**: Advanced users can define custom scripts or scenes for more tailored lighting behaviors, while simple setups can rely on automatic light discovery and control.

## Installation

To install Room Light Control, simply copy all files from the `room_light_control` directory to your Home Assistant's `/custom_components/room_light_control` directory, using the Raw button to ensure proper formatting. Then, restart Home Assistant.

## Configuration

Configuring Room Light Control is straightforward thanks to its auto-discovery feature that detects lights based on a room or area.

To enable this integration, add the following lines to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
room_light_control:
```

### Minimum sensor/entity requirements:

- An area, which represents your room (e.g. office)
- One motion sensor
- Lights assigned to the area

*Important:* This integration is built all around rooms, so first you need to configure an area for each of your rooms and assign the lights and sensors to the corresponding area.

### Configuration variables
| Property name | Description | Default value |
| --- | --- | --- |
| `room` | The name of the room, corresponding to the area name. |  |
| `motion_sensor` | A list of motion sensors used to trigger the lights. When the state changes from off to on, the lights are turned on. |  |
| `illuminance_sensor` | A sensor used to measure the illuminance in the room. (Optional) |  |
| `illuminance_sensor_threshold` | The threshold illuminance value for the lights to turn on. (Optional) | `5.0` |
| `activate_light_script_or_scene` | The script or scene used to turn on the lights. This is optional, and if not provided, the lights in the room will be turned on automatically. |  |
| `turn_off_light` | Turn off the lights by script instead of the default method which turns off every single light automatically (Optional) |  |
| `turn_off_delay` | The time delay (in seconds) before turning off the lights after no motion is detected. Acts also as a timeout for the turn_off_sensor, if it is configured. (Optional) | `180` |
| `turn_off_sensor` | A sensor used to detect when a person has left the room. When the state changes from on to off, the lights will be turned off. (Optional) |  |
| `turn_off_blocking_entity` | An entity that, when active, prevents the lights from turning off. (Optional) |  |

**Example Configurations:**

a) **Minimum Configuration** - The lights will turn on when motion is detected and will turn off after 3 minutes (default) of no motion.
```yaml
- office_light_control:
    room: office
    motion_sensor: binary_sensor.office_motion_sensor
```

b) **Using a Scene or Script to Turn On Lights** - You can either use a scene or a script to turn on the lights when motion is detected.
```yaml
- floor_light_control:
    room: floor
    motion_sensor: binary_sensor.floor_motion_sensor
    activate_light_script_or_scene: scene.floor_bright
    turn_off_delay: 30    
```

c) **Multiple Motion Sensors and Illuminance Sensor** - Use multiple motion sensors to trigger the light. An illuminance sensor can prevent the lights from turning on when there is enough natural light in the room.
```yaml
- bedroom_light_control:
    room: bedroom
    motion_sensor: 
      - binary_sensor.bedroom_left_motion_sensor
      - binary_sensor.bedroom_right_motion_sensor
    illuminance_sensor: sensor.bedroom_light_level
    illuminance_sensor_threshold: 5
    activate_light_script_or_scene: script.bedroom_activate_light
    turn_off_delay: 90
```

d) **Multiple Rooms Support** - This configuration enables automatic light control in a combined living area that includes a kitchen.
```yaml
- living_light_control:
    room: 
      - livingroom
      - kitchen
    motion_sensor: 
      - binary_sensor.living_room_motion_sensor
      - binary_sensor.kitchen_motion_sensor
    illuminance_sensor: sensor.livingroom_light_level
    illuminance_sensor_threshold: 5.0            
    activate_light_script_or_scene: scene.living_area_default
    turn_off_delay: 120           
```

e) **Using a Human Presence Sensor (Aqara FP1)** - The lights will turn on when motion is detected and will turn off when a human presence sensor like the Aqara FP1 detects that the person has left the room. This is an alternative to using a timer to turn off the lights.
```yaml
- bath_light_control:
    room: bath
    motion_sensor: 
      - binary_sensor.bath_ground_motion_sensor # PIR motion sensor
      - binary_sensor.bath_occupancy # mmwave motion sensor
    turn_off_sensor:
      - binary_sensor.bath_occupancy # mmwave motion sensor
    activate_light_script_or_scene: script.bath_activate_light 
```

## Debugging

If you encounter issues with Room Light Control, here are some steps and tools to help you troubleshoot and resolve them:

### Current state

You find all relevant attributes under Developer Tools->States. Here you can also see which lights have been dynamically scanned.
![Room Light Control States](states.png)

The state of RLC transitions as follows:
![State transitions](room_light_control_state_diagram.drawio.png)

### Enable Detailed Logging
To get detailed logs from your Room Light Control integration, you can increase the logging level in Home Assistant. Add the following to your `configuration.yaml` file under the `logger` component:

```yaml
logger:
  default: warning
  logs:
    custom_components.room_light_control: debug
```

## Release History

<details>
  <summary>Version 1.0.5-beta</summary>

*Version 1.0.5-beta*
*Release Date: 24.11.2024*

**New Features**
- Renamed `turn_on_light` to `activate_light_script_or_scene` to better reflect its intended purpose of only working with scenes or scripts.
- Made `activate_light_script_or_scene` an optional configuration variable. When it is not provided, the integration will automatically turn on lights in the room (`roomLightEntities`) instead of requiring a scene or script.

**Bug Fixes**
- Improved logging to clearly indicate whether `roomLightEntities` are being used by default or if a scene/script is being activated.

**Breaking Changes**
- The `turn_on_light` variable has been renamed to `activate_light_script_or_scene`. Configurations using the old variable will need to be updated to the new name.

</details>

<details>
  <summary>Version 1.0.4-beta</summary>

*Version 1.0.4-beta*

**Bug Fixes**
- Fixed multithreading related issues wich could lead RLC to crash

</details>

<details>
  <summary>Version 1.0.3-beta</summary>

*Version 1.0.3-beta*

**New Features**
- add compatibility for color mode xy

**Bug Fixes**
- fixed issue with too long ULID

</details>

<details>
  <summary>Version 1.0.2-beta</summary>

*Version 1.0.2-beta*

**New Features**
- add wiki chapter about debugging

**Bug Fixes**
- fixed compatibility issues with Home-Assistant 2023.12

</details>

## Contributing

Please read [CONTRIBUTING.md](.github/CONTRIBUTING.md) and the process for submitting issues.

## License

Room Light Control is licensed under the [GNU GENERAL PUBLIC LICENSE](LICENSE).

## Credits

Special credits go to Daniel Mason, the creator of [entity-controller](https://github.com/danobot/entity-controller) from which I got inspired and used his code base as a starting point for this integration.
