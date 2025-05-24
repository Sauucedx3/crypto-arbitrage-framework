import time
import multiprocessing
import ccxt # For dynamically creating exchange instances
import traceback # For detailed error logging
import logging # For logging
import os # For creating directories
import json # For trade history
from datetime import datetime # For trade history timestamp

# Assuming the original 'crypto' directory is accessible in PYTHONPATH.
import crypto.path_optimizer # PathOptimizer class will be used here
from crypto.amount_optimizer import AmtOptimizer
from crypto.trade_execution import TradeExecutor
# from crypto.utils import save_record 

class ArbitrageRunner:
    def __init__(self, 
                 exchange_configs, 
                 cmc_api_key, 
                 trading_fees_config, 
                 # Default optimizer parameters start here
                 default_path_length=6, 
                 default_simulated_bal_json=None, # Expect JSON string, parse to dict
                 default_interex_trading_size=2000, 
                 default_min_trading_limit=10, 
                 default_orderbook_n=20,
                 default_include_fiat=False,
                 default_inter_exchange_trading=True,
                 default_consider_init_bal=True, # PathOptimizer specific
                 default_consider_inter_exc_bal=True # PathOptimizer specific
                 ):
        
        self.status = "idle" # Initial status
        self.stop_event = multiprocessing.Event()
        self.last_opportunity = None
        self.error_message = "" # Initialize as empty string to accumulate errors
        self.process = None # For the multiprocessing.Process object
        self.logger = None # Will be initialized by _setup_logger
        self.trade_history_file = None # Will be set by _setup_logger
        self.log_file_path = None # Will be set by _setup_logger

        self._setup_logger()

        # Store core configurations
        self.exchange_configs = exchange_configs
        self.cmc_api_key = cmc_api_key
        self.trading_fees_config = trading_fees_config

        # Store default optimizer parameters
        _sim_bal_parsed = None
        if default_simulated_bal_json:
            try:
                _sim_bal_parsed = json.loads(default_simulated_bal_json)
                if not isinstance(_sim_bal_parsed, dict) and _sim_bal_parsed is not None: # Allow None, but error if not dict
                    self.logger.warning(f"Default simulated_bal_json ('{default_simulated_bal_json}') is not a valid JSON object. Using None.")
                    _sim_bal_parsed = None
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse default_simulated_bal_json: '{default_simulated_bal_json}'. Using None.")
                _sim_bal_parsed = None
        
        self.default_optimizer_params = {
            'path_length': int(default_path_length),
            'simulated_bal': _sim_bal_parsed, # This is now a dict or None
            'interex_trading_size': float(default_interex_trading_size),
            'min_trading_limit': float(default_min_trading_limit),
            'orderbook_n': int(default_orderbook_n),
            'include_fiat': bool(default_include_fiat),
            'inter_exchange_trading': bool(default_inter_exchange_trading),
            'consider_init_bal': bool(default_consider_init_bal),
            'consider_inter_exc_bal': bool(default_consider_inter_exc_bal),
        }
        self.current_optimizer_params = self.default_optimizer_params.copy()
        self.logger.info(f"Default optimizer parameters set: {self.default_optimizer_params}")

        # --- Initialize CCXT Exchange Instances ---
        self.ccxt_exchange_instances = {}
        init_errors = [] 

        if not isinstance(self.exchange_configs, dict) or not self.exchange_configs:
            init_errors.append("Exchange configurations (exchange_configs) are missing, not a dictionary, or empty.")
        else:
            for ex_name, config_params in self.exchange_configs.items():
                if not isinstance(config_params, dict): 
                    init_errors.append(f"Configuration for exchange '{ex_name}' is not a dictionary. Skipping.")
                    continue
                try:
                    exchange_class = getattr(ccxt, ex_name) 
                    self.ccxt_exchange_instances[ex_name] = exchange_class(config_params)
                    self.logger.info(f"Initialized CCXT instance for {ex_name}")
                except AttributeError: 
                    init_errors.append(f"ERROR: CCXT does not have an exchange named '{ex_name}'. Ensure it's a valid CCXT ID. Skipping.")
                except Exception as e: 
                    init_errors.append(f"ERROR: Initializing '{ex_name}' with CCXT failed: {type(e).__name__} - {e}. Check API keys and parameters. Skipping.")
        
        if not self.ccxt_exchange_instances: 
            init_errors.append("WARNING: No CCXT exchange instances were successfully initialized. Arbitrage functions will be impaired.")
        
        if init_errors: 
            self.error_message = "\n".join(init_errors) 
            self.logger.warning(f"ArbitrageRunner initialization encountered issues with CCXT setup:\n{self.error_message}")
            if not self.ccxt_exchange_instances: 
                self.status = "error" 

        # PathOptimizer, AmtOptimizer, and TradeExecutor are NOT initialized here anymore.
        # They will be initialized at the beginning of run_main_loop().
            self.path_optimizer = None
            self.amt_optimizer = None
            self.trade_executor = None

    def _setup_logger(self):
        self.logger = logging.getLogger(f"ArbitrageRunner_{id(self)}")
        # Ensure logger is not reconfigured if already set (e.g. in a restart scenario if object persists)
        if not self.logger.handlers: 
            self.logger.setLevel(logging.INFO)
            logs_dir = 'logs'
            os.makedirs(logs_dir, exist_ok=True)
            self.log_file_path = os.path.join(logs_dir, 'arbitrage_runner.log')
            
            fh = logging.FileHandler(self.log_file_path)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(levelname)s - %(message)s'))
            self.logger.addHandler(fh)
            self.logger.propagate = False

        history_dir = 'history'
        os.makedirs(history_dir, exist_ok=True)
        self.trade_history_file = os.path.join(history_dir, 'trade_history.log')

    def set_optimizer_parameters(self, params_dict):
        self.logger.info(f"Received parameters to override optimizer settings: {params_dict}")
        # Reset to defaults first to ensure overrides are clean for this run
        self.current_optimizer_params = self.default_optimizer_params.copy()
        
        # Helper for safe type conversion
        def _get_typed_param(key, target_type, default_val, is_json=False):
            if key in params_dict:
                val_str = params_dict[key]
                if is_json:
                    if not val_str or not val_str.strip(): # Handle empty string for JSON
                        return default_val # Or None, if that's preferred for empty simulated_bal
                    try:
                        parsed_val = json.loads(val_str)
                        # Further validation if it should be a dict or list
                        if key == 'simulated_bal' and parsed_val is not None and not isinstance(parsed_val, dict):
                            self.logger.warning(f"Invalid type for '{key}': Expected dict, got {type(parsed_val)}. Using default.")
                            return default_val
                        return parsed_val
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Invalid JSON for '{key}': {val_str}. Error: {e}. Using default.")
                        return default_val
                try:
                    if target_type == bool: # Handle boolean conversion from string "true"/"false"
                        if isinstance(val_str, bool): return val_str
                        if isinstance(val_str, str):
                            if val_str.lower() == 'true': return True
                            if val_str.lower() == 'false': return False
                        # If not a recognizable boolean string, it will fail target_type(val_str) or use default
                        return target_type(val_str) if val_str else default_val # fallback for empty string if bool not matched
                    
                    # For other types, allow empty string to mean "use default"
                    return target_type(val_str) if val_str or isinstance(val_str, (int, float, bool)) else default_val
                except ValueError:
                    self.logger.warning(f"Invalid value type for '{key}': {val_str}. Using default.")
                    return default_val
            return default_val

        self.current_optimizer_params['path_length'] = _get_typed_param('path_length', int, self.default_optimizer_params['path_length'])
        self.current_optimizer_params['simulated_bal'] = _get_typed_param('simulated_bal_json', dict, self.default_optimizer_params['simulated_bal'], is_json=True)
        self.current_optimizer_params['interex_trading_size'] = _get_typed_param('interex_trading_size', float, self.default_optimizer_params['interex_trading_size'])
        self.current_optimizer_params['min_trading_limit'] = _get_typed_param('min_trading_limit', float, self.default_optimizer_params['min_trading_limit'])
        self.current_optimizer_params['orderbook_n'] = _get_typed_param('orderbook_n', int, self.default_optimizer_params['orderbook_n'])
        
        self.current_optimizer_params['include_fiat'] = _get_typed_param('include_fiat', bool, self.default_optimizer_params['include_fiat'])
        self.current_optimizer_params['inter_exchange_trading'] = _get_typed_param('inter_exchange_trading', bool, self.default_optimizer_params['inter_exchange_trading'])
        self.current_optimizer_params['consider_init_bal'] = _get_typed_param('consider_init_bal', bool, self.default_optimizer_params['consider_init_bal'])
        self.current_optimizer_params['consider_inter_exc_bal'] = _get_typed_param('consider_inter_exc_bal', bool, self.default_optimizer_params['consider_inter_exc_bal'])

        self.logger.info(f"Optimizer parameters for next run set to: {self.current_optimizer_params}")


    def run_main_loop(self):
        # Initialize optimizers here using self.current_optimizer_params
        self.logger.info(f"run_main_loop started. Effective optimizer params: {self.current_optimizer_params}")
        
        # --- Initialize PathOptimizer, AmtOptimizer, TradeExecutor ---
        # These are now initialized at the start of each run_main_loop call
        self.path_optimizer = None
        self.amt_optimizer = None
        self.trade_executor = None

        if self.status == "error": # Check for errors from __init__ (e.g. CCXT setup)
            self.logger.error(f"Aborting run_main_loop - Runner is in error state from __init__. Errors:\n{self.error_message}")
            return
        if not self.ccxt_exchange_instances: 
            self.status = "error"; self.error_message += "\nCRITICAL ERROR: No CCXT instances for run_main_loop."
            self.logger.error(self.error_message.strip()); return 

        try:
            PathOptimizerClass = crypto.path_optimizer.PathOptimizer 
            self.path_optimizer = PathOptimizerClass(
                exchange_instances=self.ccxt_exchange_instances, 
                trading_fees=self.trading_fees_config, 
                cmc_api_key=self.cmc_api_key, 
                # Optimizer params from current_optimizer_params
                path_length=self.current_optimizer_params['path_length'],
                simulated_bal=self.current_optimizer_params['simulated_bal'],
                interex_trading_size=self.current_optimizer_params['interex_trading_size'],
                min_trading_limit=self.current_optimizer_params['min_trading_limit'],
                include_fiat=self.current_optimizer_params['include_fiat'], # Pass PathOptimizer specific params
                inter_exchange_trading=self.current_optimizer_params['inter_exchange_trading'],
                consider_init_bal=self.current_optimizer_params['consider_init_bal'],
                consider_inter_exc_bal=self.current_optimizer_params['consider_inter_exc_bal']
            )
            self.logger.info(f"PathOptimizer initialized for run with path_length: {self.current_optimizer_params['path_length']}")
        except Exception as e: 
            path_opt_error = f"ERROR: Failed to initialize PathOptimizer in run_main_loop: {type(e).__name__} - {e}."
            self.logger.error(path_opt_error); self.error_message += f"\n{path_opt_error}" 
            self.status = "error"; self.logger.error(traceback.format_exc()); return

        try:
            self.amt_optimizer = AmtOptimizer(self.path_optimizer, orderbook_n=self.current_optimizer_params['orderbook_n'])
            self.logger.info(f"AmtOptimizer initialized for run with orderbook_n: {self.current_optimizer_params['orderbook_n']}")
            self.trade_executor = TradeExecutor(self.path_optimizer)
            self.logger.info("TradeExecutor initialized for run.")
        except Exception as e: 
            opt_exec_error = f"ERROR: Failed to initialize AmtOptimizer/TradeExecutor in run_main_loop: {type(e).__name__} - {e}."
            self.logger.error(opt_exec_error); self.error_message += f"\n{opt_exec_error}"
            self.status = "error"; self.logger.error(traceback.format_exc()); return

        # --- Original Pre-run checks from before (now after optimizer init) ---
        # These are somewhat redundant if the above try-except blocks catch issues, but serve as a final gate.
        if self.status == "error": # If any optimizer init failed
            self.logger.error(f"Aborting run_main_loop - Runner in error state after optimizer init. Errors:\n{self.error_message}")
            return

        self.status = "running" 
        self.logger.info("Initializing currency info for PathOptimizer...")
        try:
            self.path_optimizer.init_currency_info() 
            self.logger.info("Currency info initialized.")
        except Exception as e:
            self.status = "error" 
            error_msg = f"Error during PathOptimizer.init_currency_info(): {type(e).__name__} - {e}."
            self.error_message += f"\n{error_msg}" 
            self.logger.error(f"CRITICAL ERROR in run_main_loop: {error_msg}")
            self.logger.error(traceback.format_exc()) 
            return 

        try:
            loop_count = 0
            while not self.stop_event.is_set():
                loop_count += 1
                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.logger.info(f"[{current_time_str}] Arbitrage loop iteration: {loop_count}, Status: {self.status}")

                self.logger.debug("Finding arbitrage opportunities...")
                self.path_optimizer.find_arbitrage()

                if self.path_optimizer.have_opportunity():
                    self.logger.info("Opportunity found. Optimizing amount...")
                    self.status = "found_opportunity"
                    self.amt_optimizer.get_solution()
                    
                    # Prepare last_opportunity structure
                    path_nodes_serializable = None
                    path_details_serializable = None
                    solution_details_serializable = None

                    if self.path_optimizer.path:
                        path_nodes_serializable = self.path_optimizer.path.nodes # Assuming nodes are serializable
                        if hasattr(self.path_optimizer.path, 'get_path_info'):
                             path_details_serializable = self.path_optimizer.path.get_path_info()

                    if self.amt_optimizer.trade_solution:
                        if hasattr(self.amt_optimizer.trade_solution, 'get_solution_info'):
                            solution_details_serializable = self.amt_optimizer.trade_solution.get_solution_info()
                    
                    self.last_opportunity = {
                        "timestamp_unix": time.time(),
                        "timestamp_iso": datetime.utcnow().isoformat(),
                        "path_nodes": path_nodes_serializable,
                        "path_details": path_details_serializable,
                        "solution_details": solution_details_serializable,
                        "p_value": self.path_optimizer.path.p_value if self.path_optimizer.path else None,
                        "estimated_profit_usd": self.amt_optimizer.trade_solution.estimated_profit_usd if self.amt_optimizer.trade_solution else None
                    }
                    self.logger.info(f"Opportunity details: p_value={self.last_opportunity['p_value']}, profit_usd={self.last_opportunity['estimated_profit_usd']}")
                    self.logger.debug(f"Full opportunity object: {self.last_opportunity}")


                    history_entry_status = "found_opportunity"
                    if self.amt_optimizer.have_workable_solution():
                        self.logger.info("Workable solution found. Simulating trade execution...")
                        # solution = self.amt_optimizer.trade_solution
                        # self.trade_executor.execute(solution) # EXECUTION DISABLED FOR SAFETY
                        self.logger.info("Trade execution SKIPPED for safety in refactoring (simulation only).")
                        self.status = "executed_trade_simulation" 
                        history_entry_status = "executed_trade_simulation_success" # Or _failure if known
                    else:
                        self.logger.info("No workable solution for the current opportunity.")
                        self.status = "opportunity_no_workable_solution"
                        history_entry_status = "opportunity_no_workable_solution"
                    
                    # Save to trade history
                    history_entry = {
                        "timestamp_iso": datetime.utcnow().isoformat(),
                        "opportunity_details": self.last_opportunity, # Save the rich last_opportunity object
                        "status_after_processing": history_entry_status
                    }
                    try:
                        with open(self.trade_history_file, 'a') as f:
                            f.write(json.dumps(history_entry) + '\n')
                    except Exception as e_hist:
                        self.logger.error(f"Failed to write to trade history file {self.trade_history_file}: {e_hist}")

                else:
                    self.logger.info("No arbitrage opportunity found in this iteration.")
                    self.status = "running_no_opportunity" 

                sleep_duration_total = 20 
                sleep_interval = 1 
                for _ in range(int(sleep_duration_total / sleep_interval)):
                    if self.stop_event.is_set():
                        self.logger.info("Stop event detected during sleep.")
                        break
                    time.sleep(sleep_interval)
                
                if self.stop_event.is_set():
                    self.logger.info("Stop event detected after sleep, breaking loop.")
                    break
            
            if self.stop_event.is_set():
                self.logger.info("Arbitrage loop received stop signal.")
            else: 
                self.logger.warning("Arbitrage loop exited unexpectedly (without stop signal).")
            self.status = "stopped"

        except Exception as e:
            self.error_message = f"Unhandled exception in run_main_loop: {str(e)}"
            self.status = "error"
            self.logger.error(self.error_message)
            self.logger.error(traceback.format_exc())
        finally:
            if self.status not in ["error", "stopped"]:
                 self.status = "stopped"
            self.logger.info(f"Arbitrage loop finished. Final status: {self.status}")


    def start(self):
        if self.status == "running" or (self.process and self.process.is_alive()):
            self.logger.warning("Attempted to start Arbitrage process but it's already running or starting.")
            return
        
        self.logger.info("Starting arbitrage process...")
        self.stop_event.clear()
        self.error_message = None 
        self.last_opportunity = None 
        self.status = "starting" 
        
        self.process = multiprocessing.Process(target=self.run_main_loop, name="ArbitrageLoop")
        self.process.start()
        self.logger.info(f"Arbitrage process started with PID: {self.process.pid}")


    def stop(self):
        if not self.process or not self.process.is_alive():
            self.logger.warning(f"Attempted to stop Arbitrage process, but it's not running or already stopped. Status: {self.status}")
            if self.status not in ["stopped", "error", "idle"]:
                self.status = "stopped" 
            return

        self.logger.info(f"Stopping arbitrage process (PID: {self.process.pid}). Current status: {self.status}")
        self.status = "stopping"
        self.stop_event.set()
        
        self.process.join(timeout=60) 

        if self.process.is_alive():
            self.logger.warning("Process did not terminate gracefully. Forcing termination...")
            self.process.terminate() 
            self.process.join(timeout=10) 
            self.status = "stopped" 
        else:
            self.logger.info("Process terminated gracefully.")
        
        if self.status not in ["error"]: 
            self.status = "stopped"

        self.logger.info(f"Arbitrage process stop sequence complete. Final status: {self.status}")
        self.process = None


    def get_status(self):
        # Check if process died unexpectedly
        current_pid = self.process.pid if self.process else None
        process_alive = self.process.is_alive() if self.process else False

        if self.process and not process_alive and self.status not in ["stopped", "error", "idle", "stopping"]:
            self.logger.warning(f"Process (PID: {current_pid}) found dead unexpectedly. Updating status to error.")
            self.status = "error"
            self.error_message = self.error_message or "Process died unexpectedly."
            # self.process = None # Keep self.process object to see exitcode if needed, but mark not alive

        return {
            "status": self.status,
            "last_opportunity": self.last_opportunity, # Ensure this is JSON serializable
            "error_message": self.error_message,
            "process_alive": process_alive,
            "pid": current_pid,
            "log_file_path": self.log_file_path,
            "trade_history_file": self.trade_history_file
        }

