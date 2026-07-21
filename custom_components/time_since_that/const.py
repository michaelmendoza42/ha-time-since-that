"""Constants for Time Since That."""

from __future__ import annotations

DOMAIN = "time_since_that"
NAME = "Time Since That"
VERSION = "1.0.0"

CONF_CHORES = "chores"
CONF_TAGS = "tags"
CONF_LAST_COMPLETED = "last_completed"
CONF_CHORE_ID = "chore_id"
CONF_NAME = "name"
CONF_CATEGORY = "category"
CONF_AREA = "area"
CONF_RECOMMENDED_EVERY = "recommended_every"
CONF_ELAPSED_DISPLAY = "elapsed_display"
CONF_VALUE = "value"
CONF_UNIT = "unit"
CONF_ROUNDING = "rounding"

ATTR_CHORE_ID = "chore_id"
ATTR_TAGS = "tags"
ATTR_FRIENDLY_CHORE_NAME = "friendly_chore_name"
ATTR_LAST_DONE_AT = "last_done_at"
ATTR_LAST_DONE_BY_NAME = "last_done_by_name"
ATTR_LAST_DONE_BY_USER_ID = "last_done_by_user_id"
ATTR_COMPLETION_COUNT = "completion_count"
ATTR_ELAPSED = "elapsed"
ATTR_ELAPSED_VALUE = "elapsed_value"
ATTR_ELAPSED_UNIT = "elapsed_unit"
ATTR_RECOMMENDED_EVERY = "recommended_every"
ATTR_RECOMMENDED_EVERY_VALUE = "recommended_every_value"
ATTR_RECOMMENDED_EVERY_UNIT = "recommended_every_unit"
ATTR_OVER_RECOMMENDED = "over_recommended"
ATTR_OVER_BY = "over_by"
ATTR_OVER_BY_VALUE = "over_by_value"
ATTR_AVERAGE_INTERVAL = "average_interval"
ATTR_AVERAGE_INTERVAL_SECONDS = "average_interval_seconds"
ATTR_MEDIAN_INTERVAL = "median_interval"
ATTR_MEDIAN_INTERVAL_SECONDS = "median_interval_seconds"
ATTR_SHORTEST_INTERVAL = "shortest_interval"
ATTR_LONGEST_INTERVAL = "longest_interval"

DATA_MANAGER = "manager"

SERVICE_MARK_DONE = "mark_done"

SOURCE_SERVICE = "service"
SOURCE_BUTTON = "button"
SOURCE_INITIAL = "initial"

UNITS = ("minutes", "hours", "days")
ROUNDING_MODES = ("floor", "ceil", "nearest")
DEFAULT_DISPLAY_UNIT = "days"
DEFAULT_DISPLAY_ROUNDING = "floor"

# v1 deliberately uses a new namespace; legacy YAML/history is not migrated.
STORAGE_KEY = f"{DOMAIN}.v1_history"
STORAGE_VERSION = 1
