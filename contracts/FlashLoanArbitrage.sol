// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@aave/protocol-v2/contracts/flashloan/base/FlashLoanReceiverBase.sol";
import "@aave/protocol-v2/contracts/interfaces/ILendingPoolAddressesProvider.sol";
import "@aave/protocol-v2/contracts/interfaces/ILendingPool.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";

/**
 * @title FlashLoanArbitrage
 * @dev A contract that performs arbitrage using flash loans from Aave V2
 */
contract FlashLoanArbitrage is FlashLoanReceiverBase, Ownable {
    // QuickSwap Router address on Polygon
    address public constant QUICKSWAP_ROUTER = 0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff;
    
    // Event emitted when a flash loan is executed
    event FlashLoanExecuted(address indexed token, uint256 amount, uint256 profit);
    
    // Event emitted when tokens are swapped
    event TokensSwapped(address indexed fromToken, address indexed toToken, uint256 amountIn, uint256 amountOut);
    
    /**
     * @dev Constructor
     * @param _addressProvider The address of the Aave V2 LendingPoolAddressesProvider
     */
    constructor(address _addressProvider) FlashLoanReceiverBase(ILendingPoolAddressesProvider(_addressProvider)) {
        // Initialize the contract
    }
    
    /**
     * @dev Execute a flash loan
     * @param _token The address of the token to borrow
     * @param _amount The amount to borrow
     * @param _path An array of token addresses representing the swap path
     */
    function executeFlashLoan(address _token, uint256 _amount, address[] calldata _path) external onlyOwner {
        address[] memory assets = new address[](1);
        uint256[] memory amounts = new uint256[](1);
        uint256[] memory modes = new uint256[](1);
        
        assets[0] = _token;
        amounts[0] = _amount;
        modes[0] = 0; // 0 = no debt, 1 = stable, 2 = variable
        
        // Encode the swap path as bytes
        bytes memory params = abi.encode(_path);
        
        // Request the flash loan from Aave
        ILendingPool(LENDING_POOL).flashLoan(
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
     * @dev This function is called after the flash loan is received
     * @param assets The addresses of the assets being flash-borrowed
     * @param amounts The amounts of the assets being flash-borrowed
     * @param premiums The fee to be paid for each asset
     * @param initiator The address that initiated the flash loan
     * @param params Encoded parameters for the arbitrage strategy
     * @return A boolean indicating if the execution was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        // Ensure the caller is the LendingPool
        require(msg.sender == LENDING_POOL, "Invalid caller");
        
        // Decode the swap path from params
        address[] memory path = abi.decode(params, (address[]));
        
        // Ensure the path is valid
        require(path.length >= 2, "Invalid path");
        require(path[0] == assets[0], "Path must start with borrowed asset");
        require(path[path.length - 1] == assets[0], "Path must end with borrowed asset");
        
        // Get the borrowed amount
        uint256 borrowedAmount = amounts[0];
        
        // Calculate the amount to be repaid
        uint256 amountToRepay = borrowedAmount + premiums[0];
        
        // Approve the router to spend the borrowed tokens
        IERC20(assets[0]).approve(QUICKSWAP_ROUTER, borrowedAmount);
        
        // Execute the arbitrage swaps
        uint256 initialBalance = IERC20(assets[0]).balanceOf(address(this));
        executeArbitrageSwaps(path, borrowedAmount);
        uint256 finalBalance = IERC20(assets[0]).balanceOf(address(this));
        
        // Calculate profit
        uint256 profit = 0;
        if (finalBalance > amountToRepay) {
            profit = finalBalance - amountToRepay;
        }
        
        // Approve the LendingPool to pull the owed amount
        IERC20(assets[0]).approve(LENDING_POOL, amountToRepay);
        
        // Emit event
        emit FlashLoanExecuted(assets[0], borrowedAmount, profit);
        
        // Return true to indicate success
        return true;
    }
    
    /**
     * @dev Execute a series of token swaps for arbitrage
     * @param _path The path of token addresses to swap through
     * @param _amountIn The initial amount to swap
     * @return The final amount received
     */
    function executeArbitrageSwaps(address[] memory _path, uint256 _amountIn) internal returns (uint256) {
        uint256 currentAmountIn = _amountIn;
        
        // Execute swaps along the path
        for (uint256 i = 0; i < _path.length - 1; i++) {
            address fromToken = _path[i];
            address toToken = _path[i + 1];
            
            // Create a temporary path for this swap
            address[] memory swapPath = new address[](2);
            swapPath[0] = fromToken;
            swapPath[1] = toToken;
            
            // Approve the router to spend the tokens
            IERC20(fromToken).approve(QUICKSWAP_ROUTER, currentAmountIn);
            
            // Execute the swap
            uint256[] memory amounts = IUniswapV2Router02(QUICKSWAP_ROUTER).swapExactTokensForTokens(
                currentAmountIn,
                0, // Accept any amount of output tokens
                swapPath,
                address(this),
                block.timestamp + 300 // 5 minute deadline
            );
            
            // Update the amount for the next swap
            currentAmountIn = amounts[amounts.length - 1];
            
            // Emit event
            emit TokensSwapped(fromToken, toToken, amounts[0], amounts[1]);
        }
        
        return currentAmountIn;
    }
    
    /**
     * @dev Withdraw tokens from the contract
     * @param _token The address of the token to withdraw
     * @param _amount The amount to withdraw
     */
    function withdrawToken(address _token, uint256 _amount) external onlyOwner {
        IERC20(_token).transfer(owner(), _amount);
    }
    
    /**
     * @dev Withdraw all tokens of a specific type from the contract
     * @param _token The address of the token to withdraw
     */
    function withdrawAllToken(address _token) external onlyOwner {
        uint256 balance = IERC20(_token).balanceOf(address(this));
        IERC20(_token).transfer(owner(), balance);
    }
    
    /**
     * @dev Withdraw native currency (MATIC) from the contract
     * @param _amount The amount to withdraw
     */
    function withdrawMATIC(uint256 _amount) external onlyOwner {
        payable(owner()).transfer(_amount);
    }
    
    /**
     * @dev Withdraw all native currency (MATIC) from the contract
     */
    function withdrawAllMATIC() external onlyOwner {
        payable(owner()).transfer(address(this).balance);
    }
    
    /**
     * @dev Fallback function to receive MATIC
     */
    receive() external payable {}
}