202510271045
# PowerDNS **dnsdist** — Home Assistant Integration (v1.1.5)

A secure, high-performance custom integration for **PowerDNS dnsdist 2.x** and **Home Assistant 2025.10+**.  
Monitor multiple dnsdist hosts and aggregated groups (sum/avg/max), view diagnostics, and use safe REST actions.

- **Compatibility:** Home Assistant **2025.10+**
- **Integration type:** Hub (devices per host & per group)
- **Domain:** `dnsdist`
- **License:** MIT
- **Current version:** **1.1.5**

---

## Features

- **UI-only setup** (no YAML)
- **Multiple hosts**, each as its own device
- **Groups** that aggregate hosts:
  - **Sum:** queries, responses, drops, rule drops, downstream errors, cache hits/misses
  - **Avg:** CPU %
  - **Max:** uptime
- **Group filtering rule sensors** aggregate per-rule match counts across members and surface idle/active icons automatically
- **Sensors** with long-term statistics:
  - Monotonic counters → `TOTAL_INCREASING` (no unit)
  - `cacheHit` (%) and `cpu` (%) → `MEASUREMENT`
  - `uptime` (seconds, `device_class=duration`) → `MEASUREMENT`
  - `security_status` (string with attributes)
  - `req_per_hour` (Requests per Hour, last hour) — **integer**
  - `req_per_day` (Requests per Day, last 24h) — **integer**
- **HTTPS + SSL verification** options
- **Encrypted API key storage** (leverages HA’s secret store when available)
- **Diagnostics** (redacts secrets)
- **REST-only services**: `clear_cache`, `enable_server`, `disable_server`, `get_backends`
- **Device button**: **Clear Cache** (with confirmation). For groups, applies to all member hosts.

> **Rate sensors need time:**  
> - `req_per_hour` needs **at least 1 hour** of data to stabilize.  
> - `req_per_day` needs **at least 24 hours** of data to stabilize.  
> Before these windows fill, values may appear lower than expected.

---

## Installation

> Requires Home Assistant **2025.10** or newer.

1. Copy `custom_components/dnsdist/` into your HA `config/custom_components/` directory.
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
- **Groups only:** `Filter <rule name>` sensors report aggregated match counts per filtering rule with a `sources` attribute breaking down member contributions; icons switch between `mdi:filter-check-outline` at zero matches and `mdi:filter` when active

> Sensor names are **metric-only**; HA prefixes with the device name (e.g., “elrond Cache Hit Rate”).

---

## Options

From the integration options:
- Change **Name**
- Adjust **Update interval**
- For **groups**, add/remove **Members**

---

## Services (REST-only)

All services live in the `dnsdist` domain. The optional `host` targets a specific **host display name**; if omitted, the action applies to **all hosts** (not groups).

> These services use the official **REST API** only. Console-dependent actions have been removed to ensure consistent behavior with YAML webserver configs.

### Clear cache
service: dnsdist.clear_cache
data:
  host: "amandil"  # optional; if omitted, all hosts
  pool: ""         # optional; default pool if omitted

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

### Get backends (results logged)
service: dnsdist.get_backends
data:
  host: "amandil"  # optional; if omitted, all hosts

---

## Device Buttons

Each **host** and **group** device exposes:

- **Clear Cache** — confirmation required; for groups, runs on all member hosts.

---

## Diagnostics

Go to **Settings → Devices & Services → PowerDNS dnsdist → ... → Download diagnostics**.  
Sensitive fields (e.g., API key) are redacted.

---

## Troubleshooting

- **Counters & Recorder**  
  Monotonic counters are unitless `TOTAL_INCREASING` — safe for long-term statistics.
- **Device page linking**  
  Distinct `DeviceInfo.identifiers` avoid collisions between hosts and groups.
- **Group shows “No active members yet” at startup**  
  Normal until each member host completes its first refresh.
- **REST requirements on dnsdist**  
  Ensure the dnsdist **webserver** is enabled with an **API key** and proper **ACL** to your HA network.

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
  button.py
  services.py
  diagnostics.py
  strings.json
  translations/
    en.json
  services.yaml

---

## Changelog

### 1.1.5
- Refined the hourly and daily request sensors to interpolate counters precisely at the window horizon, preventing inflated totals when samples span the boundary.

### 1.1.4
- Corrected hourly and daily request totals to report the actual rolling-window volume instead of extrapolated estimates.

### 1.1.3
- Reuse Home Assistant's shared HTTP session for config validation, data updates, and services to meet 2025.10 requirements.

### 1.1.2
- Switch to **REST-only** services: keep `clear_cache`, `enable_server`, `disable_server`, `get_backends`; remove console-dependent services.
- **Buttons:** only **Clear Cache** remains (confirmation enabled); group button applies to all members.
- README updated to reflect REST-only behavior and the single button.

### 1.1.1
- Added **Requests per Hour** (`req_per_hour`) and **Requests per Day** (`req_per_day`) sensors with **integer rounding**.
- Fixed duplicate device name in sensor display names by using **metric-only** labels.

### 1.1.0
- HA **2025.10** compatibility affirmed.
- Stable entity modeling for Recorder (counters `TOTAL_INCREASING`; percentages/uptime `MEASUREMENT`).
- Robust device identifiers and clean diagnostics.
- HACS/manifest alignment.

---

## License

**MIT** — see `LICENSE`.
