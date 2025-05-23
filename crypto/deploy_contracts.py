import os
import json
from web3 import Web3
from eth_account import Account
from solcx import compile_source, install_solc
from crypto.key_utils import normalize_private_key

# Install solc compiler
install_solc('0.8.10')

def compile_contract(contract_path):
    """
    Compile a Solidity contract
    
    Args:
        contract_path: Path to the contract file
        
    Returns:
        Tuple of (abi, bytecode)
    """
    with open(contract_path, 'r') as file:
        contract_source = file.read()
    
    # Compile the contract
    compiled_sol = compile_source(
        contract_source,
        output_values=['abi', 'bin'],
        solc_version='0.8.10'
    )
    
    # Extract the contract interface
    contract_id, contract_interface = compiled_sol.popitem()
    abi = contract_interface['abi']
    bytecode = contract_interface['bin']
    
    return abi, bytecode

def deploy_contract(w3, abi, bytecode, constructor_args, private_key):
    """
    Deploy a contract
    
    Args:
        w3: Web3 instance
        abi: Contract ABI
        bytecode: Contract bytecode
        constructor_args: Constructor arguments
        private_key: Private key for the deployer account
        
    Returns:
        Deployed contract address
    """
    # Create a contract factory
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Normalize the private key
    normalized_key = normalize_private_key(private_key)
    
    # Get the account from the private key
    account = Account.from_key(normalized_key)
    
    # Build the transaction
    transaction = {
        'from': account.address,
        'gas': 4000000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(account.address),
    }
    
    # Add constructor arguments if provided
    if constructor_args:
        transaction['data'] = contract.constructor(*constructor_args).data_in_transaction
    else:
        transaction['data'] = contract.constructor().data_in_transaction
    
    # Sign the transaction
    signed_txn = account.sign_transaction(transaction)
    
    # Send the transaction
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    
    # Wait for the transaction to be mined
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    # Get the contract address
    contract_address = tx_receipt.contractAddress
    
    return contract_address

def main():
    # Get environment variables
    rpc_url = os.environ.get('MAINNET_RPC_URL')
    private_key = os.environ.get('PRIVATE_KEY')
    
    if not rpc_url or not private_key:
        print("Please set MAINNET_RPC_URL and PRIVATE_KEY environment variables")
        return
    
    # Connect to Polygon
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    # Check connection
    if not w3.is_connected():
        print("Failed to connect to Polygon node")
        return
    
    # Get the account from the private key
    normalized_key = normalize_private_key(private_key)
    account = Account.from_key(normalized_key)
    print(f"Deploying contracts from account: {account.address}")
    print(f"Connected to network with Chain ID: {w3.eth.chain_id}")
    
    # Compile and deploy FlashLoanArbitrage contract
    print("Compiling FlashLoanArbitrage contract...")
    flash_loan_path = os.path.join(os.path.dirname(__file__), '../contracts/FlashLoanArbitrage.sol')
    flash_loan_abi, flash_loan_bytecode = compile_contract(flash_loan_path)
    
    # Aave Lending Pool Address Provider (Polygon Mainnet)
    aave_address_provider = '0xd05e3E715d945B59290df0ae8eF85c1BdB684744'
    
    # QuickSwap Router (Polygon Mainnet) - Uniswap V2 fork on Polygon
    quickswap_router = '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff'
    
    print("Deploying FlashLoanArbitrage contract...")
    flash_loan_address = deploy_contract(
        w3,
        flash_loan_abi,
        flash_loan_bytecode,
        [aave_address_provider, quickswap_router],
        private_key
    )
    print(f"FlashLoanArbitrage deployed at: {flash_loan_address}")
    
    # Save the contract ABI and address
    contracts_dir = os.path.join(os.path.dirname(__file__), '../contracts')
    os.makedirs(contracts_dir, exist_ok=True)
    
    with open(os.path.join(contracts_dir, 'FlashLoanArbitrage.json'), 'w') as f:
        json.dump({
            'abi': flash_loan_abi,
            'address': flash_loan_address,
            'network': 'polygon',
            'chain_id': w3.eth.chain_id
        }, f, indent=2)
    
    # Compile and deploy GaslessArbitrage contract
    print("Compiling GaslessArbitrage contract...")
    gasless_path = os.path.join(os.path.dirname(__file__), '../contracts/GaslessArbitrage.sol')
    gasless_abi, gasless_bytecode = compile_contract(gasless_path)
    
    print("Deploying GaslessArbitrage contract...")
    gasless_address = deploy_contract(
        w3,
        gasless_abi,
        gasless_bytecode,
        [],  # No constructor arguments needed
        private_key
    )
    print(f"GaslessArbitrage deployed at: {gasless_address}")
    
    # Save the contract ABI and address
    with open(os.path.join(contracts_dir, 'GaslessArbitrage.json'), 'w') as f:
        json.dump({
            'abi': gasless_abi,
            'address': gasless_address,
            'network': 'polygon',
            'chain_id': w3.eth.chain_id
        }, f, indent=2)
        
    # Save all deployed contract addresses in one file
    with open(os.path.join(contracts_dir, 'deployed_contracts.json'), 'w') as f:
        json.dump({
            'FlashLoanArbitrage': flash_loan_address,
            'GaslessArbitrage': gasless_address,
            'network': 'polygon',
            'chain_id': w3.eth.chain_id
        }, f, indent=2)
    
    print("Deployment completed successfully on Polygon Mainnet!")

if __name__ == "__main__":
    main()