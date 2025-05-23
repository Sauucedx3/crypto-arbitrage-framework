// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@aave/protocol-v2/contracts/flashloan/base/FlashLoanReceiverBase.sol";
import "@aave/protocol-v2/contracts/interfaces/ILendingPool.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";

/**
 * @title FlashLoanArbitrage
 * @dev A contract that performs arbitrage using Aave flash loans
 */
contract FlashLoanArbitrage is FlashLoanReceiverBase, Ownable {
    // Uniswap V2 Router address
    address public immutable uniswapRouter;
    
    // Events
    event ArbitrageExecuted(address indexed token, uint256 amount, uint256 profit);
    event ArbitrageFailed(address indexed token, uint256 amount, string reason);
    
    /**
     * @dev Constructor
     * @param _addressProvider The address of the Aave lending pool address provider
     * @param _uniswapRouter The address of the Uniswap V2 Router
     */
    constructor(
        ILendingPoolAddressesProvider _addressProvider,
        address _uniswapRouter
    ) FlashLoanReceiverBase(_addressProvider) {
        uniswapRouter = _uniswapRouter;
    }
    
    /**
     * @dev Executes an arbitrage operation using a flash loan
     * @param asset The address of the asset to borrow
     * @param amount The amount to borrow
     * @param params Additional parameters for the arbitrage
     */
    function executeArbitrage(
        address asset,
        uint256 amount,
        bytes calldata params
    ) external onlyOwner {
        address[] memory assets = new address[](1);
        assets[0] = asset;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;
        
        // 0 = no debt, 1 = stable, 2 = variable
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0;
        
        // Execute flash loan
        LENDING_POOL.flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            params,
            0
        );
    }
    
    /**
     * @dev This function is called after the flash loan is executed
     * @param assets The addresses of the assets borrowed
     * @param amounts The amounts borrowed
     * @param premiums The premiums (fees) to pay for the flash loan
     * @param initiator The address that initiated the flash loan
     * @param params Additional parameters for the arbitrage
     * @return A boolean indicating if the operation was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        // Ensure this is called by the lending pool
        require(msg.sender == address(LENDING_POOL), "Invalid caller");
        
        // Decode the arbitrage parameters
        (
            address[] memory path,
            uint256[] memory amountsOut
        ) = abi.decode(params, (address[], uint256[]));
        
        // Ensure the path is valid
        require(path.length >= 2, "Invalid path");
        
        // Get the borrowed asset and amount
        address asset = assets[0];
        uint256 amount = amounts[0];
        uint256 premium = premiums[0];
        uint256 amountToRepay = amount + premium;
        
        try {
            // Approve the router to spend the borrowed tokens
            IERC20(asset).approve(uniswapRouter, amount);
            
            // Execute the swap
            IUniswapV2Router02 router = IUniswapV2Router02(uniswapRouter);
            uint256[] memory swapAmounts = router.swapExactTokensForTokens(
                amount,
                amountsOut[0],
                path,
                address(this),
                block.timestamp + 300 // 5 minutes deadline
            );
            
            // Calculate profit
            uint256 finalBalance = IERC20(asset).balanceOf(address(this));
            
            // Ensure we have enough to repay the flash loan
            require(finalBalance >= amountToRepay, "Insufficient funds to repay");
            
            // Calculate profit
            uint256 profit = finalBalance - amountToRepay;
            
            // Approve the lending pool to withdraw the borrowed amount + premium
            IERC20(asset).approve(address(LENDING_POOL), amountToRepay);
            
            // Emit success event
            emit ArbitrageExecuted(asset, amount, profit);
        } catch (bytes memory reason) {
            // If the arbitrage fails, we still need to repay the flash loan
            // Transfer the required amount from the owner if necessary
            uint256 currentBalance = IERC20(asset).balanceOf(address(this));
            if (currentBalance < amountToRepay) {
                IERC20(asset).transferFrom(
                    owner(),
                    address(this),
                    amountToRepay - currentBalance
                );
            }
            
            // Approve the lending pool to withdraw the borrowed amount + premium
            IERC20(asset).approve(address(LENDING_POOL), amountToRepay);
            
            // Emit failure event
            emit ArbitrageFailed(asset, amount, string(reason));
        }
        
        return true;
    }
    
    /**
     * @dev Withdraws tokens from the contract to the owner
     * @param token The address of the token to withdraw
     */
    function withdrawToken(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        IERC20(token).transfer(owner(), balance);
    }
    
    /**
     * @dev Withdraws ETH from the contract to the owner
     */
    function withdrawETH() external onlyOwner {
        payable(owner()).transfer(address(this).balance);
    }
    
    // Allow the contract to receive ETH
    receive() external payable {}
}