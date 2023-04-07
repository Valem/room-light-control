---

# Contributing to Room Light Control

Thank you for considering contributing to Room Light Control. This guide explains how to contribute to the project.

## Issues

If you have found a bug or would like to request a feature, please create a new issue on the GitHub repository with a descriptive title and a clear description of the issue.

When reporting a bug, please include the following information:

- The version of Room Light Control you are using.
- A detailed description of the issue and steps to reproduce it.
- Any error messages or logs that you have.

Please follow the issue template instructions.

When requesting a new feature, please provide a clear description of what you would like to see and why it would be useful.

## Pull Requests

Please don't make any pull requests yet, because it's my first open source project and I first need to learn more about how to get organized for  your contribution requests. But stay tuned!

## Vision, Goals and Ideas/Improvements

### Vision
Room Light Control aims to simplify the management of lighting in rooms by providing an automated and customizable solution that integrates with Home Assistant. The idea is to create a natural experience when you enter or exit a room, which requires the most available sensors possible to be able to detect presence and light condition in a room.

### Goals
- Provide automated control of lights in a specific room of the house using motion and occupancy sensors.
- Support for human presence sensors like Aqara FP1 to prevent lights from turning off while someone is in the room.
- Allow customization of light behavior with options to configure the illuminance sensor, turn-off delay, and blocking entities.
- Enable easy configuration with auto-discovery of lights based on a room akka area.

### Non-Goals
- Triggering lights based just on sun based state or scheduled times
- Controlling other types of devices other than lights

### Ideas/Improvements
- Disable/Enable room light control instances
- Custom Lovelace Card for room_light_control 
      ideas:
      - Disable/Enable switch
      - Remaining timer seconds
      - rlc main state
      - Room light on/off
      - Last trigger time
- Define a baseline scene (ambient light). Turning on lights starts target Scene. Turning off the lights goes back to baseline scene