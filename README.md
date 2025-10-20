# 🛡️ PowerDNS dnsdist — Home Assistant Integration

![HACS Badge](https://img.shields.io/badge/HACS-Custom-blue.svg)
![Home Assistant](https://img.shields.io/badge/Requires-2025.1%2B-blue)
![Version](https://img.shields.io/badge/Version-1.0.2-green)
![License](https://img.shields.io/github/license/renaudallard/homeassistant_dnsdist)

A fully featured **Home Assistant custom integration** for [PowerDNS dnsdist](https://dnsdist.org) — the intelligent DNS load balancer.

Monitor one or more dnsdist servers, group them for aggregated metrics, and control them directly from Home Assistant via HTTPS, all configured entirely through the UI.

---

## ✨ Features

| Category | Description |
|-----------|-------------|
| 🧩 Integration Type | Hub-style (`integration_type: "hub"`) |
| 🔑 Configuration Flow | 100 % UI-based setup (no YAML) |
| ⚙️ Options Flow | Edit hosts, groups, and polling intervals from the UI |
| 👥 Group Aggregation | Combine metrics from multiple hosts |
| 📊 Sensors | Queries, responses, drops, cache, CPU, uptime, security status |
| 🔒 HTTPS + SSL | Full TLS + optional certificate verification |
| 🧰 Diagnostics | “Download diagnostics” directly in the HA UI |
| 🧾 HACS Integration | Fully HACS-compliant structure |
| 🚀 CI/CD | Automated validation and release via GitHub Actions |
| 🌍 Localization | English translations included |
| 🧑‍💻 Compatibility | Home Assistant 2025.1 +, Python 3.13 + |

---

## 📦 Installation

### 🔹 HACS (Recommended)
1. Open **HACS → Integrations → Custom Repositories**
2. Add repository:  
   ```
   https://github.com/renaudallard/homeassistant_dnsdist
   ```
   → **Type:** Integration  
3. Search for **PowerDNS dnsdist** and click **Install**
4. Restart Home Assistant

### 🔹 Manual
1. Copy the folder:
   ```
   custom_components/dnsdist/
   ```
   into your Home Assistant configuration directory:
   ```
   config/custom_components/dnsdist/
   ```
2. Restart Home Assistant

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services**
2. Click **“+ Add Integration”**
3. Search for **PowerDNS dnsdist**

### Options

| Field | Description | Example |
|--------|--------------|----------|
| **Name** | Friendly name for this dnsdist instance | `dnsdist1` |
| **Host address** | IP or hostname of the dnsdist API | `172.20.0.248` |
| **Port** | API port | `8083` |
| **API Key** | Optional X-API-Key for authentication | `supersecretapikey` |
| **Use HTTPS** | Connect over TLS | `true` |
| **Verify SSL** | Validate certificates | `false` |
| **Update interval (s)** | Polling frequency | `30` |

Groups can be created once you have at least one host configured.

---

## 📊 Sensors

Each dnsdist host or group provides:

| Sensor | Description |
|---------|-------------|
| `queries` | Total DNS queries handled |
| `responses` | Responses sent |
| `drops` | Dropped queries |
| `rule_drop` | Rule-based drops |
| `downstream_errors` | Downstream send errors |
| `cache_hits` / `cache_misses` | Cache efficiency |
| `cacheHit` | Cache hit rate (%) |
| `cpu` | CPU usage (%) |
| `uptime` | Uptime (seconds) |
| `security_status` | OK / Warning / Critical |

Sensors include readable uptime and security labels as attributes.

---

## 🧰 Built-In Services

All services are available under **Developer Tools → Actions**  
(HA 2025+ replaced “Services” with this tab).

| Service | Description |
|----------|-------------|
| `dnsdist.clear_cache` | Clear dnsdist cache |
| `dnsdist.enable_server` | Enable a backend server |
| `dnsdist.disable_server` | Disable a backend server |
| `dnsdist.reload_config` | Reload dnsdist configuration |
| `dnsdist.get_backends` | Retrieve list and state of backends |
| `dnsdist.runtime_command` | Execute any console command via REST API |

### Examples

**Clear cache**
```yaml
service: dnsdist.clear_cache
data:
  host: dnsdist1
```

**Reload configuration**
```yaml
service: dnsdist.reload_config
data:
  host: dnsdist1
```

**Run console command**
```yaml
service: dnsdist.runtime_command
data:
  host: dnsdist1
  command: showServers()
```

---

## 👥 Group Aggregation

Group entries automatically:
* Sum counters (queries, responses, drops)
* Average percentages (CPU, uptime)
* Report the highest security level among members  

Each group appears as its own device in Home Assistant.

---

## 🧾 Diagnostics

From the dnsdist device page:
* Open menu → **Download Diagnostics**  
Exports a JSON snapshot of configuration (with API keys redacted) and current stats.

---

## 🧱 Folder Layout

```
custom_components/dnsdist/
│
├── __init__.py
├── config_flow.py
├── coordinator.py
├── group_coordinator.py
├── sensor.py
├── diagnostics.py
├── const.py
├── services.yaml
├── strings.json
├── translations/en.json
└── manifest.json
```

---

## 🧩 Manifest (excerpt)

```json
{
  "domain": "dnsdist",
  "name": "PowerDNS dnsdist",
  "version": "1.0.1",
  "documentation": "https://github.com/renaudallard/homeassistant_dnsdist",
  "issue_tracker": "https://github.com/renaudallard/homeassistant_dnsdist/issues",
  "after_dependencies": ["http"],
  "config_flow": true,
  "iot_class": "local_polling",
  "integration_type": "hub",
  "services": ["services.yaml"],
  "quality_scale": "beta",
  "homeassistant": "2025.1.0",
  "requirements": [],
  "codeowners": ["@renaudallard"],
  "supported_brands": ["PowerDNS"],
  "diagnostics": true
}
```

---

## 🧠 Example Automation

Notify if any backend is down:

```yaml
alias: Notify if dnsdist backend is down
trigger:
  - platform: time_pattern
    minutes: "/10"
action:
  - service: dnsdist.get_backends
    data:
      host: dnsdist1
  - delay: "00:00:02"
  - condition: template
    value_template: >
      {% set s = states('sensor.dnsdist1_security_status') %}
      {{ s not in ['ok', 'secure'] }}
  - service: notify.persistent_notification
    data:
      title: "dnsdist Alert"
      message: "One or more dnsdist backends are down or degraded."
```

---

## 🧾 License

Licensed under the **MIT License**  
© 2025 [Renaud Allard](https://github.com/renaudallard)

Repository:  
[https://github.com/renaudallard/homeassistant_dnsdist](https://github.com/renaudallard/homeassistant_dnsdist)
