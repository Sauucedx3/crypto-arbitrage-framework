import os
import json
from typing import Dict, List, Optional, Union, Tuple
from web3 import Web3
from .flash_loan import FlashLoan
from .gasless_meta import GaslessMetaTransactions
from .path_optimizer import PathOptimizer
from .amount_optimizer import AmtOptimizer

class DeFiIntegration:
    """
    Class to integrate DeFi protocols (flash loans and gasless transactions) with the arbitrage framework
    """
    def __init__(self, 
                web3_provider: str = None, 
                biconomy_api_key: str = None,
                path_optimizer: PathOptimizer = None,
                amt_optimizer: AmtOptimizer = None):
        """
        Initialize the DeFiIntegration class
        
        Args:
            web3_provider: The Web3 provider URL (defaults to environment variable)
            biconomy_api_key: The Biconomy API key (defaults to environment variable)
            path_optimizer: An instance of PathOptimizer
            amt_optimizer: An instance of AmtOptimizer
        """
        if web3_provider is None:
            web3_provider = os.environ.get('MAINNET_RPC_URL', 'https://mainnet.infura.io/v3/your-infura-key')
        
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        self.flash_loan = FlashLoan(web3_provider)
        self.gasless_meta = GaslessMetaTransactions(web3_provider, biconomy_api_key)
        
        self.path_optimizer = path_optimizer
        self.amt_optimizer = amt_optimizer
    
    def set_optimizers(self, path_optimizer: PathOptimizer, amt_optimizer: AmtOptimizer):
        """
        Set the optimizers
        
        Args:
            path_optimizer: An instance of PathOptimizer
            amt_optimizer: An instance of AmtOptimizer
        """
        self.path_optimizer = path_optimizer
        self.amt_optimizer = amt_optimizer
    
    def calculate_flash_loan_amount(self, solution: Dict) -> Tuple[str, float]:
        """
        Calculate the optimal flash loan amount based on the arbitrage solution
        
        Args:
            solution: The arbitrage solution from AmtOptimizer
            
        Returns:
            A tuple of (token_symbol, amount)
        """
        if not solution:
            raise ValueError("No arbitrage solution provided")
        
        # Find the first trading pair to determine the starting token and amount
        first_key = next(iter(solution))
        first_trade = solution[first_key]
        
        # Extract token symbol from the first trade
        token_symbol = first_key[0].split('_')[-1]
        
        # Get the amount from the first trade
        amount = first_trade['vol']
        
        # Add a buffer for fees (e.g., 0.09% for Aave flash loans)
        amount_with_buffer = amount * 1.001
        
        return token_symbol, amount_with_buffer
    
    def prepare_arbitrage_params(self, solution: Dict) -> Dict:
        """
        Prepare parameters for the arbitrage execution
        
        Args:
            solution: The arbitrage solution from AmtOptimizer
            
        Returns:
            Parameters for the arbitrage execution
        """
        # Convert the solution to a format suitable for on-chain execution
        trades = []
        
        for key, val in solution.items():
            first_exc = key[0].split('_')[0]
            sec_exc = key[1].split('_')[0]
            
            token_from = key[0].split('_')[-1]
            token_to = key[1].split('_')[-1]
            
            # For simplicity, we're assuming all trades are on DEXes
            # In a real implementation, you'd need to handle different exchange types
            trade = {
                "exchange": first_exc,
                "tokenFrom": token_from,
                "tokenTo": token_to,
                "amount": val['vol'],
                "price": val['price'],
                "direction": val['direction']
            }
            
            trades.append(trade)
        
        return {
            "trades": trades,
            "isFlashLoan": True,
            "isGasless": True
        }
    
    def execute_arbitrage_with_flash_loan(self) -> Optional[str]:
        """
        Execute an arbitrage opportunity using a flash loan
        
        Returns:
            Transaction hash if successful, None otherwise
        """
        if not self.path_optimizer or not self.amt_optimizer:
            raise ValueError("PathOptimizer and AmtOptimizer must be set")
        
        # Find arbitrage opportunity
        self.path_optimizer.find_arbitrage()
        
        # If there is an arbitrage path, optimize the solution
        if self.path_optimizer.have_opportunity():
            self.amt_optimizer.get_solution()
            
            # If a workable trading solution is found, execute with flash loan
            if self.amt_optimizer.have_workable_solution():
                solution = self.amt_optimizer.trade_solution
                
                # Calculate flash loan amount
                token_symbol, amount = self.calculate_flash_loan_amount(solution)
                
                # Prepare arbitrage parameters
                arbitrage_params = self.prepare_arbitrage_params(solution)
                
                # Execute flash loan
                try:
                    tx_hash = self.flash_loan.execute_arbitrage_with_flash_loan(
                        token_symbol,
                        amount,
                        arbitrage_params
                    )
                    print(f"Arbitrage executed with flash loan: {tx_hash}")
                    return tx_hash
                except Exception as e:
                    print(f"Error executing flash loan: {e}")
                    return None
            else:
                print("No workable solution found")
                return None
        else:
            print("No arbitrage opportunity found")
            return None
    
    def execute_arbitrage_gasless(self) -> Optional[Dict]:
        """
        Execute an arbitrage opportunity using gasless meta transactions
        
        Returns:
            Response from Biconomy if successful, None otherwise
        """
        if not self.path_optimizer or not self.amt_optimizer:
            raise ValueError("PathOptimizer and AmtOptimizer must be set")
        
        # Find arbitrage opportunity
        self.path_optimizer.find_arbitrage()
        
        # If there is an arbitrage path, optimize the solution
        if self.path_optimizer.have_opportunity():
            self.amt_optimizer.get_solution()
            
            # If a workable trading solution is found, execute with gasless transactions
            if self.amt_optimizer.have_workable_solution():
                solution = self.amt_optimizer.trade_solution
                
                # For simplicity, we'll just execute the first trade gasless
                # In a real implementation, you'd need to handle the entire path
                first_key = next(iter(solution))
                first_trade = solution[first_key]
                
                token_from = first_key[0].split('_')[-1]
                token_to = first_key[1].split('_')[-1]
                
                # Get token addresses (simplified - in production, use a proper token registry)
                token_from_address = self.flash_loan.get_token_address(token_from)
                token_to_address = self.flash_loan.get_token_address(token_to)
                
                # QuickSwap Router on Polygon Mainnet
                exchange_contract_address = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"  # QuickSwap Router
                
                # Load GaslessArbitrage contract address from deployed contracts
                try:
                    with open(os.path.join(os.path.dirname(__file__), '../contracts/deployed_contracts.json'), 'r') as f:
                        deployed_contracts = json.load(f)
                        gasless_arbitrage_address = deployed_contracts.get('GaslessArbitrage')
                        if gasless_arbitrage_address:
                            exchange_contract_address = gasless_arbitrage_address
                except (FileNotFoundError, json.JSONDecodeError):
                    # If the file doesn't exist or is invalid, use the default QuickSwap Router
                    pass
                
                # Convert amount to wei
                amount_in_wei = int(first_trade['vol'] * (10 ** 18))  # Assuming 18 decimals
                
                try:
                    response = self.gasless_meta.execute_gasless_trade(
                        exchange_contract_address,
                        token_from_address,
                        token_to_address,
                        amount_in_wei
                    )
                    print(f"Gasless trade executed: {response}")
                    return response
                except Exception as e:
                    print(f"Error executing gasless trade: {e}")
                    return None
            else:
                print("No workable solution found")
                return None
        else:
            print("No arbitrage opportunity found")
            return None