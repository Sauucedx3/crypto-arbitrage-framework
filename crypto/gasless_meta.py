import os
import json
import time
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data
from typing import Dict, List, Optional, Union, Tuple
import requests
from crypto.key_utils import normalize_private_key

class GaslessMetaTransactions:
    """
    Class to handle gasless meta transactions using Biconomy
    """
    def __init__(self, web3_provider: str = None, biconomy_api_key: str = None):
        """
        Initialize the GaslessMetaTransactions class
        
        Args:
            web3_provider: The Web3 provider URL (defaults to environment variable)
            biconomy_api_key: The Biconomy API key (defaults to environment variable)
        """
        if web3_provider is None:
            web3_provider = os.environ.get('MAINNET_RPC_URL', 'https://mainnet.infura.io/v3/your-infura-key')
        
        if biconomy_api_key is None:
            biconomy_api_key = os.environ.get('BICONOMY_API_KEY')
            if not biconomy_api_key:
                print("Warning: No Biconomy API key provided. Set BICONOMY_API_KEY environment variable.")
        
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        self.biconomy_api_key = biconomy_api_key
        
        # Load private key from environment variable
        private_key = os.environ.get('PRIVATE_KEY')
        if private_key:
            # Normalize the private key
            normalized_key = normalize_private_key(private_key)
            self.account = Account.from_key(normalized_key)
            self.private_key = normalized_key
            print(f"Account loaded: {self.account.address}")
        else:
            self.account = None
            self.private_key = None
            print("Warning: No private key provided. Set PRIVATE_KEY environment variable.")
    
    def get_contract_abi(self, contract_address: str) -> List:
        """
        Get the ABI for a contract from Etherscan
        
        Args:
            contract_address: The contract address
            
        Returns:
            The contract ABI
        """
        # This is a simplified version - in production, you'd want to cache this
        # and handle rate limits, errors, etc.
        etherscan_api_key = os.environ.get('ETHERSCAN_API_KEY', '')
        url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={contract_address}&apikey={etherscan_api_key}"
        response = requests.get(url)
        data = response.json()
        
        if data['status'] == '1':
            return json.loads(data['result'])
        else:
            raise ValueError(f"Failed to get ABI: {data['message']}")
    
    def prepare_meta_transaction(self, 
                               contract_address: str, 
                               function_name: str, 
                               function_args: List,
                               abi: List = None) -> Dict:
        """
        Prepare a meta transaction
        
        Args:
            contract_address: The contract address
            function_name: The function name to call
            function_args: The function arguments
            abi: The contract ABI (optional, will be fetched if not provided)
            
        Returns:
            The prepared meta transaction data
        """
        if not self.account:
            raise ValueError("No account available. Set PRIVATE_KEY environment variable.")
        
        # Get ABI if not provided
        if abi is None:
            abi = self.get_contract_abi(contract_address)
        
        # Create contract instance
        contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(contract_address),
            abi=abi
        )
        
        # Get function data
        function_data = contract.encodeABI(fn_name=function_name, args=function_args)
        
        # Prepare meta transaction data
        nonce = int(time.time())  # Simple nonce, in production use a proper nonce management
        
        meta_tx_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                "MetaTransaction": [
                    {"name": "nonce", "type": "uint256"},
                    {"name": "from", "type": "address"},
                    {"name": "functionSignature", "type": "bytes"}
                ]
            },
            "domain": {
                "name": "Your Contract Name",  # Replace with actual contract name
                "version": "1",
                "chainId": self.w3.eth.chain_id,
                "verifyingContract": contract_address
            },
            "primaryType": "MetaTransaction",
            "message": {
                "nonce": nonce,
                "from": self.account.address,
                "functionSignature": function_data
            }
        }
        
        return meta_tx_data
    
    def sign_meta_transaction(self, meta_tx_data: Dict) -> str:
        """
        Sign a meta transaction
        
        Args:
            meta_tx_data: The meta transaction data
            
        Returns:
            The signature
        """
        if not self.account:
            raise ValueError("No account available. Set PRIVATE_KEY environment variable.")
        
        # Sign the meta transaction
        structured_data = encode_typed_data(meta_tx_data)
        signed = self.account.sign_message(structured_data)
        
        return signed.signature.hex()
    
    def send_meta_transaction(self, 
                            contract_address: str, 
                            function_name: str, 
                            function_args: List,
                            abi: List = None) -> Dict:
        """
        Send a meta transaction via Biconomy
        
        Args:
            contract_address: The contract address
            function_name: The function name to call
            function_args: The function arguments
            abi: The contract ABI (optional, will be fetched if not provided)
            
        Returns:
            The response from Biconomy
        """
        if not self.biconomy_api_key:
            raise ValueError("No Biconomy API key available. Set BICONOMY_API_KEY environment variable.")
        
        # Prepare meta transaction
        meta_tx_data = self.prepare_meta_transaction(
            contract_address, 
            function_name, 
            function_args,
            abi
        )
        
        # Sign meta transaction
        signature = self.sign_meta_transaction(meta_tx_data)
        
        # Get function data
        if abi is None:
            abi = self.get_contract_abi(contract_address)
        
        contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(contract_address),
            abi=abi
        )
        function_data = contract.encodeABI(fn_name=function_name, args=function_args)
        
        # Prepare request to Biconomy
        url = "https://api.biconomy.io/api/v2/meta-tx/native"
        headers = {
            "x-api-key": self.biconomy_api_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "to": contract_address,
            "from": self.account.address,
            "apiId": "your-api-id",  # Replace with your Biconomy API ID
            "params": [
                self.account.address,
                function_data,
                signature
            ],
            "signatureType": "EIP712_SIGN"
        }
        
        # Send request to Biconomy
        response = requests.post(url, headers=headers, json=data)
        return response.json()
    
    def execute_gasless_trade(self, 
                            exchange_contract_address: str, 
                            token_from: str, 
                            token_to: str, 
                            amount: int) -> Dict:
        """
        Execute a gasless trade
        
        Args:
            exchange_contract_address: The exchange contract address
            token_from: The address of the token to sell
            token_to: The address of the token to buy
            amount: The amount to sell (in wei)
            
        Returns:
            The response from Biconomy
        """
        # Example function for a swap on a DEX
        function_name = "swap"
        function_args = [
            self.w3.to_checksum_address(token_from),
            self.w3.to_checksum_address(token_to),
            amount,
            0,  # Min amount out (in production, calculate this properly)
            self.account.address,  # Recipient
            int(time.time()) + 3600  # Deadline (1 hour from now)
        ]
        
        return self.send_meta_transaction(
            exchange_contract_address,
            function_name,
            function_args
        )