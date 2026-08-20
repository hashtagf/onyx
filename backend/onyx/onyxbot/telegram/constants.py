"""Constants for the Telegram bot."""

# Seconds to wait for the Onyx chat API to answer
API_REQUEST_TIMEOUT = 180

# Telegram getUpdates long-poll timeout (seconds). Telegram caps at 50.
LONG_POLL_TIMEOUT = 50

# Telegram message hard limit
MAX_MESSAGE_LENGTH = 4096

# How long to sleep between token probes while dormant
DORMANT_SLEEP_S = 5

# Log a dormant reminder every N probes (5s * 180 = 15 min)
DORMANT_LOG_EVERY = 180

# Max source links appended to an answer
MAX_SOURCES = 5
