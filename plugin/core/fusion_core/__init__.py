"""fusion-core: lyfusion v5 engine. Uses only the Python standard library."""

VERSION = "5.0.0-rc.7"
SCHEMA = 2  # Shared by config.json, local.json, and fusion.db. aq.2 and earlier had no version, so treat them as version 1. Increment only for changes old versions would misread; new fields with defaults do not require an increment.
