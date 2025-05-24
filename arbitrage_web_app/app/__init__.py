from flask import Flask
import sys # For potential PYTHONPATH adjustments
import os
import json
import traceback
from flask_sqlalchemy import SQLAlchemy # Added for DB
from ..arbitrage_manager import ArbitrageRunner 

# Initialize SQLAlchemy globally so it can be imported by models.py
db = SQLAlchemy()

def create_app():
    app = Flask(__name__, instance_relative_config=True) # Enable instance folder
    
    # Ensure instance folder exists for SQLite DB
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError as e:
        print(f"Error creating instance path {app.instance_path}: {e}")
        # Depending on severity, might want to exit or raise
        pass 

    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_dev_secret_key_!@#$%')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'arbitrage_data.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app) # Initialize db with the Flask app

    print("Attempting to initialize ArbitrageRunner with configurations from environment variables...")
    initialization_errors = []
    
    # 1. Load CoinMarketCap API Key
    cmc_api_key_str = os.environ.get('CMC_API_KEY')
    if not cmc_api_key_str:
        initialization_errors.append("CMC_API_KEY environment variable not set.")
        print("ERROR: CMC_API_KEY environment variable not set.")

    # 2. Load Exchange Configurations
    exchange_configs_json_str = os.environ.get('EXCHANGE_CONFIGS')
    exchange_configs_dict = {}
    if exchange_configs_json_str:
        try:
            exchange_configs_dict = json.loads(exchange_configs_json_str)
            if not isinstance(exchange_configs_dict, dict):
                initialization_errors.append("EXCHANGE_CONFIGS is not a valid JSON dictionary.")
                exchange_configs_dict = {} 
        except json.JSONDecodeError as e:
            initialization_errors.append(f"Failed to parse EXCHANGE_CONFIGS JSON: {e}")
    else:
        initialization_errors.append("EXCHANGE_CONFIGS environment variable not set or empty.")

    # 3. Load Trading Fees Configuration
    trading_fees_json_str = os.environ.get('TRADING_FEES_CONFIG')
    trading_fees_dict = {}
    if trading_fees_json_str:
        try:
            trading_fees_dict = json.loads(trading_fees_json_str)
            if not isinstance(trading_fees_dict, dict):
                initialization_errors.append("TRADING_FEES_CONFIG is not a valid JSON dictionary.")
                trading_fees_dict = {} 
        except json.JSONDecodeError as e:
            initialization_errors.append(f"Failed to parse TRADING_FEES_CONFIG JSON: {e}")
    else:
        initialization_errors.append("TRADING_FEES_CONFIG environment variable not set or empty.")

    # 4. Load Default Optimizer Parameters
    lib_def_path_length = 6
    lib_def_simulated_bal_json = None 
    lib_def_interex_trading_size = 2000.0
    lib_def_min_trading_limit = 10.0
    lib_def_orderbook_n = 20
    lib_def_include_fiat = False
    lib_def_inter_exchange_trading = True
    lib_def_consider_init_bal = True
    lib_def_consider_inter_exc_bal = True

    default_path_length = int(os.environ.get('DEFAULT_PATH_LENGTH', lib_def_path_length))
    default_simulated_bal_json_str = os.environ.get('DEFAULT_SIMULATED_BAL_JSON', lib_def_simulated_bal_json)
    default_interex_trading_size = float(os.environ.get('DEFAULT_INTEREX_TRADING_SIZE', lib_def_interex_trading_size))
    default_min_trading_limit = float(os.environ.get('DEFAULT_MIN_TRADING_LIMIT', lib_def_min_trading_limit))
    default_orderbook_n = int(os.environ.get('DEFAULT_ORDERBOOK_N', lib_def_orderbook_n))
    default_include_fiat = os.environ.get('DEFAULT_INCLUDE_FIAT', str(lib_def_include_fiat)).lower() == 'true'
    default_inter_exchange_trading = os.environ.get('DEFAULT_INTER_EXCHANGE_TRADING', str(lib_def_inter_exchange_trading)).lower() == 'true'
    default_consider_init_bal = os.environ.get('DEFAULT_CONSIDER_INIT_BAL', str(lib_def_consider_init_bal)).lower() == 'true'
    default_consider_inter_exc_bal = os.environ.get('DEFAULT_CONSIDER_INTER_EXC_BAL', str(lib_def_consider_inter_exc_bal)).lower() == 'true'
    
    if initialization_errors:
        print(f"WARNING: General configuration issues (API keys, CEX/Fees JSON) found:\n- " + "\n- ".join(initialization_errors))

    # 5. Load DeFi Specific Configurations
    app.config['POLYGON_RPC_URL'] = os.environ.get('POLYGON_RPC_URL')
    app.config['BICONOMY_API_KEY'] = os.environ.get('BICONOMY_API_KEY')
    app.config['PRIVATE_KEY'] = os.environ.get('PRIVATE_KEY') 
    app.config['POLYGONSCAN_API_KEY'] = os.environ.get('POLYGONSCAN_API_KEY')
    
    # 6. Load Smart Contract Addresses
    app.config['FLASH_LOAN_CONTRACT_ADDRESS'] = os.environ.get('FLASH_LOAN_CONTRACT_ADDRESS')
    app.config['GASLESS_CONTRACT_ADDRESS'] = os.environ.get('GASLESS_CONTRACT_ADDRESS')

    # Logging for DeFi and Contract Address configurations
    # (This can be consolidated or made more structured if needed)
    print(f"INFO: POLYGON_RPC_URL is {'loaded' if app.config.get('POLYGON_RPC_URL') else 'NOT SET'}")
    print(f"INFO: BICONOMY_API_KEY is {'loaded' if app.config.get('BICONOMY_API_KEY') else 'NOT SET'}")
    print(f"INFO: PRIVATE_KEY is {'loaded' if app.config.get('PRIVATE_KEY') else 'NOT SET'} (key value not logged)")
    print(f"INFO: POLYGONSCAN_API_KEY is {'loaded' if app.config.get('POLYGONSCAN_API_KEY') else 'NOT SET'}")
    print(f"INFO: FLASH_LOAN_CONTRACT_ADDRESS is {'loaded' if app.config.get('FLASH_LOAN_CONTRACT_ADDRESS') else 'NOT SET'}")
    print(f"INFO: GASLESS_CONTRACT_ADDRESS is {'loaded' if app.config.get('GASLESS_CONTRACT_ADDRESS') else 'NOT SET'}")

    # Import models here AFTER db is defined and app.config is set,
    # so models.py can import 'db' from this module.
    from . import models # This will create models.py if it doesn't exist and define ArbitrageRecord

    # Initialize ArbitrageRunner (CEX Bot)
    app.runner = None 
    try:
        app.runner = ArbitrageRunner(
            exchange_configs=exchange_configs_dict,
            cmc_api_key=cmc_api_key_str,
            trading_fees_config=trading_fees_dict,
            default_path_length=default_path_length,
            default_simulated_bal_json=default_simulated_bal_json_str,
            default_interex_trading_size=default_interex_trading_size,
            default_min_trading_limit=default_min_trading_limit,
            default_orderbook_n=default_orderbook_n,
            default_include_fiat=default_include_fiat,
            default_inter_exchange_trading=default_inter_exchange_trading,
            default_consider_init_bal=default_consider_init_bal,
            default_consider_inter_exc_bal=default_consider_inter_exc_bal,
            database_uri=app.config['SQLALCHEMY_DATABASE_URI'], # Pass database URI
            record_model_class_path='app.models.ArbitrageRecord' # Pass string path to model
        )
        runner_status_on_init = app.runner.get_status()
        if runner_status_on_init.get('status') == 'error':
            print(f"ERROR: ArbitrageRunner initialized into an error state: {runner_status_on_init.get('error_message')}")
        else:
            print(f"INFO: ArbitrageRunner initialized successfully. Status: {runner_status_on_init.get('status')}")
    except Exception as e: 
        print(f"ERROR: Unexpected error during ArbitrageRunner initialization: {e}")
        traceback.print_exc()
        app.runner = None

    # Initialize DeFiBotManager
    app.defi_runner = None 
    if app.runner and app.runner.status != 'error' and hasattr(app.runner, 'path_optimizer') and app.runner.path_optimizer and hasattr(app.runner, 'amt_optimizer') and app.runner.amt_optimizer:
        if app.config.get('POLYGON_RPC_URL') and app.config.get('PRIVATE_KEY'): 
            try:
                from ..defi_bot_manager import DeFiBotManager 
                app.defi_runner = DeFiBotManager(
                    app_config=app.config, 
                    path_optimizer=app.runner.path_optimizer, 
                    amt_optimizer=app.runner.amt_optimizer
                )
                print("INFO: DeFiBotManager initialized.")
                if app.defi_runner.initialization_error:
                    print(f"WARNING: DeFiBotManager initialized, but reported: {app.defi_runner.initialization_error}")
            except Exception as e_defi_init:
                print(f"ERROR: Unexpected error during DeFiBotManager initialization: {e_defi_init}")
                traceback.print_exc()
        else:
            print("WARNING: DeFiBotManager not initialized: Missing POLYGON_RPC_URL or PRIVATE_KEY.")
    elif app.runner is None or app.runner.status == 'error': # Check if app.runner is None first
        print("WARNING: DeFiBotManager not initialized: ArbitrageRunner (app.runner) is None or in error state.")
    elif not (hasattr(app.runner, 'path_optimizer') and app.runner.path_optimizer and 
              hasattr(app.runner, 'amt_optimizer') and app.runner.amt_optimizer):
        print("WARNING: DeFiBotManager not initialized: ArbitrageRunner's optimizers not available.")


    with app.app_context():
        db.create_all() # Create database tables from models defined in models.py
        from . import routes # Import routes after app and db setup to avoid circular imports

    return app
```