# Example of how it might be used (for testing purposes, not part of the class):
# This __main__ block needs to be updated to use the new __init__ signature
# and also to correctly mock PathOptimizer if it's to be run standalone without actual crypto ops.
# For now, this part is outdated due to prior refactoring of __init__.
if __name__ == '__main__':
    # This __main__ block is for basic testing of ArbitrageRunner structure.
    # It requires that crypto.path_optimizer.PathOptimizer is properly mocked
    # or that valid configurations are provided for a real run.
    
    print("--- Mocking PathOptimizer for standalone ArbitrageRunner test ---")
    class MockPathOptimizer:
        def __init__(self, exchange_instances, trading_fees, cmc_api_key, 
                     path_length, simulated_bal, interex_trading_size, min_trading_limit):
            self.logger = logging.getLogger("MockPathOptimizer") # Use logging for mocks too
            self.logger.info(f"Initialized with {len(exchange_instances)} exchanges.")
            self.path = None
            self.trade_solution = None # For AmtOptimizer part

        def init_currency_info(self):
            self.logger.info("init_currency_info() called.")
        def find_arbitrage(self):
            self.logger.info("find_arbitrage() called.")
            # Simulate finding an opportunity sometimes
            if time.time() % 15 < 7 : # Found every ~15s for 7s
                self.path = type('obj', (object,), {'nodes': ['EX1_BTC', 'EX1_USDT', 'EX2_USDT', 'EX2_BTC', 'EX1_BTC'], 'p_value': 0.005, 'get_path_info': lambda: "Mock Path Details"})()
                self.logger.info("Mock opportunity found.")
            else:
                self.path = None
        def have_opportunity(self):
            return self.path is not None

    # Temporarily replace the actual PathOptimizer for this test run
    original_po_class = crypto.path_optimizer.PathOptimizer
    crypto.path_optimizer.PathOptimizer = MockPathOptimizer
    print("--- crypto.path_optimizer.PathOptimizer replaced with MockPathOptimizer ---")

    # Mock configurations
    mock_ex_configs = {'mock_ex1': {}, 'mock_ex2': {}} # Dummy, as CCXT part is somewhat tested by ArbitrageRunner init
    mock_cmc_key = "DUMMY_CMC_KEY"
    mock_fees = {"default": 0.002}

    print("\nInitializing ArbitrageRunner with mock configurations...")
    runner = ArbitrageRunner(
        exchange_configs=mock_ex_configs,
        cmc_api_key=mock_cmc_key,
        trading_fees_config=mock_fees,
        path_length=4
    )
    
    status_info = runner.get_status()
    print(f"Initial status: {status_info['status']}, Log: {status_info['log_file_path']}, History: {status_info['trade_history_file']}")
    
    if status_info['status'] == 'error':
        print(f"Runner initialization failed: {status_info['error_message']}")
    else:
        print("\nAttempting to start ArbitrageRunner...")
        runner.start()
        
        time.sleep(1) # Let it try to start
        print(f"Status after 1s: {runner.get_status()}")
        
        print("Main script will wait for ~25 seconds...")
        time.sleep(25) 
        
        print(f"\nStatus after 25s: {runner.get_status()}")
        if runner.get_status().get("last_opportunity"):
            print(f"  Last opportunity found: {runner.get_status()['last_opportunity']['p_value']}")

        print("\nAttempting to stop ArbitrageRunner...")
        runner.stop()
        
        time.sleep(2) 
        print(f"Final status after stop: {runner.get_status()}")

    # Restore original PathOptimizer
    crypto.path_optimizer.PathOptimizer = original_po_class
    print("\n--- Restored original crypto.path_optimizer.PathOptimizer ---")
    print("--- ArbitrageRunner standalone test with logging and history (mocked PO) complete ---")
            self.process = None # Clear the dead process reference

        return {
            "status": self.status,
            "last_opportunity": self.last_opportunity,
            "error_message": self.error_message,
            "process_alive": self.process.is_alive() if self.process else False,
            "pid": self.process.pid if self.process else None
        }

