# PowerDNS **dnsdist** — Home Assistant Integration

[![Release](https://img.shields.io/badge/version-1.3.1-blue.svg)](#changelog)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.10%2B-41BDF5)](https://www.home-assistant.io/)
[![dnsdist](https://img.shields.io/badge/dnsdist-2.x-ff6f00)](https://dnsdist.org)
[![Validate HACS](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/hacs-validation.yml/badge.svg)](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/hacs-validation.yml)
[![Ruff](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/ruff.yml/badge.svg)](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/ruff.yml)
[![Tests](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/tests.yml/badge.svg)](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/tests.yml)
[![Type Check](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/mypy.yml/badge.svg)](https://github.com/renaudallard/homeassistant_dnsdist/actions/workflows/mypy.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> A secure, high-performance bridge between **PowerDNS dnsdist 2.x** and **Home Assistant 2025.10+**. Monitor every proxy, surface aggregated insights, and control dnsdist safely through REST-only actions.

---

## 📘 Table of Contents <a id="table-of-contents"></a>

1. [At a Glance](#at-a-glance)
2. [Feature Highlights](#feature-highlights)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Entities](#entities)
6. [Lovelace Card](#lovelace-card)
7. [Options](#options)
8. [Services](#services)
9. [Device Buttons](#device-buttons)
10. [Diagnostics](#diagnostics)
11. [Troubleshooting](#troubleshooting)
12. [File Map](#file-map)
13. [Changelog](#changelog)
14. [License](#license)

---

## ⚡ At a Glance <a id="at-a-glance"></a>

| | |
| --- | --- |
| **Integration type** | Hub (per-host and per-group devices) |
| **Domain** | `dnsdist` |
| **Current version** | **1.3.1** |
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
- **Dynamic rule sensors** for temporary blocks (dynblocks) from rate limiting, DoS protection, etc.
- **Custom Lovelace card** (`dnsdist-card`) for a beautiful dashboard display with gauges, counters, and filtering rules.
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
- **Host validation:** Enforces RFC 1123 hostnames plus IPv4/IPv6 literals, catching typos before the connection test
- **API Key:** Optional; securely stored when supported
- **Use HTTPS / Verify SSL:** Toggle TLS and certificate validation
- **Update interval (s):** Polling frequency (default `30`)
- **Include filtering rule sensors:** Disabled by default; enable to expose per-rule sensors
- **Connection verification:** Setup now requires a valid dnsdist statistics JSON payload before finishing, so wrong URLs or non-json endpoints fail fast

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
- **Dynamic rule sensors** (`Dynblock <network>`) — tracks temporary blocks (dynblocks) with attributes for reason, action, time remaining, and eBPF status. Icons flip between `mdi:shield-check-outline` (idle) and `mdi:shield-alert` (active).

> Sensor entity names are metric-only. Home Assistant automatically prefixes them with the device name (e.g., "elrond Cache Hit Rate").

---

## 🎨 Lovelace Card <a id="lovelace-card"></a>

The integration includes a custom Lovelace card for displaying dnsdist metrics in a visually appealing dashboard layout.

### Features

- **Header** with title and security status badge (OK/Warning/Critical color-coded)
- **Needle gauges** for CPU usage and Cache Hit Rate with color gradients in compact horizontal layout
  - CPU label and value on the left, gauge on the right
  - Cache Hit gauge on the left, label and value on the right
  - CPU: green (low) to red (high) indicating load severity
  - Cache Hit: red (low) to green (high) indicating cache efficiency
- **Uptime display** in human-readable format
- **Traffic counters** grid: Queries, Responses, Drops, Rule Drops, Errors
- **Request rates** tiles: Per Hour and Per Day
- **Filtering rules** list sorted by match count with expandable details
- **Dynamic rules** list showing temporary blocks with reason, time remaining, and block count
- **Clear Cache** button with confirmation dialog
- **Theme support** respects Home Assistant light/dark mode
- **Compact mode** for sidebar placement

### Installation

The card is automatically registered when the integration loads. If needed, you can manually add the resource:

1. Go to **Settings → Dashboards → Resources**
2. Add `/dnsdist_static/dnsdist-card.js?v=1.3.1` as a JavaScript Module

### Usage

Add the card to your dashboard via the UI card picker (search for "dnsdist") or manually:

```yaml
type: custom:dnsdist-card
entity_prefix: dns1              # Required: matches your dnsdist device name
title: My DNS Server             # Optional: custom card title
show_filters: true               # Optional: show filtering rules section (default: true)
show_dynamic_rules: true         # Optional: show dynamic rules section (default: true)
show_actions: true               # Optional: show action buttons (default: true)
compact: false                   # Optional: compact mode for sidebars (default: false)
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `entity_prefix` | string | *required* | The device name prefix used for entity IDs (e.g., `dns1` for `sensor.dns1_total_queries`) |
| `title` | string | entity_prefix | Custom title displayed in the card header |
| `show_filters` | boolean | `true` | Show the filtering rules section |
| `show_dynamic_rules` | boolean | `true` | Show the dynamic rules (dynblocks) section |
| `show_actions` | boolean | `true` | Show action buttons (Clear Cache) |
| `compact` | boolean | `false` | Use smaller sizes for sidebar placement |

### Visual Editor

The card includes a visual configuration editor accessible through the Lovelace UI. It automatically detects available dnsdist devices and provides toggles for all options.

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
  utils.py
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
  frontend/                    # Lovelace card source
    package.json
    tsconfig.json
    rollup.config.mjs
    src/
      dnsdist-card.ts          # Main card component
      dnsdist-card-editor.ts   # Visual config editor
      styles.ts                # CSS styles
      types.ts                 # TypeScript interfaces
  www/
    dnsdist-card.js            # Built card bundle
```

---

## 📝 Changelog <a id="changelog"></a>

### 1.3.1
- Redesign gauge layout for more compact display
  - CPU label and value positioned on the left of the gauge
  - Cache Hit label and value positioned on the right of the gauge
  - Reduced horizontal spacing between gauges

### 1.3.0
- Add dynamic rules (dynblocks) support
  - New sensors track temporary blocks from rate limiting and DoS protection
  - Attributes include network, reason, action, time remaining, and eBPF status
  - Icons flip between shield-check (idle) and shield-alert (active)
- Add dynamic rules section to Lovelace card
  - Displays blocked networks with block count and expandable details
  - New `show_dynamic_rules` configuration option (default: true)
  - Visual editor toggle for dynamic rules display
- Group aggregation for dynamic rules with source tracking

### 1.2.1
- Redesign gauge visualization with needle indicator and segmented color gradient arc
  - CPU gauge: green to red gradient (high values indicate load)
  - Cache Hit gauge: red to green gradient (high values indicate efficiency)
  - Smooth needle animation on value changes

### 1.2.0
- Add custom Lovelace card (`dnsdist-card`) for dashboard display.
  - Visual gauges for CPU and Cache Hit Rate
  - Traffic counters grid with formatted numbers
  - Request rate tiles (per hour/day)
  - Dynamic filtering rules list sorted by match count
  - Expandable rule details with pattern, type, and status
  - Clear Cache button with confirmation dialog
  - Visual config editor with device auto-detection
  - Compact mode for sidebar placement
  - Full theme support (light/dark mode)
- Auto-register frontend resource on integration load.

### 1.1.18
- Fix SSL verification logic to correctly skip validation when disabled.
- Improve error handling and add specific logging for SSL and connection errors.
- Add debug logging for API requests in config flow and coordinator.

### 1.1.17
- Fix schema serialization error for custom host validator.
- Fix config flow step transition and API validation.
- Add debug logging and improve error handling in config flow.
- Add unit tests for validators and utility functions.
- Add GitHub Actions workflows for ruff linting and mypy type checking.

### 1.1.16
- Fix ruff linting errors: remove unused imports and fix module-level import ordering.
- Add missing `monotonic` import in coordinator for CPU timing calculations.
- Remove unnecessary try/except around dict.get() in sensor module.
- Remove blocking `asyncio.sleep` call in group coordinator that could cause timeouts.
- Add type hints to coordinator methods for improved code clarity.
- Standardize asyncio timeout import style across modules.

### 1.1.15
- Refactor codebase to eliminate code duplication across coordinator modules.
- Extract shared utilities into `utils.py`: slugify functions, type coercion, device info builder, and rolling window computation.
- Create `HistoryMixin` for shared history persistence logic between host and group coordinators.
- Centralize security status mappings in `const.py`.
- Fix async generator type annotation in button.py.
- Remove redundant history flag assignments in coordinator logic.
- Pre-compile regex patterns for improved performance.

### 1.1.14
- Remove deprecated HACS metadata (`country`) to match the current HACS specification.
- Run the HACS validation workflow with default checks by dropping the custom `ignore` override.

### 1.1.13
- Add a HACS validation workflow and badge so each PR/push runs the official HACS checks automatically.
- Align manifests with current HACS/Home Assistant requirements (key ordering, supported fields only).
- Declare a config-entry-only schema to satisfy hassfest validation for setup hooks.

### 1.1.12
- Validate host entries against RFC 1123 hostnames plus IPv4/IPv6 literals directly in the config flow to prevent mis-typed endpoints.
- The connection test now parses the dnsdist statistics JSON and verifies required counters before setup completes, catching wrong URLs or non-dnsdist services early.

### 1.1.11
- Further streamline rolling-window rate calculations for host and group coordinators to minimize allocations and disk writes.

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
