# PowerDNS **dnsdist** — Home Assistant Integration

[![Release](https://img.shields.io/badge/version-1.1.10-blue.svg)](#changelog)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.10%2B-41BDF5)](https://www.home-assistant.io/)
[![dnsdist](https://img.shields.io/badge/dnsdist-2.x-ff6f00)](https://dnsdist.org)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> A secure, high-performance bridge between **PowerDNS dnsdist 2.x** and **Home Assistant 2025.10+**. Monitor every proxy, surface aggregated insights, and control dnsdist safely through REST-only actions.

---

## 📘 Table of Contents <a id="table-of-contents"></a>

1. [At a Glance](#at-a-glance)
2. [Feature Highlights](#feature-highlights)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Entities](#entities)
6. [Options](#options)
7. [Services](#services)
8. [Device Buttons](#device-buttons)
9. [Diagnostics](#diagnostics)
10. [Troubleshooting](#troubleshooting)
11. [File Map](#file-map)
12. [Changelog](#changelog)
13. [License](#license)

---

## ⚡ At a Glance <a id="at-a-glance"></a>

| | |
| --- | --- |
| **Integration type** | Hub (per-host and per-group devices) |
| **Domain** | `dnsdist` |
| **Current version** | **1.1.10** |
| **Home Assistant** | **2025.10+** |
| **dnsdist** | **2.x** |
| **License** | [MIT](LICENSE) |

---

## ✨ Feature Highlights <a id="feature-highlights"></a>

- **UI-only setup** — zero YAML required.
- **Multiple hosts** — each dnsdist endpoint becomes its own device.
- **Aggregated groups** with smart rollups:
  - **Sum:** queries, responses, drops, rule drops, downstream errors, cache hits/misses
  - **Average:** CPU %
  - **Max:** uptime
- **Filtering rule sensors** for per-rule match counts (opt-in for hosts, on by default for groups) complete with idle/active icons.
- **Long-term statistics ready** sensors:
  - Monotonic counters as `TOTAL_INCREASING` (`count` unit)
  - `cacheHit` and `cpu` as `%` (`MEASUREMENT`)
  - `uptime` as seconds (`device_class=duration`, `MEASUREMENT`)
  - `security_status` with rich attributes
  - `req_per_hour` / `req_per_day` as integer rolling windows
- **Secure by default** with HTTPS, SSL verification, and encrypted API key storage (uses HA’s secret store when available).
- **Diagnostics bundle** that automatically redacts sensitive data.
- **REST-only services** (`clear_cache`, `enable_server`, `disable_server`, `get_backends`) and a **Clear Cache** device button for both hosts and groups.

> **Rate sensors need runway:** `req_per_hour` stabilizes after the first hour. `req_per_day` needs 24 hours of samples. Early readings may appear lower than expected.

---

## 🛠 Installation <a id="installation"></a>

> Requires Home Assistant **2025.10** or newer.

1. Copy `custom_components/dnsdist/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Navigate to **Settings → Devices & Services → + Add Integration** and pick **PowerDNS dnsdist**.

**HACS (optional):** Add this repository as a custom source (if private) or install directly if public. Ensure the integration sits in `custom_components/dnsdist`.

---

## 🧩 Configuration <a id="configuration"></a>

### Add a Host

- **Name:** Display name for Home Assistant
- **Host / Port:** dnsdist API endpoint (default port `8083`)
- **API Key:** Optional; securely stored when supported
- **Use HTTPS / Verify SSL:** Toggle TLS and certificate validation
- **Update interval (s):** Polling frequency (default `30`)
- **Include filtering rule sensors:** Disabled by default; enable to expose per-rule sensors

### Add a Group

- **Group name** — Home Assistant device label
- **Members** — Choose from existing host names
- **Update interval (s):** Default `30`
- **Include filtering rule sensors:** Enabled by default; disable to skip aggregated rule sensors

> Group rollups: **sum** (counters), **avg** (CPU %), **max** (uptime), and priority **security_status** (critical → warning → ok → unknown).

---

## 📊 Entities <a id="entities"></a>

Each host or group creates a Home Assistant device with these sensors:

- `queries`, `responses`, `drops`, `rule_drop`, `downstream_errors`, `cache_hits`, `cache_misses`
  - `state_class=TOTAL_INCREASING`, unit `count`
- `cacheHit` — `%` (`MEASUREMENT`)
- `cpu` — `%` (`MEASUREMENT`)
- `uptime` — seconds (`device_class=duration`, `MEASUREMENT`)
  - Attribute `human_readable`: `Xd HHh MMm`
- `req_per_hour` — integer requests/hour (rolling 1-hour window)
- `req_per_day` — integer requests/day (rolling 24-hour window)
- `security_status` — string with `status_code` (0–3) and `status_label`
- **Filtering rule sensors** (`Filter <rule name>`) — per-rule matches for hosts, aggregated counts plus a `sources` attribute for groups. Icons flip between `mdi:filter-check-outline` (idle) and `mdi:filter` (active).

> Sensor entity names are metric-only. Home Assistant automatically prefixes them with the device name (e.g., “elrond Cache Hit Rate”).

---

## ⚙️ Options <a id="options"></a>

From the integration options panel you can:

- Rename a host or group
- Tune the **Update interval**
- For groups, add or remove **Members**
- Toggle **Filtering rule sensors** at any time (hosts default off, groups default on)
- Decide whether disabling filtering rule sensors should immediately delete the existing entities (enabled by default)

---

## 🔌 Services <a id="services"></a>

All services live under the `dnsdist` domain. Supplying `host` targets a specific display name; omit it to broadcast the action to every host (groups excluded).

> Console-dependent behaviors are gone. Everything here calls the official dnsdist REST API so it works regardless of your YAML webserver configuration.

### `dnsdist.clear_cache`

```yaml
service: dnsdist.clear_cache
data:
  host: "amandil"  # optional; runs on all hosts when omitted
  pool: ""         # optional; defaults to dnsdist's primary pool
```

### `dnsdist.enable_server`

```yaml
service: dnsdist.enable_server
data:
  host: "amandil"
  backend: "192.168.1.10:53"
```

### `dnsdist.disable_server`

```yaml
service: dnsdist.disable_server
data:
  host: "amandil"
  backend: "192.168.1.10:53"
```

### `dnsdist.get_backends`

```yaml
service: dnsdist.get_backends
data:
  host: "amandil"  # optional; runs on all hosts when omitted
```

---

## 🕹 Device Buttons <a id="device-buttons"></a>

Each host or group device exposes a single **Clear Cache** button. Confirmation is required, and group presses cascade to every member host.

---

## 🧪 Diagnostics <a id="diagnostics"></a>

Visit **Settings → Devices & Services → PowerDNS dnsdist → ⋮ → Download diagnostics**. The export automatically redacts secrets such as API keys.

---

## 🩺 Troubleshooting <a id="troubleshooting"></a>

- **Counters & Recorder** — Monotonic counters use `TOTAL_INCREASING` and the `count` unit, so long-term statistics stay healthy.
- **Device page linking** — Host and group devices use unique `DeviceInfo.identifiers`, preventing cross-linking.
- **Group shows “No active members yet”** — Normal until each member host completes its first refresh.
- **REST prerequisites on dnsdist** — Ensure the dnsdist webserver is enabled, has an API key, and allows your Home Assistant network in the ACL.

---

## 🗂 File Map <a id="file-map"></a>

```
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
```

---

## 📝 Changelog <a id="changelog"></a>

### 1.1.10
- Sanitize dnsdist backend identifiers used by REST services, rejecting control characters and logging invalid requests.

### 1.1.9
- Preserve hourly and daily dnsdist query history across Home Assistant restarts so rolling rate sensors stay accurate.

### 1.1.8
- Preload the dnsdist sensor and button platforms during integration startup to avoid blocking import warnings on Home Assistant 2025.10.
- Provide a compatibility fallback for the removed `COUNT` unit constant so count-based sensors keep their units on new Home Assistant releases.

### 1.1.7
- Report dnsdist monotonic counters with Home Assistant's `count` unit to keep Recorder statistics enabled.

### 1.1.6
- Added per-entry control over filtering rule sensors: hosts default off, groups default on, and both can be changed later.
- Introduced an option to automatically delete existing filtering rule sensors when the feature is turned off.

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

## 📄 License <a id="license"></a>

**MIT** — see [`LICENSE`](LICENSE).
