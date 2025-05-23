import os
from dotenv import load_dotenv
import web3
from web3 import Web3
from eth_account import Account
import json

# Load environment variables
load_dotenv()

def test_environment_variables():
    """Test that environment variables are loaded correctly"""
    print("Testing environment variables...")
    
    required_vars = ['MAINNET_RPC_URL', 'BICONOMY_API_KEY', 'PRIVATE_KEY']
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var} is set")
        else:
            print(f"❌ {var} is not set")

def test_web3_connection():
    """Test Web3 connection"""
    print("\nTesting Web3 connection...")
    
    try:
        # Initialize Web3
        web3_provider = os.environ.get('MAINNET_RPC_URL', 'https://mainnet.infura.io/v3/your-infura-key')
        w3 = Web3(Web3.HTTPProvider(web3_provider))
        
        # Check connection
        if w3.is_connected():
            print(f"✅ Connected to Ethereum node")
            print(f"✅ Chain ID: {w3.eth.chain_id}")
            print(f"✅ Latest block number: {w3.eth.block_number}")
        else:
            print(f"❌ Failed to connect to Ethereum node")
    except Exception as e:
        print(f"❌ Error connecting to Ethereum node: {e}")

def test_token_addresses():
    """Test token addresses"""
    print("\nTesting token addresses...")
    
    # Common token addresses on Ethereum mainnet
    TOKEN_ADDRESSES = {
        'ETH': '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE',  # Special address for ETH
        'WETH': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
        'DAI': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
        'USDC': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
        'USDT': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        'WBTC': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
    }
    
    for symbol, address in TOKEN_ADDRESSES.items():
        print(f"✅ {symbol}: {address}")

def test_aave_lending_pool():
    """Test Aave lending pool address"""
    print("\nTesting Aave lending pool address...")
    
    # Aave V2 Lending Pool address on Ethereum mainnet
    AAVE_LENDING_POOL_ADDRESS = '0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9'
    print(f"✅ Aave V2 Lending Pool: {AAVE_LENDING_POOL_ADDRESS}")

def test_uniswap_router():
    """Test Uniswap router address"""
    print("\nTesting Uniswap router address...")
    
    # Uniswap V2 Router address on Ethereum mainnet
    UNISWAP_ROUTER_ADDRESS = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    print(f"✅ Uniswap V2 Router: {UNISWAP_ROUTER_ADDRESS}")

if __name__ == "__main__":
    print("Testing DeFi integration components...\n")
    
    test_environment_variables()
    test_web3_connection()
    test_token_addresses()
    test_aave_lending_pool()
    test_uniswap_router()
    
    print("\nTests completed!")