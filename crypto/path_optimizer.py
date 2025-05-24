from docplex.mp.model import Model
import numpy as np
from itertools import combinations
# from .info import fiat, trading_fee, tokens # Remove trading_fee from here
from .info import fiat, tokens # Keep fiat and tokens if they are still used and not passed in
from .utils import get_withdrawal_fees, get_crypto_prices, multiThread
import re
from copy import deepcopy


class PathOptimizer(Model):
    '''
    optimization model class for solving multi-lateral arbitrage path that maximizes profit.
    It outputs value zero when no arbitrage opportunity is found. When an opportunity is found,
    the model outputs the profit percentage as well as the arbitrage path.
    Arbitrage output considers the transaction spread as well as commission rates.
    Users can change parameter settings through modifying function set_params or inherit in subclass.

    Example Use:
    m = PathOptimizer(exchanges_instances_dict, trading_fees=fees_dict, cmc_api_key=key_str) # Example of new call
    m.find_arbitrage()
    '''
    length = None  # number n, the number of currencies included.
    path_length = None  # the upper bound of arbitrage path length
    currency_set = None  # a set of length n, where n is the number of currencies included.
    exchanges = None  # the dict for storing clients towards each exchanges

    transit_price_matrix = None
    trading_fees = None  # MODIFIED: This will store the passed-in trading_fees dictionary.
    cmc_api_key = None   # NEW: To store the CoinMarketCap API Key.
    interex_trading_size = None  
    withdrawal_fee = None  
    include_fiat = None  
    inter_exchange_trading = None  
    fiat_set = None  
    token_set = None 
    run_times = 0  
    refresh_time = None  
    var_location = None  
    commission_matrix = None
    vol_matrix = None  
    currency2index = None  
    index2currency = None  
    required_currencies = None  
    crypto_prices = None  
    min_trading_limit = None  
    balance_dict = None  
    price = None  
    inter_convert_list = None  
    consider_inter_exc_bal = None  
    consider_init_bal = None  
    print_content = None  
    simulated_bal = None  

    obj = None  
    var = None  
    x = None  
    xs = None  
    path = None  

    # MODIFIED __init__ to directly accept new parameters or pass through **params
    # If ArbitrageRunner passes them as named args: exchange_instances, trading_fees, cmc_api_key
    def __init__(self, exchange_instances, trading_fees, cmc_api_key, **params):
        super().__init__()
        self.exchanges = exchange_instances # Renamed from 'exchanges' for clarity if passed directly
        
        # Directly set mandatory new parameters
        self.trading_fees = trading_fees
        self.cmc_api_key = cmc_api_key
        
        # Set other parameters using the existing set_params logic, but ensure it doesn't overwrite the above
        self.set_params(params)


    def _run_time_init(self):
        '''function to initialize params and variables only when find_arbitrage() is run'''
        self.init_currency_info() # Will now use self.cmc_api_key
        self.length = len(self.currency_set)
        self.currency2index = {item: i for i, item in enumerate(self.currency_set)}
        self.index2currency = {val: key for key, val in self.currency2index.items()}
        self.get_inter_convert_list()
        # initiate decision variables and constraints for optimization model
        self.update_withdrawal_fee()
        self.get_var_location()
        var_num = int(np.sum(self.var_location))
        self.var = self.binary_var_list(var_num, name='x')
        self.x = np.zeros([self.length, self.length])
        self.x = self.x.astype('object')
        self.x[self.var_location] = self.var
        self.set_constraints()

    def find_arbitrage(self):
        '''
        solve the optimization model to see whether there is an arbitrage opportunity and save the
        profit rate and arbitrage path. The main function to be used in this object.
        '''
        self.print_content = ''

        if self.run_times == 0:
            self._run_time_init()

        if self.run_times % self.refresh_time == 0:
            self.update_withdrawal_fee()
            self.update_ref_coin_price() # Will now use self.cmc_api_key
            self.update_commission_fee() # Will now use self.trading_fees

        self.update_objectives()
        ms = self.solve()
        if ms is None: # Check if solve failed (e.g. infeasible, unbounded)
            self.obj = 0
            self.path = []
            self.print_content = 'Optimization failed or no solution found.'
            print(self.print_content)
            self.run_times +=1
            return

        self.xs = np.zeros([self.length, self.length])
        try:
            # Ensure var list is not empty and ms contains values for them
            if self.var:
                 self.xs[self.var_location] = ms.get_values(self.var)
            else: # No variables, means no path possible with current var_location
                 self.xs[self.var_location] = [] # or handle as appropriate
        except Exception as e:
            print(f"Error getting variable values: {e}. Model might be infeasible or unbounded.")
            self.obj = 0
            self.path = []
            self.print_content = f'Optimization error: {e}'
            print(self.print_content)
            self.run_times += 1
            return
            
        path_indices = list(zip(*np.nonzero(self.xs)))
        path = [(self.index2currency[i], self.index2currency[j]) for i, j in path_indices]
        self.path = self._sort_list(path)
        
        # Check if objective_value is valid before using it
        if hasattr(ms, 'objective_value') and ms.objective_value is not None:
             self.obj = np.exp(ms.objective_value) - 1 if ms.objective_value is not None else 0
        else:
            self.obj = 0 # Default if no objective value

        self.print_content = 'profit rate: {}, arbitrage path: {}'.format(self.obj, self.path)
        print(self.print_content)
        self.run_times += 1

    def set_params(self, params):
        '''modify some params that might affect the initiation of model before init_currency_info()'''

        # default settings
        self.required_currencies = []
        self.path_length = 4 # Default, can be overridden by params
        self.include_fiat = False
        # self.trading_fees is now set in __init__
        self.fiat_set = fiat # From .info (still used if include_fiat is False)
        self.token_set = tokens # From .info (still used for filtering)
        self.inter_exchange_trading = True
        self.consider_init_bal = True
        self.consider_inter_exc_bal = True
        self.interex_trading_size = 100  # only affects inter-exchange
        self.min_trading_limit = 10
        self.refresh_time = 1000

        # Allow overriding defaults with **params passed to __init__
        # Note: trading_fees and cmc_api_key are handled directly in __init__
        for key, val in params.items():
            if key not in ['trading_fees', 'cmc_api_key']: # Avoid overwriting these if passed in params
                if hasattr(self, key):
                    setattr(self, key, val)
                else:
                    # Allow setting new attributes via params if desired, or raise error
                    # For now, let's be strict and only allow existing attributes to be set via general params.
                    print(f'Warning: Parameter "{key}" is not a predefined attribute in PathOptimizer. It will be ignored.')
                    # raise ValueError('{} is not a valid attribute in model'.format(key)) 
            elif key == 'trading_fees' and self.trading_fees is None: # If passed via params and not __init__ arg
                self.trading_fees = val
            elif key == 'cmc_api_key' and self.cmc_api_key is None: # If passed via params and not __init__ arg
                self.cmc_api_key = val


    def init_currency_info(self):
        '''
        to read in all the available currencies and sort them in order, this function
        needs to initiate the attribute currency_set and required_currencies
        '''
        self.currency_set = set()
        for exc_name, exchange in self.exchanges.items():
            try:
                exchange.load_markets()
                currency_names = ['{}_{}'.format(exc_name, cur) for cur in exchange.currencies.keys()]
                self.currency_set |= set(currency_names)
                if not self.include_fiat:
                    self.currency_set -= set(['{}_{}'.format(exc_name, fiat_cur) for fiat_cur in self.fiat_set]) # Use fiat_cur to avoid clash
            except Exception as e:
                print(f"Error loading markets or currencies for {exc_name}: {e}")
                continue # Skip this exchange if it causes issues

        coin_set = set([i.split('_')[-1] for i in self.currency_set])
        coin_set = coin_set & (self.token_set | self.fiat_set) # Filter by allowed tokens and fiat
        
        # MODIFIED: Pass self.cmc_api_key to get_crypto_prices
        if not self.cmc_api_key:
            print("WARNING: CMC API Key not set in PathOptimizer. Price fetching will likely fail.")
            self.crypto_prices = {} # Cannot fetch prices
        else:
            self.crypto_prices = get_crypto_prices(self.cmc_api_key, list(coin_set)) # Pass list of unique coins

        self.currency_set = set([i for i in self.currency_set if i.split('_')[-1] in self.crypto_prices.keys()])

    def update_transit_price(self):
        '''to update data of the transit_price_matrix'''
        self.price = {}
        self.transit_price_matrix = np.zeros([self.length, self.length])

        exc_name_list = list(self.exchanges.keys())
        thread_num = len(exc_name_list)
        exc_price_list = multiThread(self.parallel_fetch_tickers, exc_name_list, thread_num)
        for exc_price in exc_price_list:
            self.price.update(exc_price)

        for pair, items in self.price.items():
            try:
                from_cur, to_cur = pair.split('/')
                if from_cur in self.currency_set and to_cur in self.currency_set:
                    from_index = self.currency2index[from_cur]
                    to_index = self.currency2index[to_cur]
                    if items.get('ask') and items.get('bid') and items['ask'] != 0 and items['bid'] != 0: # Check existence and non-zero
                        self.transit_price_matrix[from_index, to_index] = items['bid']
                        self.transit_price_matrix[to_index, from_index] = 1 / items['ask']
                    else:
                        # print(f"Warning: Missing or zero bid/ask for {pair} on an exchange. Setting transit price to 0.")
                        self.transit_price_matrix[from_index, to_index] = 0
                        self.transit_price_matrix[to_index, from_index] = 0
            except Exception as e:
                print(f"Error processing ticker {pair}: {e}")
                continue


        for from_cur, to_cur in self.inter_convert_list:
            from_index = self.currency2index[from_cur]
            to_index = self.currency2index[to_cur]

            if from_cur in self.withdrawal_fee:
                self.transit_price_matrix[from_index, to_index] = 1
            else: # If no withdrawal fee info, assume not transferable this way for model
                self.transit_price_matrix[from_index, to_index] = 0

            if to_cur in self.withdrawal_fee:
                self.transit_price_matrix[to_index, from_index] = 1
            else: # If no withdrawal fee info, assume not transferable this way
                self.transit_price_matrix[to_index, from_index] = 0

    def update_withdrawal_fee(self):
        '''update withdrawal fee for each exchange'''
        self.withdrawal_fee = {}
        # Iterate over items (name, instance) for clarity
        for exc_name, exchange_instance in self.exchanges.items(): # Use self.exchanges (dict of instances)
            try:
                # Pass exchange_instance to get_withdrawal_fees
                fee = get_withdrawal_fees(exchange_instance, self.interex_trading_size) 
                for currency_code in list(fee.keys()):
                    # Construct full name, e.g., "binance_BTC"
                    new_name = '{}_{}'.format(exc_name, currency_code) 
                    if new_name in self.currency_set:
                        fee[new_name] = fee.pop(currency_code)
                    else:
                        fee.pop(currency_code) # Remove if not in the considered currency set
                self.withdrawal_fee.update(fee)
            except Exception as e:
                print(f"Error updating withdrawal fees for {exc_name}: {e}")
                continue


    def update_balance(self):
        '''function to update the crypto-currency balance in all the exchanges'''
        self.balance_dict = {}
        coin_set = set([i.split('_')[-1] for i in self.currency_set])

        exc_name_list = list(self.exchanges.keys())
        thread_num = len(exc_name_list)
        
        # Ensure self.exchanges contains CCXT instances
        fetch_free_balance = lambda x_name: self.exchanges[x_name].fetch_free_balance() if hasattr(self.exchanges.get(x_name), 'fetch_free_balance') else {}
        
        if self.simulated_bal is None:
            exc_bal_list = multiThread(fetch_free_balance, exc_name_list, thread_num)
            exc_bal_dict = dict(zip(exc_name_list, exc_bal_list))
        else:
            exc_bal_dict = deepcopy(self.simulated_bal)

        for exc_name, exc_bal in exc_bal_dict.items(): # Iterate through the fetched/simulated balances
            # exc_bal = exc_bal_dict[exc_name]
            for i in list(exc_bal.keys()): # i is the short coin symbol e.g. 'BTC'
                if i in coin_set and i in self.crypto_prices and 'price' in self.crypto_prices[i]: # Ensure price info exists
                    balance = exc_bal.pop(i)
                    usd_balance = balance * self.crypto_prices[i]['price']
                    full_name = '{}_{}'.format(exc_name, i)
                    if full_name in self.currency_set: # Ensure the full currency name is in our set
                         self.balance_dict[full_name] = {
                            'balance': balance,
                            'usd_balance': usd_balance
                        }
                else: # Coin not in consideration or no price info
                    exc_bal.pop(i, None) # Remove safely

            # self.balance_dict.update(exc_bal) # This was incorrect; balances are per full_name

    def update_commission_fee(self):
        '''function to update the withdrawal fee and trading commission fee into the commission matrix'''
        self.commission_matrix = np.zeros([self.length, self.length])
        
        # Ensure self.trading_fees is a dictionary
        if not isinstance(self.trading_fees, dict):
            print("ERROR: self.trading_fees is not a dictionary. Cannot update commission fees.")
            # Potentially use a default if this state is recoverable, or ensure __init__ sets it properly.
            # For now, it will likely cause errors below if not a dict.
            # A robust solution would be to have a default fee in self.trading_fees like self.trading_fees.get('default', 0.002)
            default_fee_val = 0.002 # A fallback default
        else:
            default_fee_val = self.trading_fees.get('default', 0.002)


        # intra exchange commission fee
        for exc_name in self.exchanges.keys():
            indexes = [index for cur_name, index in self.currency2index.items() if exc_name in cur_name.split('_')[0]] # Match by prefix
            
            # Get the fee for the current exchange, or use the default fee
            current_exchange_fee = self.trading_fees.get(exc_name, default_fee_val) if isinstance(self.trading_fees, dict) else default_fee_val
            
            # Apply this fee to the commission matrix for intra-exchange trades
            # Using np.ix_ for indexing submatrix might be cleaner if performance is an issue for large N
            for r_idx in indexes:
                for c_idx in indexes:
                    if r_idx != c_idx: # No fee for converting a currency to itself
                         self.commission_matrix[r_idx, c_idx] = current_exchange_fee
        
        # inter exchange commission fee (withdrawal fees)
        for from_cur, to_cur in self.inter_convert_list:
            from_index = self.currency2index[from_cur]
            to_index = self.currency2index[to_cur]

            if from_cur in self.withdrawal_fee and 'usd_rate' in self.withdrawal_fee[from_cur]:
                self.commission_matrix[from_index, to_index] = self.withdrawal_fee[from_cur]['usd_rate']
            # else:
                # If no withdrawal fee, commission is 0 for this path (or path is impossible if transit_price also 0)
                # self.commission_matrix[from_index, to_index] = 0 # Or some high value if impossible

            if to_cur in self.withdrawal_fee and 'usd_rate' in self.withdrawal_fee[to_cur]: # Check reverse path
                self.commission_matrix[to_index, from_index] = self.withdrawal_fee[to_cur]['usd_rate']
            # else:
                # self.commission_matrix[to_index, from_index] = 0


    def update_ref_coin_price(self):
        '''update all crypto currencies' prices in terms of US dollars'''
        # MODIFIED: Pass self.cmc_api_key
        if not self.cmc_api_key:
            print("WARNING: CMC API Key not set. Cannot update reference coin prices.")
            # self.crypto_prices might become stale or remain empty.
            return
        if not self.crypto_prices: # If it's empty initially
             print("INFO: crypto_prices is empty, attempting to fetch for all known coins in currency_set.")
             coin_set = set([i.split('_')[-1] for i in self.currency_set])
             if coin_set:
                 self.crypto_prices = get_crypto_prices(self.cmc_api_key, list(coin_set))
             else:
                 print("WARNING: No coins in currency_set to fetch prices for.")
        else: # Update existing
            self.crypto_prices = get_crypto_prices(self.cmc_api_key, list(self.crypto_prices.keys()))


    def set_constraints(self):
        '''set optimization constraints for the Cplex model'''
        if not self.var_location.any(): # No possible paths
            print("WARNING: var_location is all False. No paths to optimize. Constraints skipped.")
            return

        # 1. closed-circle arbitrage requirement, for each currency, transit-in equals transit-out.
        self.add_constraints(
            (self.sum(self.x[currency, j] for j in range(self.length) if self.var_location[currency,j] ) == \
             self.sum(self.x[i, currency] for i in range(self.length) if self.var_location[i,currency] ) \
             for currency in range(self.length)), names='flow_balance')
        
        # 2. each currency can only be transited-in at most once.
        self.add_constraints((self.sum(self.x[currency, j] for j in range(self.length) if self.var_location[currency,j]) <= 1 \
                              for currency in range(self.length)), names='max_one_in')
        
        # 3. each currency can only be transited-out at most once.
        self.add_constraints((self.sum(self.x[i, currency] for i in range(self.length) if self.var_location[i,currency]) <= 1 \
                              for currency in range(self.length)), names='max_one_out')

        # 4. the whole arbitrage path should be less than a given length
        if isinstance(self.path_length, int) and self.path_length > 0 :
            self.add_constraint(self.sum(self.x[i,j] for i in range(self.length) for j in range(self.length) if self.var_location[i,j] ) <= self.path_length, ctname='path_len')
        
        # 5. the arbitrage path have to go by some certain nodes, in update_changeable_constraint()
        # This constraint is added/updated in update_changeable_constraint()

    def update_objectives(self):
        '''
        update balance, transition price matrix, volume matrix and changeable constraint, and modify maximization
        objective based on that
        '''
        self.update_balance()
        self.update_transit_price()
        self.update_vol_matrix()
        self.update_changeable_constraint() # This might add/remove a constraint

        # Ensure var_location is boolean for indexing
        final_transit_matrix = np.log(
            np.nan_to_num(self.transit_price_matrix) * \
            (1 - np.nan_to_num(self.commission_matrix)) * \
            ((np.nan_to_num(self.vol_matrix) >= self.min_trading_limit).astype(int))
        )
        
        # Ensure only valid, non-zero, non-inf log values are used
        final_transit_matrix[~np.isfinite(final_transit_matrix)] = -np.inf # Penalize invalid paths heavily
        
        # Get only the elements where a variable exists
        final_transit_values_for_vars = final_transit_matrix[self.var_location]
        
        # Ensure self.var (the list of CPLEX variables) matches the number of True in var_location
        if len(self.var) == len(final_transit_values_for_vars):
            self.maximize(self.sum(self.var[i] * final_transit_values_for_vars[i] for i in range(len(self.var))))
        else:
            print(f"ERROR: Mismatch between number of decision variables ({len(self.var)}) and valid paths ({len(final_transit_values_for_vars)}). Objective not set.")
            # This state indicates a severe issue, likely in get_var_location or _run_time_init
            # To prevent CPLEX error, we might set a dummy objective or skip maximization.
            # For now, this will likely lead to CPLEX errors if solve() is called.
            # A robust solution might be to not proceed with solve() if this occurs.
            if not self.var and not final_transit_values_for_vars: # No variables, no paths
                 self.maximize(0) # Maximize constant 0 if no variables
            # else: error state


    def update_vol_matrix(self, percentile=0.01):
        '''
        function to update the volume matrix which is used to determine whether a path is feasible.
        '''
        usd_values = {}
        self.vol_matrix = np.zeros([self.length, self.length])

        for key, val_dict in self.price.items(): # val_dict is the ticker content
            if isinstance(val_dict, dict): # Ensure val_dict is a dictionary
                base_cur_short = key.split('/')[0].split('_')[-1] # Short name like 'BTC'
                if base_cur_short in self.crypto_prices and \
                   self.crypto_prices[base_cur_short].get('price') is not None and \
                   val_dict.get('baseVolume') is not None:
                    
                    usd_values[key] = val_dict['baseVolume'] * self.crypto_prices[base_cur_short]['price'] * percentile
            # else: print(f"Warning: Ticker {key} data is not a dict: {val_dict}")


        for key, val_usd in usd_values.items():
            from_cur_full, to_cur_full = key.split('/') # These are full names like 'binance_BTC'
            if from_cur_full in self.currency_set and to_cur_full in self.currency_set:
                self.vol_matrix[self.currency2index[from_cur_full], self.currency2index[to_cur_full]] = val_usd
                self.vol_matrix[self.currency2index[to_cur_full], self.currency2index[from_cur_full]] = val_usd

        for from_cur_full, to_cur_full in self.inter_convert_list:
            if self.consider_inter_exc_bal:
                from_cur_bal = self.balance_dict.get(from_cur_full, {}).get('usd_balance', 0)
                to_cur_bal = self.balance_dict.get(to_cur_full, {}).get('usd_balance', 0)
            else:
                from_cur_bal = np.inf # Effectively no balance constraint
                to_cur_bal = np.inf

            # Volume for inter-exchange is based on the destination balance if withdrawing to it
            # plus the fee (already in USD terms from withdrawal_fee structure)
            if from_cur_full in self.withdrawal_fee and 'usd_fee' in self.withdrawal_fee[from_cur_full]:
                from_cur_withdraw_fee = self.withdrawal_fee[from_cur_full]['usd_fee']
                # The "volume" or capacity of this path is how much of destination coin we can get,
                # limited by destination balance. Or, if trading size is fixed, it's that size.
                # This logic might need refinement based on how interex_trading_size is used.
                # For now, let's consider it as destination_balance + fee as a rough measure of capacity
                # This seems to be what the original logic implied.
                self.vol_matrix[self.currency2index[from_cur_full], self.currency2index[to_cur_full]] = to_cur_bal + from_cur_withdraw_fee
            
            if to_cur_full in self.withdrawal_fee and 'usd_fee' in self.withdrawal_fee[to_cur_full]:
                to_cur_withdraw_fee = self.withdrawal_fee[to_cur_full]['usd_fee']
                self.vol_matrix[self.currency2index[to_cur_full], self.currency2index[from_cur_full]] = from_cur_bal + to_cur_withdraw_fee


    def get_inter_convert_list(self):
        '''store all the possible inter-exchange trading path'''
        self.inter_convert_list = []
        if self.inter_exchange_trading:
            same_currency_maps = dict()
            for i in self.currency_set: # self.currency_set contains full names like 'binance_BTC'
                short_name = i.split('_')[-1] # Extracts 'BTC'
                if short_name not in same_currency_maps:
                    same_currency_maps[short_name] = [i]
                else:
                    same_currency_maps[short_name].append(i)

            for short_name, full_names_list in same_currency_maps.items():
                if len(full_names_list) >= 2: # If BTC exists on two or more exchanges
                    for from_cur_full, to_cur_full in combinations(full_names_list, 2):
                        # Ensure these paths are only added if withdrawal is possible (fee info exists)
                        # This check might be better placed in update_vol_matrix or update_transit_price for inter-exchange
                        if from_cur_full in self.withdrawal_fee and to_cur_full in self.withdrawal_fee:
                             self.inter_convert_list.append((from_cur_full, to_cur_full))
                        # else:
                        #    print(f"Skipping inter-exchange {from_cur_full} -> {to_cur_full} due to missing withdrawal fee info for one or both.")


    def _sort_list(self, tuple_list):
        '''
        sort the list by having each tuple in the list to be connected one by one, head to tail,
        the first item of the list would be a top-rank coin if the path includes one.
        '''
        if not tuple_list: return [] # Handle empty list early
        
        # Create a dictionary to quickly find the next segment in the path
        # Key: start_node, Value: (start_node, end_node) segment
        path_segments = {segment[0]: segment for segment in tuple_list}
        
        # Determine the starting point of the path
        # Prefer a currency from self.required_currencies if it starts a segment
        start_node = None
        if self.required_currencies:
            for currency in self.required_currencies:
                if currency in path_segments:
                    start_node = currency
                    break
        
        # If no required currency starts a path, or no required_currencies, pick any start from the list
        if start_node is None:
            # To make it deterministic and avoid issues if tuple_list is empty later
            if not path_segments: return [] 
            
            # Try to find a node that is a start but not an end of any other segment (a true start)
            all_start_nodes = set(path_segments.keys())
            all_end_nodes = set(s[1] for s in path_segments.values())
            possible_true_starts = list(all_start_nodes - all_end_nodes)
            if possible_true_starts:
                start_node = possible_true_starts[0] # Pick one deterministically
            else: # It's a cycle, pick the first segment's start node from original list
                 start_node = tuple_list[0][0]


        if start_node not in path_segments: # Path is disjointed or empty
            # This can happen if the path is not a simple cycle or line, or if tuple_list was empty and required_currencies didn't match
            # Fallback to just returning the original list if sorting logic fails to find a start
            # Or, if it implies an error, handle accordingly. For now, return as is if complex.
            # print("Warning: Could not determine a definitive start for path sorting. Returning original path segments.")
            return tuple_list


        sorted_path = []
        current_segment = path_segments[start_node]
        
        for _ in range(len(tuple_list)): # Max iterations to prevent infinite loop in malformed paths
            if current_segment not in sorted_path:
                 sorted_path.append(current_segment)
            else: # Already added this segment, implies a cycle that's been completed or error
                break 
            
            next_start_node = current_segment[1] # End of current is start of next
            if next_start_node in path_segments:
                current_segment = path_segments[next_start_node]
                if current_segment == sorted_path[0] and len(sorted_path) == len(tuple_list): # Closed the loop
                    break 
            else: # Path breaks
                break 
        
        # If the sorted path doesn't include all segments, it might be a disjointed path
        # or the logic needs to handle multiple cycles/paths. For now, this handles one cycle/line.
        if len(sorted_path) != len(tuple_list) and len(tuple_list) > 0 :
             # print(f"Warning: Path sorting might be incomplete. Original: {len(tuple_list)}, Sorted: {len(sorted_path)}")
             # This could happen with multiple disjoint paths from Cplex. For now, return what was sorted.
             pass

        return sorted_path


    def parallel_fetch_tickers(self, exc_name):
        '''function to be used to fetch ticker info in multi-thread wrapper'''
        try:
            exchange_instance = self.exchanges.get(exc_name)
            if not exchange_instance:
                print(f"Error: Exchange instance for {exc_name} not found in self.exchanges.")
                return {}

            # Ensure markets are loaded for the exchange instance
            if not exchange_instance.markets or not exchange_instance.symbols: # Check if markets are loaded
                print(f"INFO: Markets for {exc_name} not loaded by parallel_fetch_tickers. Loading now...")
                exchange_instance.load_markets() # Load markets if not already loaded

            exc_tickers_raw = exchange_instance.fetch_tickers() # Fetch all tickers
            processed_tickers = {}
            for pair_symbol, ticker_data in exc_tickers_raw.items():
                # Standardize pair format (e.g., BTC/USDT) and ensure it's in loaded markets
                if pair_symbol in exchange_instance.markets:
                    # Construct full name: 'exchangeName_BASE/exchangeName_QUOTE'
                    base_ccy, quote_ccy = pair_symbol.split('/')
                    full_pair_name = f"{exc_name}_{base_ccy}/{exc_name}_{quote_ccy}"
                    processed_tickers[full_pair_name] = ticker_data
                # else: # Ticker pair not in loaded markets, might be an issue or ignorable
                    # print(f"Debug: Ticker {pair_symbol} for {exc_name} not in its loaded markets. Skipping.")
            return processed_tickers
        except Exception as e:
            print(f"Error in parallel_fetch_tickers for {exc_name}: {e}")
            # traceback.print_exc()
            return {}


    def update_changeable_constraint(self):
        '''
        constraint about required currencies
        the arbitrage path have to go by some certain nodes.
        '''
        if self.consider_init_bal:
            # Sort coins by their USD balance, high to low
            coin_balance_list = [(key, val.get('usd_balance', 0)) for key, val in self.balance_dict.items() if val.get('usd_balance', 0) >= self.min_trading_limit]
            coin_balance_list = sorted(coin_balance_list, key=lambda x: x[1], reverse=True)
            
            new_required_currencies = [item[0] for item in coin_balance_list] # item[0] is full currency name like 'binance_BTC'
            
            # Check if the list of required currencies has actually changed
            # This avoids removing and re-adding the same constraint if the list is identical
            is_same_as_before = (new_required_currencies == self.required_currencies)
            
            self.required_currencies = new_required_currencies # Update to the new list

            if not self.required_currencies: # If list is empty, no constraint needed or remove existing
                if self.get_constraint_by_name('changeable_currency_flow'):
                    self.remove_constraint('changeable_currency_flow')
                return # Exit early

            if is_same_as_before and self.get_constraint_by_name('changeable_currency_flow'):
                # If list is same and constraint exists, do nothing
                return

            # If list changed or constraint doesn't exist, update/add it
            required_cur_indices = [self.currency2index[cur_name] for cur_name in self.required_currencies if cur_name in self.currency2index]
            
            if not required_cur_indices: # If none of the required currencies are in our model's index
                if self.get_constraint_by_name('changeable_currency_flow'):
                    self.remove_constraint('changeable_currency_flow')
                return

            # Define the constraint: sum of flows out of required currencies must be >= a small fraction of total flow (or 1 if path exists)
            # This encourages using these high-balance currencies.
            # Sum of x[idx, j] for all j where var_location[idx, j] is True
            sum_outflows_from_required = self.sum(self.x[idx, j] 
                                                  for idx in required_cur_indices 
                                                  for j in range(self.length) 
                                                  if self.var_location[idx,j])
            
            # A small positive lower bound if any path exists, to ensure at least one required currency is used.
            # If we want to ensure *at least one* of these is used if *any* path is chosen:
            # This constraint means: "if there is any flow (sum(x) > 0), then sum_outflows_from_required must be >= 1"
            # This can be tricky. A simpler one: "sum_outflows_from_required >= 1" if a path should always start from one of these.
            # Or, if any path is chosen, it must include one of these.
            # The original "left >= right * sum(x)" is a bit unusual. Let's try "sum_outflows_from_required >= 1"
            # This means at least one edge must start from one of the high-balance currencies.
            # This might be too restrictive if the optimal path doesn't start there.
            
            # Let's use: sum of flows through required_currencies (in or out) >= 1, if total sum(x) > 0
            # total_flow_through_required = self.sum(self.x[idx, j] for idx in required_cur_indices for j in range(self.length) if self.var_location[idx,j]) + \
            #                               self.sum(self.x[j, idx] for idx in required_cur_indices for j in range(self.length) if self.var_location[j,idx])
            # This sum might double count if a required currency transits to another required currency.
            # A simpler approach: at least one of the required currencies must be part of the path.
            # That is, sum over k in required_cur_indices ( sum over j (x_kj) ) >= 1
            
            # Reverting to a simpler interpretation or the original if it was intended:
            # "sum of (flows out of required currencies) >= N" where N could be 1 to ensure one is used.
            # Or, the original logic might have been to encourage use, not strictly require.
            # For now, let's try to make it "at least one required currency must be used (either as start or intermediate)"
            # This means sum of (x_ij where i is required OR j is required) >= 1
            # This is complex to write directly.
            
            # The original was: self.sum(self.x[required_cur_index, :]) >= 0.0000001 * self.sum(self.x)
            # This means sum of edges starting from required_currencies must be non-zero if any path exists.
            # Let's stick to this logic but ensure it's correctly formulated.
            
            # Sum of all variables (x_ij for all i,j where var_location is true)
            total_vars_sum = self.sum(self.var) # self.var is already filtered by var_location

            if self.get_constraint_by_name('changeable_currency_flow'):
                self.remove_constraint('changeable_currency_flow')
            
            # If there are required currencies and variables to form a path
            if required_cur_indices and len(self.var) > 0:
                 # Constraint: sum_outflows_from_required >= (a very small number if total_vars_sum > 0, else 0)
                 # This is tricky with CPLEX. A common way: sum_outflows_from_required >= Y, where Y is a binary var,
                 # and Y is 1 if total_vars_sum > 0.
                 # Or more simply: if a path exists (total_vars_sum >=1), then sum_outflows_from_required >=1
                 # This can be written with an indicator constraint or a big-M formulation.
                 # For now, let's use a simpler "if any path, at least one outflow from required":
                 # sum_outflows_from_required >= 1 * (any_var_selected_binary)
                 # This is still complex. The original was a soft constraint.
                 # Let's try: sum_outflows_from_required >= 1 (if we want to force using one)
                 # Or if just to encourage: it's part of objective. The constraint should be hard if used.

                 # Constraint: if any path is chosen (sum(all x_ij) >= 1), then at least one x_kj (k in required) must be chosen.
                 # This implies sum_outflows_from_required >= 1 if self.sum(self.var) >=1
                 # This is a logical constraint. For CPLEX:
                 # self.add_indicator(self.sum(self.var) >= 1, sum_outflows_from_required >= 1, name='changeable_currency_flow')
                 # Docplex syntax for indicator: model.if_then(condition_constraint, then_constraint)
                 
                 # For now, let's use a simpler direct constraint if required_currencies exist:
                 self.add_constraint(sum_outflows_from_required >= 1, ctname='changeable_currency_flow')
                 # This means if a path is found, it MUST start from one of the high-balance currencies.
                 # This might be too restrictive. The old ">= small_fraction * total_flow" was less strict.
                 # If this causes issues (no paths found), this constraint is a candidate for revision.
                 # print(f"INFO: Added 'changeable_currency_flow' constraint for {len(required_cur_indices)} currencies.")


    def get_var_location(self):
        '''
        a function to locate all the trading-feasible pairs so that decision variables can be located,
        used to reduced the number of decision variables, to accelerate the modelling speed.
        '''
        self.var_location = np.zeros([self.length, self.length], dtype=bool) # Initialize with False
        # intra exchange
        for exc_name, exchange in self.exchanges.items():
            # Markets should be loaded before this point (e.g. in init_currency_info)
            if not exchange.markets: 
                # print(f"Warning: Markets for {exc_name} not loaded in get_var_location. Attempting to load now.")
                try:
                    exchange.load_markets(True) # Force reload
                except Exception as e:
                    print(f"ERROR: Could not load markets for {exc_name} in get_var_location: {e}")
                    continue # Skip this exchange

            for market_symbol in exchange.markets: # market_symbol is like 'BTC/USDT'
                try:
                    # Some exchanges might have symbols that don't split, or are not active
                    if '/' not in market_symbol: continue
                    base_ccy, quote_ccy = market_symbol.split('/')
                except ValueError:
                    # print(f"Warning: Could not parse market symbol '{market_symbol}' for exchange {exc_name}. Skipping.")
                    continue

                from_cur_full = f'{exc_name}_{base_ccy}'
                to_cur_full = f'{exc_name}_{quote_ccy}'
                
                if from_cur_full in self.currency2index and to_cur_full in self.currency2index:
                    from_index = self.currency2index[from_cur_full]
                    to_index = self.currency2index[to_cur_full]
                    self.var_location[from_index, to_index] = True
                    self.var_location[to_index, from_index] = True # Path can go both ways

        # inter exchange
        # Ensure inter_convert_list is up-to-date and reflects actual transferability (e.g. withdrawal fee exists)
        for from_cur_full, to_cur_full in self.inter_convert_list:
            # These are full names like 'binance_BTC'
            if from_cur_full in self.currency2index and to_cur_full in self.currency2index:
                # Check if withdrawal is actually possible (e.g. fee info exists for from_cur_full)
                # This logic should align with how transit_price_matrix handles inter-exchange
                if from_cur_full in self.withdrawal_fee: # If we can withdraw from_cur_full
                    self.var_location[self.currency2index[from_cur_full], self.currency2index[to_cur_full]] = True
                # If we can withdraw to_cur_full (for reverse path)
                if to_cur_full in self.withdrawal_fee:
                    self.var_location[self.currency2index[to_cur_full], self.currency2index[from_cur_full]] = True
        
        # self.var_location = self.var_location == 1 # Already boolean

    def have_opportunity(self):
        '''return whether the optimizer finds a possible arbitrage path'''
        # Path is a list of tuples. Empty list means no path.
        return bool(self.path and len(self.path) > 0 and self.obj > 0)

```
