import os
import sys
import time
from dotenv import load_dotenv

# Add the parent directory to the path so we can import the crypto package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crypto.exchanges import exchanges
from crypto.path_optimizer import PathOptimizer
from crypto.amount_optimizer import AmtOptimizer
from crypto.flash_loan import FlashLoan
from crypto.defi_integration import DeFiIntegration

# Load environment variables from .env file
load_dotenv()

def main():
    # Check if required environment variables are set
    required_env_vars = ['MAINNET_RPC_URL', 'PRIVATE_KEY']
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
        
        # If a workable trading solution is found, execute with flash loan
        if amt_optimizer.have_workable_solution():
            solution = amt_optimizer.trade_solution
            print("Workable solution found!")
            print(f"Solution: {solution}")
            
            # Calculate flash loan amount
            token_symbol, amount = defi_integration.calculate_flash_loan_amount(solution)
            print(f"Flash loan required: {amount} {token_symbol}")
            
            # Ask for confirmation before executing
            confirm = input("Execute flash loan arbitrage? (y/n): ")
            if confirm.lower() == 'y':
                try:
                    tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
                    if tx_hash:
                        print(f"Flash loan transaction hash: {tx_hash}")
                    else:
                        print("Flash loan execution failed")
                except Exception as e:
                    print(f"Error executing flash loan: {e}")
            else:
                print("Flash loan execution cancelled")
        else:
            print("No workable solution found")
    else:
        print("No arbitrage opportunity found")

if __name__ == "__main__":
    main()