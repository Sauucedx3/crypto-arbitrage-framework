from flask import Flask
import sys # For potential PYTHONPATH adjustments
import os
import json
import traceback
from ..arbitrage_manager import ArbitrageRunner # ArbitrageRunner is now in arbitrage_manager.py at the root of arbitrage_web_app

# Attempt to set up PYTHONPATH if crypto is not found directly
# This assumes a specific directory structure where 'crypto_arbitrage_framework'
# is a sibling to 'arbitrage_web_app' or is the root containing 'crypto'.
# Adjust as necessary for your actual project structure.
# sys.path.append('../crypto_arbitrage_framework') # Example if needed
# sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'crypto_arbitrage_framework')) # More robust relative path if needed


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_default_strong_secret_key_for_development_only')
    # Add any other initial configurations here if needed later
    # app.config.from_object('config.ConfigObject') # Example for loading from a config class/object

    print("Attempting to initialize ArbitrageRunner with configurations from environment variables...")
    initialization_errors = []
    
    # 1. Load CoinMarketCap API Key
    cmc_api_key_str = os.environ.get('CMC_API_KEY')
    if not cmc_api_key_str:
        initialization_errors.append("CMC_API_KEY environment variable not set.")
        print("ERROR: CMC_API_KEY environment variable not set.")

    # 2. Load Exchange Configurations (expected as a JSON string)
    exchange_configs_json_str = os.environ.get('EXCHANGE_CONFIGS')
    exchange_configs_dict = {}
    if exchange_configs_json_str:
        try:
            exchange_configs_dict = json.loads(exchange_configs_json_str)
            if not isinstance(exchange_configs_dict, dict):
                initialization_errors.append("EXCHANGE_CONFIGS is not a valid JSON dictionary/object.")
                print("ERROR: EXCHANGE_CONFIGS is not a valid JSON dictionary/object.")
                exchange_configs_dict = {} # Reset to empty
        except json.JSONDecodeError as e:
            initialization_errors.append(f"Failed to parse EXCHANGE_CONFIGS JSON: {e}")
            print(f"ERROR: Failed to parse EXCHANGE_CONFIGS JSON: {e}")
    else:
        initialization_errors.append("EXCHANGE_CONFIGS environment variable not set or empty.")
        print("WARNING: EXCHANGE_CONFIGS environment variable not set or empty. No exchanges will be configured.")

    # 3. Load Trading Fees Configuration (expected as a JSON string)
    trading_fees_json_str = os.environ.get('TRADING_FEES_CONFIG')
    trading_fees_dict = {}
    if trading_fees_json_str:
        try:
            trading_fees_dict = json.loads(trading_fees_json_str)
            if not isinstance(trading_fees_dict, dict):
                initialization_errors.append("TRADING_FEES_CONFIG is not a valid JSON dictionary/object.")
                print("ERROR: TRADING_FEES_CONFIG is not a valid JSON dictionary/object.")
                trading_fees_dict = {} # Reset to empty
        except json.JSONDecodeError as e:
            initialization_errors.append(f"Failed to parse TRADING_FEES_CONFIG JSON: {e}")
            print(f"ERROR: Failed to parse TRADING_FEES_CONFIG JSON: {e}")
    else:
        initialization_errors.append("TRADING_FEES_CONFIG environment variable not set or empty.")
        print("WARNING: TRADING_FEES_CONFIG environment variable not set or empty. Default fees in PathOptimizer might apply if not handled.")

    # 4. Load Default Optimizer Parameters from Environment Variables
    # These will be passed to ArbitrageRunner's __init__ to set its default behavior.
    # ArbitrageRunner will then use these defaults unless overridden by parameters sent with a 'start' command.

    # Library defaults (used if env var is missing or invalid)
    lib_def_path_length = 6
    lib_def_simulated_bal_json = None # No simulation by default
    lib_def_interex_trading_size = 2000.0
    lib_def_min_trading_limit = 10.0
    lib_def_orderbook_n = 20
    lib_def_include_fiat = False
    lib_def_inter_exchange_trading = True
    lib_def_consider_init_bal = True
    lib_def_consider_inter_exc_bal = True

    try:
        default_path_length = int(os.environ.get('DEFAULT_PATH_LENGTH', lib_def_path_length))
    except ValueError:
        print(f"WARNING: Invalid DEFAULT_PATH_LENGTH. Using library default: {lib_def_path_length}")
        default_path_length = lib_def_path_length

    default_simulated_bal_json_str = os.environ.get('DEFAULT_SIMULATED_BAL_JSON', lib_def_simulated_bal_json)
    # This JSON string will be parsed within ArbitrageRunner's __init__ for its default_optimizer_params

    try:
        default_interex_trading_size = float(os.environ.get('DEFAULT_INTEREX_TRADING_SIZE', lib_def_interex_trading_size))
    except ValueError:
        print(f"WARNING: Invalid DEFAULT_INTEREX_TRADING_SIZE. Using library default: {lib_def_interex_trading_size}")
        default_interex_trading_size = lib_def_interex_trading_size
    
    try:
        default_min_trading_limit = float(os.environ.get('DEFAULT_MIN_TRADING_LIMIT', lib_def_min_trading_limit))
    except ValueError:
        print(f"WARNING: Invalid DEFAULT_MIN_TRADING_LIMIT. Using library default: {lib_def_min_trading_limit}")
        default_min_trading_limit = lib_def_min_trading_limit

    try:
        default_orderbook_n = int(os.environ.get('DEFAULT_ORDERBOOK_N', lib_def_orderbook_n))
    except ValueError:
        print(f"WARNING: Invalid DEFAULT_ORDERBOOK_N. Using library default: {lib_def_orderbook_n}")
        default_orderbook_n = lib_def_orderbook_n

    # For boolean flags, check for 'true' (case-insensitive)
    default_include_fiat_str = os.environ.get('DEFAULT_INCLUDE_FIAT', str(lib_def_include_fiat))
    default_include_fiat = default_include_fiat_str.lower() == 'true'
    
    default_inter_exchange_trading_str = os.environ.get('DEFAULT_INTER_EXCHANGE_TRADING', str(lib_def_inter_exchange_trading))
    default_inter_exchange_trading = default_inter_exchange_trading_str.lower() == 'true'

    default_consider_init_bal_str = os.environ.get('DEFAULT_CONSIDER_INIT_BAL', str(lib_def_consider_init_bal))
    default_consider_init_bal = default_consider_init_bal_str.lower() == 'true'

    default_consider_inter_exc_bal_str = os.environ.get('DEFAULT_CONSIDER_INTER_EXC_BAL', str(lib_def_consider_inter_exc_bal))
    default_consider_inter_exc_bal = default_consider_inter_exc_bal_str.lower() == 'true'


    if initialization_errors:
        print(f"WARNING: Configuration issues found during Flask app initialization:\n- " + "\n- ".join(initialization_errors))

    try:
        app.runner = ArbitrageRunner(
            exchange_configs=exchange_configs_dict,
            cmc_api_key=cmc_api_key_str,
            trading_fees_config=trading_fees_dict,
            # Pass loaded default optimizer parameters
            default_path_length=default_path_length,
            default_simulated_bal_json=default_simulated_bal_json_str, # Pass as string, parsed in ArbitrageRunner
            default_interex_trading_size=default_interex_trading_size,
            default_min_trading_limit=default_min_trading_limit,
            default_orderbook_n=default_orderbook_n,
            default_include_fiat=default_include_fiat,
            default_inter_exchange_trading=default_inter_exchange_trading,
            default_consider_init_bal=default_consider_init_bal,
            default_consider_inter_exc_bal=default_consider_inter_exc_bal
        )
        runner_status_on_init = app.runner.get_status()
        if runner_status_on_init.get('status') == 'error':
            print(f"ERROR: ArbitrageRunner initialized into an error state. Check errors: {runner_status_on_init.get('error_message')}")
        else:
            print(f"INFO: ArbitrageRunner initialized successfully. Initial status: {runner_status_on_init.get('status')}")

    except ImportError as e: # Handles if ArbitrageRunner or its deps (like crypto.path_optimizer) are not found
        print(f"ERROR: Failed to import ArbitrageRunner or its dependencies: {e}")
        print("Ensure 'arbitrage_manager.py' is correctly placed and all 'crypto.*' modules are in PYTHONPATH.")
        traceback.print_exc()
        app.runner = None 
    except Exception as e: # Catch any other unexpected errors during ArbitrageRunner instantiation
        print(f"ERROR: An unexpected error occurred during ArbitrageRunner initialization: {e}")
        traceback.print_exc()
        app.runner = None
    # else:
        # if app.runner is None: # If it was set to None due to pre-initialization config errors
        #    print("INFO: ArbitrageRunner initialization skipped due to missing critical configurations.")


    with app.app_context():
        from . import routes # Import routes

    return app
