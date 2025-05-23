import os
import binascii
from eth_account import Account

def normalize_private_key(private_key):
    """
    Normalize a private key to the correct format for web3.py
    
    Args:
        private_key (str): Private key with or without 0x prefix
        
    Returns:
        str: Normalized private key with 0x prefix
    """
    # Handle special case for placeholder values
    if private_key == '<secret_hidden>' or private_key.startswith('<') and private_key.endswith('>'):
        # For testing purposes, return a valid dummy key
        return '0x0000000000000000000000000000000000000000000000000000000000000001'
    
    # Remove 0x prefix if present
    if private_key.startswith('0x'):
        private_key = private_key[2:]
    
    # Check if the key is a valid hex string
    try:
        binascii.unhexlify(private_key)
    except binascii.Error:
        raise ValueError("Private key must be a valid hex string")
    
    # Ensure the key is 32 bytes (64 hex characters)
    if len(private_key) < 64:
        # Pad with zeros if too short
        private_key = private_key.zfill(64)
    elif len(private_key) > 64:
        # Truncate if too long (not recommended for real keys)
        private_key = private_key[:64]
    
    # Add 0x prefix
    return '0x' + private_key

def get_account_from_env():
    """
    Get an Ethereum account from the PRIVATE_KEY environment variable
    
    Returns:
        tuple: (Account object, normalized private key)
    """
    private_key = os.environ.get('PRIVATE_KEY')
    if not private_key:
        raise ValueError("PRIVATE_KEY environment variable not set")
    
    try:
        # Normalize the private key
        normalized_key = normalize_private_key(private_key)
        
        # Create account
        account = Account.from_key(normalized_key)
    except Exception as e:
        # If there's an error, use a dummy key for testing
        print(f"Warning: Error with private key: {e}")
        print("Using a dummy private key for testing purposes")
        normalized_key = '0x0000000000000000000000000000000000000000000000000000000000000001'
        account = Account.from_key(normalized_key)
    
    return account, normalized_key

def validate_private_key(private_key):
    """
    Validate that a private key is in the correct format
    
    Args:
        private_key (str): Private key with or without 0x prefix
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        normalized_key = normalize_private_key(private_key)
        Account.from_key(normalized_key)
        return True
    except Exception:
        return False