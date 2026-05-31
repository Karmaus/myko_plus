# Myko+ Home Assistant Integration

A custom Home Assistant integration for controlling Myko+ smart devices through the Myko cloud API.

This integration currently allows you to:
- Control Myko+ lights (bulbs)
- Control supported Myko+ portable AC units
- Adjust brightness, color temperature, RGB color, and effects
- Set HVAC mode, target temperature, fan speed, swing, and sleep mode for supported ACs
- Keep device states in sync with the cloud

## Features

- Cloud-based communication with Myko+ services
- Support for light entities (brightness, color temperature, RGB, effects)
- Support for climate entities (and sleep mode switch entities) for supported portable AC devices
- Token handling with automatic refresh
- Config Flow support (UI-based setup)

## Installation

### HACS (recommended)
1. Add this repository as a custom repository in HACS
2. Install the integration
3. Restart Home Assistant

### Manual
Copy the `custom_components/myko_plus` folder into your Home Assistant `config` directory.

## Configuration

After installation:
1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **Myko+**
4. Enter your Myko account credentials

## Status

⚠️ This is my first Home Assistant integration and it is still under active development.

Currently, only light (bulb) and portable AC devices are supported, as no other Myko+ device types were available for testing.

Some parts of the API are based on reverse engineering and may change over time. Expect bugs and potential breaking changes.

## Notes

- This integration uses the Myko+ cloud API and does not support local control.
- Device state is currently read from the `/devices` payload, with per-device fallback only when inline state is missing.
- API behavior may change without notice from the provider.
- Feedback and contributions are welcome!

## Disclaimer

This project is not affiliated with or endorsed by Myko or Kingfisher.
