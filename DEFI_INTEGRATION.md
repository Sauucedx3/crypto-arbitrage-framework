# DeFi Integration: Flash Loans and Gasless Meta Transactions on Polygon

This extension to the Crypto Arbitrage Framework adds support for flash loans and gasless meta transactions on Polygon Mainnet, enabling more advanced arbitrage strategies with lower gas costs.

## Flash Loans

Flash loans allow you to borrow assets without collateral, as long as you repay the loan within the same transaction. This enables arbitrage with minimal capital requirements.

### Features

- Integration with Aave V2 flash loans on Polygon
- Smart contract for on-chain arbitrage execution
- Python interface for initiating flash loans
- Support for multiple tokens (MATIC, WMATIC, WETH, DAI, USDC, USDT, WBTC)
- Lower gas costs compared to Ethereum mainnet

### Usage

```python
from crypto.flash_loan import FlashLoan
from crypto.defi_integration import DeFiIntegration

# Initialize the DeFi integration
defi_integration = DeFiIntegration(
    web3_provider=os.environ.get('MAINNET_RPC_URL'),
    path_optimizer=path_optimizer,
    amt_optimizer=amt_optimizer
)

# Execute arbitrage with flash loan
tx_hash = defi_integration.execute_arbitrage_with_flash_loan()
```

## Gasless Meta Transactions

Gasless meta transactions allow users to execute transactions without paying for gas, by having a relayer submit the transaction on their behalf.

### Features

- Integration with Biconomy for gasless transactions
- Smart contract for on-chain execution
- Support for EIP-712 signatures
- Python interface for creating and sending meta transactions

### Usage

```python
from crypto.gasless_meta import GaslessMetaTransactions
from crypto.defi_integration import DeFiIntegration

# Initialize the DeFi integration
defi_integration = DeFiIntegration(
    web3_provider=os.environ.get('MAINNET_RPC_URL'),
    biconomy_api_key=os.environ.get('BICONOMY_API_KEY'),
    path_optimizer=path_optimizer,
    amt_optimizer=amt_optimizer
)

# Execute arbitrage with gasless transactions
response = defi_integration.execute_arbitrage_gasless()
```

## Smart Contracts

Two smart contracts are included:

1. **FlashLoanArbitrage.sol**: A contract that performs arbitrage using Aave flash loans on Polygon
2. **GaslessMetaTransactions.sol**: A contract that enables gasless meta transactions for arbitrage on Polygon

### Deployment

To deploy the smart contracts on Polygon Mainnet:

1. Set the required environment variables:
   - `MAINNET_RPC_URL`: Polygon RPC URL (e.g., https://polygon-rpc.com)
   - `PRIVATE_KEY`: Private key for deployment

2. Run the deployment script:
   ```
   python -m crypto.deploy_contracts
   ```

The deployment script will automatically use the correct contract addresses for Aave and QuickSwap on Polygon.

## Environment Variables

The following environment variables are required:

- `MAINNET_RPC_URL`: Polygon RPC URL (e.g., https://polygon-rpc.com)
- `BICONOMY_API_KEY`: API key for Biconomy
- `PRIVATE_KEY`: Private key for signing transactions

Note: Despite the name `MAINNET_RPC_URL`, this should be set to a Polygon RPC URL for this implementation.

## Dependencies

- web3>=5.23.0
- eth-account>=0.5.6
- requests>=2.25.1
- py-solc-x>=1.1.1
- python-dotenv>=0.19.0

## Example

See `crypto/defi_main.py` for a complete example of how to use flash loans and gasless meta transactions with the arbitrage framework.

## Limitations

- Flash loans require a profitable arbitrage opportunity to cover the flash loan fee (0.09% for Aave V2)
- Gasless meta transactions require registration with Biconomy and setting up a relayer
- Smart contracts need to be deployed on the Ethereum network (or other supported networks)