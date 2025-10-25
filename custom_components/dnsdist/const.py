# 202510231445
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

# Attribute names / normalized stat keys
ATTR_QUERIES = "queries"
ATTR_RESPONSES = "responses"
ATTR_DROPS = "drops"
ATTR_RULE_DROP = "rule_drop"
ATTR_CACHE_HITS = "cache_hits"
ATTR_CACHE_MISSES = "cache_misses"
ATTR_CACHE_HITRATE = "cacheHit"
ATTR_CPU = "cpu"
ATTR_UPTIME = "uptime"
ATTR_DOWNSTREAM_ERRORS = "downstream_errors"
ATTR_SECURITY_STATUS = "security_status"
ATTR_FILTERING_RULES = "filtering_rules"

# New computed rate metrics
ATTR_REQ_PER_HOUR = "req_per_hour"  # requests/hour over last hour (normalized)
ATTR_REQ_PER_DAY = "req_per_day"    # requests/day over last 24h (normalized)
