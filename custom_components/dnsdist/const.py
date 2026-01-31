"""Constants for the PowerDNS dnsdist integration."""

DOMAIN = "dnsdist"

# Default update interval in seconds
DEFAULT_UPDATE_INTERVAL = 30

# Platforms used by this integration
PLATFORMS = ["sensor", "button"]  # <-- added button

# Dispatcher signal names (safe to import everywhere)
SIGNAL_DNSDIST_RELOAD = f"{DOMAIN}_reload_groups"

# Keys for configuration / options
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_USE_HTTPS = "use_https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_NAME = "name"
CONF_MEMBERS = "members"
CONF_IS_GROUP = "is_group"
CONF_INCLUDE_FILTER_SENSORS = "include_filter_sensors"
CONF_REMOVE_DISABLED_FILTER_SENSORS = "remove_filter_sensors_on_disable"

# Attribute names for sensor data
ATTR_QUERIES = "queries"
ATTR_RESPONSES = "responses"
ATTR_DROPS = "drops"
ATTR_RULE_DROP = "rule_drop"
ATTR_DOWNSTREAM_ERRORS = "downstream_errors"
ATTR_CACHE_HITS = "cache_hits"
ATTR_CACHE_MISSES = "cache_misses"
ATTR_CACHE_HITRATE = "cacheHit"
ATTR_CPU = "cpu"
ATTR_UPTIME = "uptime"
ATTR_SECURITY_STATUS = "security_status"
ATTR_REQ_PER_HOUR = "req_per_hour"
ATTR_REQ_PER_DAY = "req_per_day"

# Attribute names for complex data structures
ATTR_FILTERING_RULES = "filtering_rules"
ATTR_DYNAMIC_RULES = "dynamic_rules"

# Storage helpers
STORAGE_VERSION = 1
STORAGE_KEY_HISTORY = "history"

# Security status mappings (dnsdist API code -> string)
SECURITY_STATUS_MAP = {
    0: "unknown",
    1: "ok",
    2: "warning",
    3: "critical",
}

# Security status reverse mapping (string -> code)
SECURITY_STATUS_CODE = {
    "unknown": 0,
    "ok": 1,
    "secure": 1,  # alias for ok
    "warning": 2,
    "critical": 3,
}

# Security status human-readable labels
SECURITY_STATUS_LABEL = {
    "unknown": "Unknown",
    "ok": "OK",
    "secure": "OK",
    "warning": "Upgrade Recommended",
    "critical": "Upgrade Required",
}
