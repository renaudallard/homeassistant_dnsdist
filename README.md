# PowerDNS dnsdist Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![GitHub Release](https://img.shields.io/github/v/release/renaudallard/homeassistant_dnsdist)
![GitHub License](https://img.shields.io/github/license/renaudallard/homeassistant_dnsdist)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1+-blue)

---

## Overview

This custom integration allows **Home Assistant** to connect to one or more
[PowerDNS dnsdist 2.0.0](https://dnsdist.org/) servers through the REST API.

It provides:

- Real-time metrics such as queries, cache hits, CPU usage, security status, etc.
- Support for multiple dnsdist hosts
- Group aggregation across multiple servers
- SSL / HTTPS support
- Diagnostics for troubleshooting ("Download diagnostics")
- UI-based configuration — no YAML required
- Full support for Home Assistant 2025+

---

## Features

| Feature | Description |
|----------|-------------|
| 🔍 Auto-discovery | Add multiple dnsdist hosts through the UI |
| 🧠 Aggregated Groups | Combine multiple servers into a single logical group |
| 📊 Sensors | Total queries, responses, drops, cache stats, CPU usage, uptime |
| 🛡️ Security Status | Shows OK / Upgrade recommended / Upgrade required |
| 🔐 HTTPS + SSL | Connect securely using API key authentication |
| 🧰 Diagnostics | Download runtime diagnostics via the HA UI |
| ⚙️ Options Flow | Edit groups and hosts directly from the UI |

---

## Installation

### Via HACS (Recommended)

1. Open **HACS → Integrations → Custom Repositories**
2. Add this repository:
   ```
   https://github.com/renaudallard/homeassistant_dnsdist
   ```
   Category: **Integration**
3. Install the integration **PowerDNS dnsdist**
4. Restart Home Assistant

### Manual installation

1. Copy the `custom_components/dnsdist/` folder into your
   `<config>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

### Step 1 — Add integration

Go to:

**Settings → Devices & Services → Add Integration → PowerDNS dnsdist**

Then choose one of:

- **Add dnsdist Host** — connect to a single dnsdist instance
- **Add dnsdist Group** — aggregate multiple dnsdist hosts into one logical group

### Step 2 — Fill in connection details

| Field | Description |
|--------|-------------|
| Name | Friendly name for this dnsdist server |
| Host address | IP or hostname of the dnsdist API |
| Port | Port of the API (default: 8083) |
| API Key | Optional API key if authentication is enabled |
| Use HTTPS | Enable if dnsdist API runs over HTTPS |
| Verify SSL certificate | Disable if using self-signed certificates |
| Update interval (seconds) | Polling interval for statistics (default: 30) |

### Step 3 — Add groups (optional)

After adding at least one host, you can create a group:

1. Go to **Settings → Devices & Services → Add Integration → PowerDNS dnsdist**
2. Choose **Add dnsdist Group**
3. Select which hosts belong to the group (a host can be part of multiple groups)
4. Choose the update interval

You can edit groups later via the ⚙️ “Configure” button.

---

## Available Sensors

| Sensor | Description |
|---------|-------------|
| Total Queries | Number of queries processed |
| Responses | Number of responses sent |
| Dropped Queries | Total dropped queries |
| Rule Drops | Queries dropped due to rules |
| Downstream Send Errors | Errors while sending to downstream servers |
| Cache Hits | Cache hits count |
| Cache Misses | Cache misses count |
| Cache Hit Rate | Percent of queries served from cache |
| CPU Usage | Current dnsdist CPU usage (%) |
| Uptime | Time since dnsdist started |
| Security Status | One of: OK / Upgrade recommended / Upgrade required |

---

## Example UI

*(Replace with screenshots once published)*

| Example | Description |
|----------|-------------|
| ![dnsdist sensors](https://user-images.githubusercontent.com/placeholder/sensors.png) | dnsdist sensors for a single host |
| ![dnsdist group](https://user-images.githubusercontent.com/placeholder/group.png) | Aggregated group combining multiple servers |

---

## Services

| Service | Description |
|----------|-------------|
| `dnsdist.enable_server` | Enable a backend server |
| `dnsdist.disable_server` | Disable a backend server |
| `dnsdist.clear_cache` | Clear dnsdist cache |
| `dnsdist.reload_config` | Reload configuration |

*(These appear automatically under “Developer Tools → Services”)*

---

## SSL & Authentication

This integration supports both **HTTP** and **HTTPS** endpoints.
If your dnsdist API uses self-signed certificates, you can disable certificate validation
during setup (uncheck “Verify SSL certificate”).

---

## Diagnostics

In Home Assistant, open the integration page → click “⋮ → Download Diagnostics”
to retrieve a JSON diagnostic bundle containing connection details, API response data,
and any recent errors for troubleshooting.

---

## Requirements

- Home Assistant 2025.1 or later
- Python ≥ 3.13
- PowerDNS dnsdist 2.0.0+ (uses `/api/v1/servers/localhost/statistics`)

---

## Development

```bash
git clone https://github.com/renaudallard/homeassistant_dnsdist.git
cd homeassistant_dnsdist
```

To run inside a Home Assistant dev environment:

```bash
hass --script check_config
```

---

## Folder structure

```
custom_components/dnsdist/
├── __init__.py
├── config_flow.py
├── coordinator.py
├── group_coordinator.py
├── sensor.py
├── const.py
├── manifest.json
├── strings.json
└── translations/
    └── en.json
```

---

## Troubleshooting

| Symptom | Cause / Fix |
|----------|-------------|
| `not_implemented` when adding integration | Outdated config_flow → ensure latest version |
| “Unknown error occurred” adding group | No hosts available → add at least one host first |
| All group sensors show “unavailable” | Delete and re-add group (data schema changed) |
| Uptime shows as “unavailable” | dnsdist API uptime not returned — check version |
| Security Status incorrect | dnsdist not reporting proper `security-status` metric |

---

## License

MIT © [Renaud Allard](https://github.com/renaudallard)

---

## Feedback

- Report bugs or feature requests via [GitHub Issues](https://github.com/renaudallard/homeassistant_dnsdist/issues)
- Contributions welcome via Pull Requests 🎉
