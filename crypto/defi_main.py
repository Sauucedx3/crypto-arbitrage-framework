import os
import time
from crypto.exchanges import exchanges
from crypto.path_optimizer import PathOptimizer
from crypto.amount_optimizer import AmtOptimizer
from crypto.trade_execution import TradeExecutor
from crypto.defi_integration import DeFiIntegration
from crypto.utils import save_record

if __name__ == '__main__':
    # Check if required environment variables are set
    required_env_vars = ['MAINNET_RPC_URL', 'BICONOMY_API_KEY', 'PRIVATE_KEY']
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables before running this script.")
        exit(1)
    
    # Simulate the balance of coins in each exchange
    simulated_bal = {
        'kucoin': {'BTC': 10, 'ETH': 200, 'NEO': 1000, 'XRP': 30000, 'XLM': 80000},
        'binance': {'BTC': 10, 'ETH': 200, 'NEO': 1000, 'XRP': 30000, 'XLM': 80000},
        'bittrex': {'BTC': 10, 'ETH': 200, 'NEO': 1000, 'XRP': 30000, 'XLM': 80000},
    }
    
    # Initialize the path_optimizer with extra parameters
    path_optimizer = PathOptimizer(
        exchanges,
        path_length=6,  # Allow arbitrage path of max length 6
        simulated_bal=simulated_bal,  # Check opportunities with simulated balance
        interex_trading_size=2000,  # Approximate the inter exchange trading size to be 2000 USD
        inter_exchange_trading=True,
        min_trading_limit=10  # Minimum trading limit is 10 USD
    )
    path_optimizer.init_currency_info()
    
    # Initialize the amt_optimizer
    amt_optimizer = AmtOptimizer(path_optimizer, orderbook_n=20)
    
    # Initialize the trade executor
    trade_executor = TradeExecutor(path_optimizer)
    
    # Initialize the DeFi integration
    defi_integration = DeFiIntegration(
        web3_provider=os.environ.get('MAINNET_RPC_URL'),
        biconomy_api_key=os.environ.get('BICONOMY_API_KEY'),
        path_optimizer=path_optimizer,
        amt_optimizer=amt_optimizer
    )
    
    # Define execution modes
    EXECUTION_MODES = {
        'standard': 'Standard execution (no flash loans or gasless transactions)',
        'flash_loan': 'Execute with flash loans',
        'gasless': 'Execute with gasless meta transactions',
        'both': 'Execute with both flash loans and gasless meta transactions'
    }
    
    # Select execution mode (can be changed to any of the above)
    execution_mode = 'standard'
    print(f"Execution mode: {EXECUTION_MODES[execution_mode]}")
    
    # Loop over the process of finding opportunities and executing trades
    for i in range(10):
        print(f"\nIteration {i+1}/10")
        
        # Move all the kucoin money to trade wallet if needed
        if i % 1500 == 0:
            try:
                trade_executor.kucoin_move_to_trade()
                print("Moved funds to Kucoin trade wallet")
            except Exception as e:
                print(f"Error moving funds to Kucoin trade wallet: {e}")
        
        try:
            # Find arbitrage
            path_optimizer.find_arbitrage()
            
            # If there is an arbitrage path, optimize the solution
            if path_optimizer.have_opportunity():
                print("Arbitrage opportunity found!")
                
                # Get the solution
                amt_optimizer.get_solution()
                
                # Save the arbitrage path info and amount optimization info to record.txt
                save_record(path_optimizer, amt_optimizer)
                
                # If a workable trading solution is found, execute the trade based on the selected mode
                if amt_optimizer.have_workable_solution():
                    solution = amt_optimizer.trade_solution
                    
                    if execution_mode == 'standard':
                        # Standard execution (no flash loans or gasless transactions)
                        print("Executing standard trade...")
                        trade_executor.execute(solution)
                    
                    elif execution_mode == 'flash_loan':
                        # Execute with flash loans
                        print("Executing trade with flash loan...")
                        tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
                        if tx_hash:
                            print(f"Flash loan transaction hash: {tx_hash}")
                        else:
                            print("Flash loan execution failed")
                    
                    elif execution_mode == 'gasless':
                        # Execute with gasless meta transactions
                        print("Executing gasless trade...")
                        response = defi_integration.execute_arbitrage_gasless()
                        if response:
                            print(f"Gasless transaction response: {response}")
                        else:
                            print("Gasless execution failed")
                    
                    elif execution_mode == 'both':
                        # Execute with both flash loans and gasless meta transactions
                        print("Executing trade with flash loan and gasless transactions...")
                        tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
                        if tx_hash:
                            print(f"Flash loan transaction hash: {tx_hash}")
                        else:
                            print("Flash loan execution failed")
                else:
                    print("No workable solution found")
            else:
                print("No arbitrage opportunity found")
        
        except Exception as e:
            print(f"Error in iteration {i+1}: {e}")
        
        # Rest for 20 seconds as some of the APIs do not allow too frequent requests
        print(f"Waiting 20 seconds before next iteration...")
        time.sleep(20)