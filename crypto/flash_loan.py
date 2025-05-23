import os
import json
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount
from typing import Dict, List, Optional, Union, Tuple
from crypto.key_utils import normalize_private_key

# ABI for Aave V2 Flash Loan
AAVE_LENDING_POOL_ABI = json.loads('''
[
    {
        "inputs": [
            {
                "internalType": "address[]",
                "name": "assets",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "premiums",
                "type": "uint256[]"
            },
            {
                "internalType": "address",
                "name": "initiator",
                "type": "address"
            },
            {
                "internalType": "bytes",
                "name": "params",
                "type": "bytes"
            }
        ],
        "name": "executeOperation",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address[]",
                "name": "assets",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "modes",
                "type": "uint256[]"
            },
            {
                "internalType": "address",
                "name": "onBehalfOf",
                "type": "address"
            },
            {
                "internalType": "bytes",
                "name": "params",
                "type": "bytes"
            },
            {
                "internalType": "uint16",
                "name": "referralCode",
                "type": "uint16"
            }
        ],
        "name": "flashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
''')

# Common token addresses on Polygon mainnet
TOKEN_ADDRESSES = {
    'MATIC': '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE',  # Special address for MATIC
    'WMATIC': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
    'WETH': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',
    'DAI': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063',
    'USDC': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
    'USDT': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
    'WBTC': '0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6'
}

# Aave V2 addresses on Polygon mainnet
AAVE_LENDING_POOL_ADDRESS = '0x8dFf5E27EA6b7AC08EbFdf9eB090F32ee9a30fcf'
AAVE_LENDING_POOL_ADDRESS_PROVIDER = '0xd05e3E715d945B59290df0ae8eF85c1BdB684744'

class FlashLoan:
    """
    Class to handle flash loan operations for arbitrage
    """
    def __init__(self, web3_provider: str = None):
        """
        Initialize the FlashLoan class
        
        Args:
            web3_provider: The Web3 provider URL (defaults to environment variable)
        """
        if web3_provider is None:
            web3_provider = os.environ.get('MAINNET_RPC_URL', 'https://mainnet.infura.io/v3/your-infura-key')
        
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        self.lending_pool = self.w3.eth.contract(
            address=self.w3.to_checksum_address(AAVE_LENDING_POOL_ADDRESS),
            abi=AAVE_LENDING_POOL_ABI
        )
        
        # Load private key from environment variable
        private_key = os.environ.get('PRIVATE_KEY')
        if private_key:
            # Handle private key format (with or without 0x prefix)
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            self.account: LocalAccount = Account.from_key(private_key)
            print(f"Account loaded: {self.account.address}")
        else:
            self.account = None
            print("Warning: No private key provided. Set PRIVATE_KEY environment variable.")
    
    def execute_flash_loan(self, 
                          token_address: str, 
                          amount: int, 
                          params: bytes = b'',
                          mode: int = 0) -> str:
        """
        Execute a flash loan
        
        Args:
            token_address: The address of the token to borrow
            amount: The amount to borrow (in wei)
            params: Additional parameters to pass to the executeOperation function
            mode: Flash loan mode (0 = no debt, 1 = stable, 2 = variable)
            
        Returns:
            Transaction hash
        """
        if not self.account:
            raise ValueError("No account available. Set PRIVATE_KEY environment variable.")
        
        # Prepare flash loan parameters
        assets = [self.w3.to_checksum_address(token_address)]
        amounts = [amount]
        modes = [mode]  # 0 = no debt (flash loan), 1 = stable, 2 = variable
        on_behalf_of = self.account.address
        referral_code = 0
        
        # Build transaction
        tx = self.lending_pool.functions.flashLoan(
            assets,
            amounts,
            modes,
            on_behalf_of,
            params,
            referral_code
        ).build_transaction({
            'from': self.account.address,
            'gas': 3000000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
        })
        
        # Sign and send transaction
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"Flash loan transaction sent: {tx_hash.hex()}")
        return tx_hash.hex()
    
    def get_token_address(self, symbol: str) -> str:
        """
        Get the address of a token by its symbol
        
        Args:
            symbol: The token symbol (e.g., 'ETH', 'DAI')
            
        Returns:
            The token address
        """
        symbol = symbol.upper()
        if symbol in TOKEN_ADDRESSES:
            return TOKEN_ADDRESSES[symbol]
        else:
            raise ValueError(f"Token symbol {symbol} not found in known tokens")
    
    def execute_arbitrage_with_flash_loan(self, 
                                         token_symbol: str, 
                                         amount: float,
                                         arbitrage_params: Dict) -> str:
        """
        Execute an arbitrage opportunity using a flash loan
        
        Args:
            token_symbol: The symbol of the token to borrow (e.g., 'DAI')
            amount: The amount to borrow (in token units, not wei)
            arbitrage_params: Parameters for the arbitrage execution
            
        Returns:
            Transaction hash
        """
        token_address = self.get_token_address(token_symbol)
        
        # Convert amount to wei based on token decimals
        decimals = 18  # Default for most ERC20 tokens
        if token_symbol == 'USDC' or token_symbol == 'USDT':
            decimals = 6
        
        amount_in_wei = int(amount * (10 ** decimals))
        
        # Encode arbitrage parameters
        encoded_params = self.w3.eth.abi.encode_abi(
            ['address', 'uint256', 'bytes'],
            [token_address, amount_in_wei, self.w3.to_hex(arbitrage_params)]
        )
        
        # Execute flash loan
        return self.execute_flash_loan(token_address, amount_in_wei, encoded_params)