# Example of how it might be used (for testing purposes, not part of the class):
if __name__ == '__main__':
    # This part is tricky because `exchanges` from `crypto.exchanges` initializes
    # ccxt objects, potentially loading API keys if configured in that file.
    
    print("Defining MockExchange for testing purposes...")
    class MockExchange:
        def __init__(self, name):
            self.name = name
            self.id = name # PathOptimizer uses 'id'
            self.symbols = ['BTC/USDT', 'ETH/USDT', 'ETH/BTC']
            self.currencies = ['BTC', 'USDT', 'ETH']
            self.has = {'fetchTickers': True, 'fetchOHLCV': True, 'fetchOrderBook': True}
            self.verbose = False
            self.rateLimit = 100 # ms, example
            self.checkRequiredCredentials = lambda: None # Mock this method
            print(f"MockExchange '{name}' initialized.")

        def load_markets(self): # PathOptimizer calls this
            print(f"MockExchange '{self.name}': load_markets() called.")
            return {
                s: {"symbol": s, "base": s.split('/')[0], "quote": s.split('/')[1], "active": True} 
                for s in self.symbols
            }

        def fetch_tickers(self, symbols=None): # PathOptimizer calls this
            print(f"MockExchange '{self.name}': fetch_tickers({symbols}) called.")
            tickers = {}
            for sym in symbols if symbols else self.symbols:
                base, quote = sym.split('/')
                tickers[sym] = {
                    'symbol': sym, 'bid': 1.0, 'ask': 1.01, 'timestamp': time.time() * 1000,
                    'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime()),
                    'info': {} # Add more mock data if needed by PathOptimizer logic
                }
            return tickers
        
        def fetch_order_book(self, symbol, limit): # AmtOptimizer calls this via PathOptimizer
            print(f"MockExchange '{self.name}': fetch_order_book({symbol}, {limit}) called.")
            return {
                'bids': [[0.99, 10.0]] * limit, # price, amount
                'asks': [[1.01, 10.0]] * limit,
                'timestamp': time.time() * 1000,
                'datetime': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime()),
                'nonce': None
            }

    mock_exchanges_dict = {
        'mock_ex1': MockExchange('mock_ex1'),
        'mock_ex2': MockExchange('mock_ex2'),
        'mock_ex3': MockExchange('mock_ex3') # Add a third for more complex paths
    }
    
    print("\nSimulating ArbitrageRunner execution with multiprocessing.")
    
    # The PathOptimizer expects a dictionary of ccxt exchange objects.
    print("Initializing ArbitrageRunner with mock exchanges...")
    runner = ArbitrageRunner(exchange_instances=mock_exchanges_dict, path_length=3, interex_trading_size=100)
    
    print(f"Initial status: {runner.get_status()}")
    
    print("\nAttempting to start ArbitrageRunner...")
    runner.start() # This should now run run_main_loop in a separate process
    
    print(f"Status after calling start: {runner.get_status()}")
    print("Main script will wait for a few seconds, then stop the runner...")
    
    time.sleep(5) # Let the runner work for a few seconds
    
    current_status = runner.get_status()
    print(f"\nStatus after 5s: {current_status}")
    if current_status.get("last_opportunity"):
        print(f"Last opportunity found: {current_status['last_opportunity']}")

    time.sleep(25) # Wait for another cycle, path_optimizer should find no opp if graph is static

    current_status = runner.get_status()
    print(f"\nStatus after 30s: {current_status}")
    if current_status.get("last_opportunity"):
        print(f"Last opportunity found: {current_status['last_opportunity']}")


    print("\nAttempting to stop ArbitrageRunner...")
    runner.stop()
    
    # Give some time for the process to fully stop and status to update
    time.sleep(2) 
    print(f"Final status after stop: {runner.get_status()}")

    print("\nTesting restart...")
    runner.start()
    print(f"Status after calling start again: {runner.get_status()}")
    time.sleep(5)
    current_status = runner.get_status()
    print(f"\nStatus after 5s (second run): {current_status}")
    runner.stop()
    time.sleep(2)
    print(f"Final status after second stop: {runner.get_status()}")

    print("\nArbitrageRunner class defined and basic process lifecycle tested.")
    print("Further testing requires integration with actual exchange data or more sophisticated mocks for PathOptimizer/AmtOptimizer logic.")

```
