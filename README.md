202510231415
# PowerDNS **dnsdist** — Home Assistant Integration (v1.1.1)

A secure, high-performance custom integration for **PowerDNS dnsdist 2.x** and **Home Assistant 2025.10+**.  
Monitor multiple dnsdist hosts and aggregated groups (sum/avg/max), view diagnostics, and invoke control services.

- **Compatibility:** Home Assistant **2025.10+**
- **Integration type:** Hub (devices per host & per group)
- **Domain:** `dnsdist`
- **License:** MIT
- **Current version:** **1.1.1**

---

## Features

- **UI-only setup** (no YAML)
- **Multiple hosts**, each as its own device
- **Groups** that aggregate hosts:
  - **Sum:** queries, responses, drops, rule drops, downstream errors, cache hits/misses
  - **Avg:** CPU %
  - **Max:** uptime
- **Sensors** with long-term statistics:
  - Monotonic counters → `TOTAL_INCREASING` (no unit)
  - `cacheHit` (%) and `cpu` (%) → `MEASUREMENT`
  - `uptime` (seconds, `device_class=duration`) → `MEASUREMENT`
  - `security_status` (string with attributes)
  - **New:** `req_per_hour` (Requests per Hour, last hour) and `req_per_day` (Requests per Day, last 24h) — **rounded to whole units**
- **HTTPS + SSL verification** options
- **Encrypted API key storage** (leverages HA’s secret store when available)
- **Diagnostics** (redacts secrets)
- **Services**: `clear_cache`, `enable_server`, `disable_server`, `reload_config`, `get_backends`, `runtime_command`
- **Localization**: `strings.json` + `translations/en.json`

---

## Installation

> Requires Home Assistant **2025.10** or newer.

1. Copy the `custom_components/dnsdist/` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → + Add Integration** and select **PowerDNS dnsdist**.

**HACS (optional):** If you use HACS, add your repository (if private) or install directly if public. Ensure the folder path is exactly `custom_components/dnsdist`.

---

## Configuration

### Add a Host
- **Name:** Display name
- **Host / Port:** API endpoint (default port `8083`)
- **API Key:** Optional (stored securely when supported)
- **Use HTTPS / Verify SSL:** TLS options
- **Update interval (s):** Polling frequency (default `30`)

### Add a Group
- **Group name**
- **Members:** Select from existing host names
- **Update interval (s):** Default `30`

> Groups compute **sum** (counters), **avg** (CPU %), **max** (uptime), and a priority **security_status** (critical > warning > ok > unknown).

---

## Entities

Each **host** and **group** creates a **Device** with these sensors:

- `queries`, `responses`, `drops`, `rule_drop`, `downstream_errors`, `cache_hits`, `cache_misses`  
  - `state_class=TOTAL_INCREASING`, **no unit**
- `cacheHit` — `%` (`MEASUREMENT`)
- `cpu` — `%` (`MEASUREMENT`)
- `uptime` — seconds (`device_class=duration`, `MEASUREMENT`)  
  - Attribute `human_readable`: `Xd HHh MMm`
- `req_per_hour` — requests/hour (last hour window), **integer**
- `req_per_day` — requests/day (from last 24h window), **integer**
- `security_status` — string  
  - Attributes: `status_code` (0–3), `status_label`

> Sensor names are **metric-only**; HA automatically prefixes the device name (e.g., “elrond Cache Hit Rate”).

---

## Options

From the integration options:
- Change **Name**
- Adjust **Update interval**
- For **groups**, add/remove **Members**

---

## Services

All services live in the `dnsdist` domain. The optional `host` targets a specific **host display name**; if omitted, the action applies to **all hosts** (not groups).

### Clear cache
service: dnsdist.clear_cache
data:
  host: "amandil"  # optional

### Enable a backend
service: dnsdist.enable_server
data:
  host: "amandil"
  backend: "192.168.1.10:53"

### Disable a backend
service: dnsdist.disable_server
data:
  host: "amandil"
  backend: "192.168.1.10:53"

### Reload configuration
service: dnsdist.reload_config
data:
  host: "amandil"  # optional

### Get backends (results logged)
service: dnsdist.get_backends
data:
  host: "amandil"  # optional

### Runtime console command
service: dnsdist.runtime_command
data:
  host: "amandil"  # optional
  command: "showServers()"

---

## Diagnostics

Go to **Settings → Devices & Services → PowerDNS dnsdist → ... → Download diagnostics**.  
Sensitive fields (e.g., API key) are redacted.

---

## Troubleshooting

- **Recorder unit warnings**  
  Ensure counters are unitless with `TOTAL_INCREASING`. This integration sets that correctly.
- **Device card opens wrong page**  
  Devices use unique `DeviceInfo.identifiers` per host/group to avoid collisions.
- **Group shows “No active members yet” at startup**  
  Normal until each member host completes its first refresh.

---

## File Map

custom_components/dnsdist/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  options_flow.py
  coordinator.py
  group_coordinator.py
  sensor.py
  services.py
  diagnostics.py
  strings.json
  translations/
    en.json
  services.yaml

---

## Changelog

### 1.1.1
- Added **Requests per Hour** (`req_per_hour`) and **Requests per Day** (`req_per_day`) sensors with integer rounding.
- Fixed duplicate name prefix in sensor display names by using metric-only labels (HA prefixes device name).

### 1.1.0
- HA **2025.10** compatibility affirmed.
- Stable entity modeling for LTS/recorder (counters = `TOTAL_INCREASING`; percentages/uptime = `MEASUREMENT`).
- Robust device identifiers (per host/group) and clean diagnostics.
- Service schemas aligned with `services.yaml`.

---

## License

**MIT** — see `LICENSE`.
