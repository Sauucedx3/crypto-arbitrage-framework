import os
import sys
import time
from dotenv import load_dotenv

# Add the parent directory to the path so we can import the crypto package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crypto.exchanges import exchanges
from crypto.path_optimizer import PathOptimizer
from crypto.amount_optimizer import AmtOptimizer
from crypto.defi_integration import DeFiIntegration

# Load environment variables from .env file
load_dotenv()

def main():
    # Check if required environment variables are set
    required_env_vars = ['MAINNET_RPC_URL', 'BICONOMY_API_KEY', 'PRIVATE_KEY']
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables before running this script.")
        return
    
    # Simulate the balance of coins in each exchange
    simulated_bal = {
        'binance': {'BTC': 1, 'ETH': 10, 'USDT': 10000, 'USDC': 10000},
    }
    
    # Initialize the path_optimizer with extra parameters
    path_optimizer = PathOptimizer(
        exchanges,
        path_length=4,  # Allow arbitrage path of max length 4
        simulated_bal=simulated_bal,  # Check opportunities with simulated balance
        interex_trading_size=1000,  # Approximate the inter exchange trading size to be 1000 USD
        inter_exchange_trading=False,  # Focus on intra-exchange arbitrage for this example
        min_trading_limit=10  # Minimum trading limit is 10 USD
    )
    path_optimizer.init_currency_info()
    
    # Initialize the amt_optimizer
    amt_optimizer = AmtOptimizer(path_optimizer, orderbook_n=20)
    
    # Initialize the DeFi integration
    defi_integration = DeFiIntegration(
        web3_provider=os.environ.get('MAINNET_RPC_URL'),
        biconomy_api_key=os.environ.get('BICONOMY_API_KEY'),
        path_optimizer=path_optimizer,
        amt_optimizer=amt_optimizer
    )
    
    print("Looking for arbitrage opportunities...")
    
    # Find arbitrage opportunity
    path_optimizer.find_arbitrage()
    
    # If there is an arbitrage path, optimize the solution
    if path_optimizer.have_opportunity():
        print("Arbitrage opportunity found!")
        print(f"Path: {path_optimizer.path}")
        print(f"Expected return: {path_optimizer.ret:.2%}")
        
        # Get the solution
        amt_optimizer.get_solution()
        
        # If a workable trading solution is found, execute with flash loan and gasless transactions
        if amt_optimizer.have_workable_solution():
            solution = amt_optimizer.trade_solution
            print("Workable solution found!")
            print(f"Solution: {solution}")
            
            # Calculate flash loan amount
            token_symbol, amount = defi_integration.calculate_flash_loan_amount(solution)
            print(f"Flash loan required: {amount} {token_symbol}")
            
            # Ask for execution mode
            print("\nExecution modes:")
            print("1. Standard execution (no flash loans or gasless transactions)")
            print("2. Execute with flash loans")
            print("3. Execute with gasless meta transactions")
            print("4. Execute with both flash loans and gasless meta transactions")
            
            mode = input("Select execution mode (1-4): ")
            
            if mode == "1":
                print("Standard execution not implemented in this example.")
                print("Please use the main.py script for standard execution.")
            
            elif mode == "2":
                print("Executing with flash loans...")
                try:
                    tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
                    if tx_hash:
                        print(f"Flash loan transaction hash: {tx_hash}")
                    else:
                        print("Flash loan execution failed")
                except Exception as e:
                    print(f"Error executing flash loan: {e}")
            
            elif mode == "3":
                print("Executing with gasless meta transactions...")
                try:
                    response = defi_integration.execute_arbitrage_gasless()
                    if response:
                        print(f"Gasless transaction response: {response}")
                    else:
                        print("Gasless execution failed")
                except Exception as e:
                    print(f"Error executing gasless transaction: {e}")
            
            elif mode == "4":
                print("Executing with both flash loans and gasless meta transactions...")
                try:
                    # First execute with flash loan
                    tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
                    if tx_hash:
                        print(f"Flash loan transaction hash: {tx_hash}")
                        
                        # Then execute with gasless transactions
                        response = defi_integration.execute_arbitrage_gasless()
                        if response:
                            print(f"Gasless transaction response: {response}")
                        else:
                            print("Gasless execution failed")
                    else:
                        print("Flash loan execution failed")
                except Exception as e:
                    print(f"Error executing combined approach: {e}")
            
            else:
                print("Invalid mode selected")
        else:
            print("No workable solution found")
    else:
        print("No arbitrage opportunity found")

if __name__ == "__main__":
    main()