// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";

/**
 * @title GaslessArbitrage
 * @dev A contract that performs arbitrage using meta transactions (gasless)
 */
contract GaslessArbitrage is Ownable {
    using ECDSA for bytes32;
    
    // QuickSwap Router address on Polygon
    address public constant QUICKSWAP_ROUTER = 0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff;
    
    // Mapping of used nonces
    mapping(address => mapping(uint256 => bool)) public usedNonces;
    
    // Event emitted when a meta transaction is executed
    event MetaTransactionExecuted(address indexed user, address indexed relayer, bytes functionSignature);
    
    // Event emitted when tokens are swapped
    event TokensSwapped(address indexed fromToken, address indexed toToken, uint256 amountIn, uint256 amountOut);
    
    // Event emitted when an arbitrage is executed
    event ArbitrageExecuted(address indexed user, address[] path, uint256 amountIn, uint256 amountOut, uint256 profit);
    
    /**
     * @dev Execute a meta transaction
     * @param userAddress The address of the user who signed the transaction
     * @param functionSignature The function to call
     * @param sigR The R component of the signature
     * @param sigS The S component of the signature
     * @param sigV The V component of the signature
     * @param nonce The nonce to prevent replay attacks
     */
    function executeMetaTransaction(
        address userAddress,
        bytes memory functionSignature,
        bytes32 sigR,
        bytes32 sigS,
        uint8 sigV,
        uint256 nonce
    ) public returns (bytes memory) {
        // Verify the nonce hasn't been used
        require(!usedNonces[userAddress][nonce], "Nonce already used");
        
        // Mark the nonce as used
        usedNonces[userAddress][nonce] = true;
        
        // Recreate the message that was signed
        bytes32 messageHash = keccak256(
            abi.encodePacked(
                address(this),
                userAddress,
                functionSignature,
                nonce
            )
        );
        
        // Convert to an Ethereum signed message
        bytes32 ethSignedMessageHash = messageHash.toEthSignedMessageHash();
        
        // Recover the signer's address
        address signer = ethSignedMessageHash.recover(sigV, sigR, sigS);
        
        // Verify the signer is the user or an authorized relayer
        require(signer == userAddress, "Invalid signature");
        
        // Execute the function
        (bool success, bytes memory returnData) = address(this).call(
            abi.encodePacked(functionSignature, userAddress)
        );
        
        // Revert if the call failed
        require(success, "Function call failed");
        
        // Emit event
        emit MetaTransactionExecuted(userAddress, msg.sender, functionSignature);
        
        return returnData;
    }
    
    /**
     * @dev Execute an arbitrage trade
     * @param _path The path of token addresses to swap through
     * @param _amountIn The initial amount to swap
     * @param _minAmountOut The minimum amount to receive at the end
     * @param _deadline The deadline for the transaction
     */
    function executeArbitrage(
        address[] calldata _path,
        uint256 _amountIn,
        uint256 _minAmountOut,
        uint256 _deadline
    ) external {
        // Ensure the path is valid
        require(_path.length >= 2, "Invalid path");
        require(_path[0] == _path[_path.length - 1], "Path must start and end with the same token");
        
        // Transfer tokens from the user to this contract
        IERC20(_path[0]).transferFrom(msg.sender, address(this), _amountIn);
        
        // Execute the arbitrage swaps
        uint256 initialBalance = IERC20(_path[0]).balanceOf(address(this));
        uint256 finalAmount = executeArbitrageSwaps(_path, _amountIn);
        
        // Ensure we received at least the minimum amount
        require(finalAmount >= _minAmountOut, "Insufficient output amount");
        
        // Calculate profit
        uint256 profit = finalAmount > _amountIn ? finalAmount - _amountIn : 0;
        
        // Transfer the tokens back to the user
        IERC20(_path[0]).transfer(msg.sender, finalAmount);
        
        // Emit event
        emit ArbitrageExecuted(msg.sender, _path, _amountIn, finalAmount, profit);
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
     * @dev Get the current nonce for a user
     * @param user The user's address
     * @return The next available nonce
     */
    function getNonce(address user) external view returns (uint256) {
        uint256 nonce = 0;
        while (usedNonces[user][nonce]) {
            nonce++;
        }
        return nonce;
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