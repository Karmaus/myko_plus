# Myko+ Home Assistant Integration

A custom Home Assistant integration for controlling Myko+ smart devices through the Myko cloud API.

> **Forked from [Karmaus/myko_plus](https://github.com/Karmaus/myko_plus).**  
> AC/climate support contributed by [mullak99](https://github.com/mullak99).  
> This fork adds confirmed API field mappings, proper device registry info, and fixes based on live API data captured from real Sengled devices.

## Supported devices

| Device type | HA platform | Notes |
|---|---|---|
| RGB smart bulbs (`LIGHT_RGB`) | `light` | Brightness, colour temperature, RGB, effects |
| White smart bulbs (`LIGHT_WHITE`) | `light` | Brightness and colour temperature only |
| Portable AC / Air conditioner | `climate` | HVAC mode, target temp, fan, swing, presets |
| AC sleep mode | `switch` | Dedicated toggle for sleep mode on AC devices |

## Features

- Cloud-based communication with Myko+ services
- Devices appear in the HA device registry with manufacturer, model, firmware version, and serial number
- `LIGHT_WHITE` bulbs are correctly limited to colour temperature mode (no RGB controls)
- Colour temperature sent as direct Kelvin values (confirmed from live API data)
- Optimistic state updates — UI responds immediately without waiting for the next poll
- Automatic token refresh with full re-login fallback
- Config Flow support (UI-based setup)

## Installation

### HACS (recommended)
1. Add this repository as a custom repository in HACS
2. Install the integration
3. Restart Home Assistant

### Manual
Copy the `custom_components/myko_plus` folder into your Home Assistant `config/custom_components` directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **Myko+**
4. Enter your Myko account credentials

## Changelog (this fork)

### 2026-06-08
- Confirmed real API field names from live device data (`_id`, `name`, `client`, `reference`, `serial_number`, `state.fwVer`)
- Added proper `DeviceInfo` to all entity types (lights, climate, switches)
- Fixed colour temperature: device returns and accepts direct Kelvin values — removed incorrect inversion mapping
- `LIGHT_WHITE` devices now only expose `ColorMode.COLOR_TEMP` (no RGB)
- Simplified light device detection using `profile_name` prefix (`LIGHT_`)
- Removed unreliable `connected` field from availability checks (field is always `False` in the API even when devices are reachable)
- AC/climate support merged from [mullak99/ac-climate-support](https://github.com/mullak99/myko_plus/tree/ac-climate-support)

## Status

⚠️ Still under active development. Currently tested with Sengled smart bulbs on the Myko+ platform. AC support is included but less tested.

Some API endpoints are based on reverse engineering and may change. Expect occasional breaking changes.

## Notes

- This integration uses the Myko+ cloud API — local control is not supported.
- Device state is read from the inline `state` field returned with each device, with a per-device endpoint fallback when inline state is absent.
- API behaviour may change without notice from the provider.
- Feedback and contributions are welcome!

## Disclaimer

This project is not affiliated with or endorsed by Myko or Kingfisher.
