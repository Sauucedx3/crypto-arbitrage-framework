import os
from dotenv import load_dotenv
from crypto.flash_loan import FlashLoan
from crypto.gasless_meta import GaslessMetaTransactions

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

def test_flash_loan():
    """Test the FlashLoan class"""
    print("\nTesting FlashLoan class...")
    
    try:
        # Initialize FlashLoan
        flash_loan = FlashLoan()
        
        # Test token address lookup
        token_symbol = 'DAI'
        token_address = flash_loan.get_token_address(token_symbol)
        print(f"✅ Token address for {token_symbol}: {token_address}")
        
        print("FlashLoan class initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing FlashLoan: {e}")

def test_gasless_meta():
    """Test the GaslessMetaTransactions class"""
    print("\nTesting GaslessMetaTransactions class...")
    
    try:
        # Initialize GaslessMetaTransactions
        gasless_meta = GaslessMetaTransactions()
        
        print("GaslessMetaTransactions class initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing GaslessMetaTransactions: {e}")

if __name__ == "__main__":
    print("Testing DeFi integration components...\n")
    
    test_environment_variables()
    test_flash_loan()
    test_gasless_meta()
    
    print("\nTests completed!")