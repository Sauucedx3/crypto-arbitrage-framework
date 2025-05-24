import ccxt

# --- Configuration Note ---
# The 'exchanges' dictionary previously defined in this file, which instantiated
# CCXT objects (e.g., exchanges = {'binance': ccxt.binance(), ...}),
# is no longer the primary method for ArbitrageRunner to obtain its exchange instances.
#
# ArbitrageRunner now dynamically creates CCXT exchange instances based on the
# 'exchange_configs' dictionary passed to its constructor. In the web application,
# these 'exchange_configs' are loaded from the EXCHANGE_CONFIGS environment
# variable (a JSON string), which the user is guided to set up via the /configure UI.
#
# This change allows for full configuration of API keys, secrets, passwords, and
# other CCXT parameters for each exchange externally, without hardcoding them here.
#
# The dictionary below is commented out to reflect this new approach and to avoid confusion.
# This file might be deprecated or repurposed in the future (e.g., to list supported
# exchange IDs or provide utility functions related to exchanges if needed).

# exchanges = {
#     'binance': ccxt.binance(),
#     'kucoin': ccxt.kucoin2(), # Note: ccxt.kucoin2 refers to KuCoin v2 API; ccxt.kucoin for v1.
#                              # The actual CCXT ID used (e.g., 'kucoin' or 'kucoinfutures')
#                              # should match what's expected by the ccxt library and configured
#                              # by the user in exchange_configs.
#     'bittrex': ccxt.bittrex(),
#     # Add other exchanges here if this file were to be used for default, keyless instances
#     # for other purposes, but ArbitrageRunner will not use these for its core functions.
# }

# If this file is intended to provide a list of supported exchange IDs for UI or validation:
# SUPPORTED_EXCHANGE_IDS = [
#     'binance',
#     'kraken',
#     'kucoin',
#     'bittrex',
#     'bitfinex',
#     # ... etc.
# ]
# This would be a separate constant, not a dictionary of instances.
```
