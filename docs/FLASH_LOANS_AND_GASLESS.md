# Flash Loans and Gasless Meta Transactions

This document explains how to use flash loans and gasless meta transactions in the crypto arbitrage framework.

## Flash Loans

Flash loans allow you to borrow assets without collateral, as long as you return the borrowed amount (plus fees) within the same transaction. This is useful for arbitrage, as it allows you to execute trades with more capital than you have.

### How Flash Loans Work

1. You borrow a large amount of tokens from a lending protocol (e.g., Aave)
2. You use these tokens to execute an arbitrage opportunity
3. You return the borrowed tokens plus a fee (typically 0.09%) to the lending protocol
4. All of this happens in a single transaction

### Using Flash Loans in the Framework

The framework provides a `FlashLoan` class that handles flash loan operations. Here's how to use it:

```python
from crypto.flash_loan import FlashLoan

# Initialize the flash loan
flash_loan = FlashLoan(web3_provider='https://polygon-rpc.com')

# Execute a flash loan
tx_hash = flash_loan.execute_arbitrage_with_flash_loan(
    token_symbol='USDC',
    amount=10000,  # 10,000 USDC
    arbitrage_params={
        'trades': [
            {
                'exchange': 'quickswap',
                'tokenFrom': 'USDC',
                'tokenTo': 'WETH',
                'amount': 10000,
                'price': 0.0005,
                'direction': 'buy'
            },
            {
                'exchange': 'sushiswap',
                'tokenFrom': 'WETH',
                'tokenTo': 'USDC',
                'amount': 5,
                'price': 2100,
                'direction': 'sell'
            }
        ],
        'isFlashLoan': True,
        'isGasless': False
    }
)

print(f"Flash loan transaction hash: {tx_hash}")
```

### Supported Tokens

The framework supports the following tokens on Polygon:

- MATIC (Native token)
- WMATIC (Wrapped MATIC)
- WETH (Wrapped Ethereum)
- DAI (Dai Stablecoin)
- USDC (USD Coin)
- USDT (Tether)
- WBTC (Wrapped Bitcoin)

## Gasless Meta Transactions

Gasless meta transactions allow you to execute transactions without paying gas fees. Instead, a relayer (e.g., Biconomy) pays the gas fees for you. This is useful for users who don't have MATIC to pay for gas.

### How Gasless Meta Transactions Work

1. You sign a message with your private key
2. The message contains the transaction data you want to execute
3. A relayer (e.g., Biconomy) submits the transaction to the blockchain and pays the gas fees
4. The transaction is executed as if you had submitted it yourself

### Using Gasless Meta Transactions in the Framework

The framework provides a `GaslessMetaTransactions` class that handles gasless meta transactions. Here's how to use it:

```python
from crypto.gasless_meta import GaslessMetaTransactions

# Initialize the gasless meta transactions
gasless_meta = GaslessMetaTransactions(
    web3_provider='https://polygon-rpc.com',
    biconomy_api_key='your-biconomy-api-key'
)

# Execute a gasless trade
response = gasless_meta.execute_gasless_trade(
    exchange_contract_address='0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',  # QuickSwap Router
    token_from='0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
    token_to='0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
    amount=10000000000  # 10 USDC (with 6 decimals)
)

print(f"Gasless transaction response: {response}")
```

### Requirements for Gasless Meta Transactions

To use gasless meta transactions, you need:

1. A Biconomy API key
2. A deployed contract that supports meta transactions (e.g., GaslessArbitrage.sol)
3. Tokens to trade

## Combining Flash Loans and Gasless Meta Transactions

You can combine flash loans and gasless meta transactions to execute arbitrage without paying gas fees and with more capital than you have. The framework provides a `DeFiIntegration` class that handles this integration.

```python
from crypto.defi_integration import DeFiIntegration
from crypto.path_optimizer import PathOptimizer
from crypto.amount_optimizer import AmtOptimizer

# Initialize the DeFi integration
defi_integration = DeFiIntegration(
    web3_provider='https://polygon-rpc.com',
    biconomy_api_key='your-biconomy-api-key',
    path_optimizer=path_optimizer,
    amt_optimizer=amt_optimizer
)

# Execute arbitrage with flash loan
tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
print(f"Flash loan transaction hash: {tx_hash}")

# Execute arbitrage with gasless meta transactions
response = defi_integration.execute_arbitrage_gasless()
print(f"Gasless transaction response: {response}")
```

## Deploying the Contracts

The framework provides a `deploy_contracts.py` script that deploys the flash loan and gasless meta transaction contracts to the Polygon network.

```bash
# Set environment variables
export MAINNET_RPC_URL=https://polygon-rpc.com
export PRIVATE_KEY=your-private-key
export BICONOMY_API_KEY=your-biconomy-api-key

# Deploy the contracts
python -m crypto.deploy_contracts
```

This will deploy the `FlashLoanArbitrage` and `GaslessArbitrage` contracts to the Polygon network and save the contract addresses to `contracts/deployed_contracts.json`.

## Testing the Integration

The framework provides a `test_polygon.py` script that tests the Polygon integration.

```bash
# Set environment variables
export MAINNET_RPC_URL=https://polygon-rpc.com
export PRIVATE_KEY=your-private-key
export BICONOMY_API_KEY=your-biconomy-api-key

# Run the test
python test_polygon.py
```

This will test the connection to the Polygon network, the account setup, and the Aave and QuickSwap contracts.

## Example Usage

The framework provides an example script `examples/polygon_example.py` that demonstrates how to use flash loans and gasless meta transactions for arbitrage.

```bash
# Set environment variables
export MAINNET_RPC_URL=https://polygon-rpc.com
export PRIVATE_KEY=your-private-key
export BICONOMY_API_KEY=your-biconomy-api-key

# Run the example
python examples/polygon_example.py
```

This will find arbitrage opportunities on Polygon and execute them using flash loans and gasless meta transactions.