// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";

/**
 * @title GaslessMetaTransactions
 * @dev A contract that enables gasless meta transactions for arbitrage
 */
contract GaslessMetaTransactions is Ownable {
    using ECDSA for bytes32;
    
    // Uniswap V2 Router address
    address public immutable uniswapRouter;
    
    // Domain separator for EIP-712
    bytes32 public immutable DOMAIN_SEPARATOR;
    
    // The hash of the EIP-712 type for meta transactions
    bytes32 public constant META_TRANSACTION_TYPEHASH = keccak256(
        "MetaTransaction(uint256 nonce,address from,bytes functionSignature)"
    );
    
    // Mapping of address to nonce
    mapping(address => uint256) public nonces;
    
    // Events
    event MetaTransactionExecuted(address indexed from, address indexed to, bytes functionSignature);
    
    /**
     * @dev Constructor
     * @param _uniswapRouter The address of the Uniswap V2 Router
     */
    constructor(address _uniswapRouter) {
        uniswapRouter = _uniswapRouter;
        
        // Initialize domain separator
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("GaslessMetaTransactions")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }
    
    /**
     * @dev Executes a meta transaction
     * @param userAddress The address of the user who signed the meta transaction
     * @param functionSignature The function signature to execute
     * @param sigR The R component of the signature
     * @param sigS The S component of the signature
     * @param sigV The V component of the signature
     */
    function executeMetaTransaction(
        address userAddress,
        bytes memory functionSignature,
        bytes32 sigR,
        bytes32 sigS,
        uint8 sigV
    ) public returns (bytes memory) {
        // Verify the signature
        bytes32 digest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                DOMAIN_SEPARATOR,
                keccak256(
                    abi.encode(
                        META_TRANSACTION_TYPEHASH,
                        nonces[userAddress]++,
                        userAddress,
                        keccak256(functionSignature)
                    )
                )
            )
        );
        
        address signer = ecrecover(digest, sigV, sigR, sigS);
        require(signer == userAddress, "GaslessMetaTransactions: Invalid signature");
        
        // Execute the function
        (bool success, bytes memory returnData) = address(this).call(
            abi.encodePacked(functionSignature, userAddress)
        );
        require(success, "GaslessMetaTransactions: Function call failed");
        
        emit MetaTransactionExecuted(userAddress, address(this), functionSignature);
        
        return returnData;
    }
    
    /**
     * @dev Executes a swap on Uniswap (can be called via meta transaction)
     * @param tokenIn The address of the token to swap from
     * @param tokenOut The address of the token to swap to
     * @param amountIn The amount of tokenIn to swap
     * @param amountOutMin The minimum amount of tokenOut to receive
     * @param deadline The deadline for the swap
     * @param userAddress The address of the user (appended by executeMetaTransaction)
     */
    function swap(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin,
        uint256 deadline,
        address userAddress
    ) public returns (uint256[] memory amounts) {
        // Ensure this is called via executeMetaTransaction or by the owner
        require(
            msg.sender == address(this) || msg.sender == owner(),
            "GaslessMetaTransactions: Unauthorized"
        );
        
        // Transfer tokens from the user to this contract
        IERC20(tokenIn).transferFrom(userAddress, address(this), amountIn);
        
        // Approve the router to spend the tokens
        IERC20(tokenIn).approve(uniswapRouter, amountIn);
        
        // Create the swap path
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;
        
        // Execute the swap
        IUniswapV2Router02 router = IUniswapV2Router02(uniswapRouter);
        amounts = router.swapExactTokensForTokens(
            amountIn,
            amountOutMin,
            path,
            userAddress,  // Send the output tokens directly to the user
            deadline
        );
        
        return amounts;
    }
    
    /**
     * @dev Executes a multi-hop swap on Uniswap (can be called via meta transaction)
     * @param path The path of tokens to swap through
     * @param amountIn The amount of the first token to swap
     * @param amountOutMin The minimum amount of the last token to receive
     * @param deadline The deadline for the swap
     * @param userAddress The address of the user (appended by executeMetaTransaction)
     */
    function swapMultiHop(
        address[] memory path,
        uint256 amountIn,
        uint256 amountOutMin,
        uint256 deadline,
        address userAddress
    ) public returns (uint256[] memory amounts) {
        // Ensure this is called via executeMetaTransaction or by the owner
        require(
            msg.sender == address(this) || msg.sender == owner(),
            "GaslessMetaTransactions: Unauthorized"
        );
        
        // Ensure the path is valid
        require(path.length >= 2, "GaslessMetaTransactions: Invalid path");
        
        // Transfer tokens from the user to this contract
        IERC20(path[0]).transferFrom(userAddress, address(this), amountIn);
        
        // Approve the router to spend the tokens
        IERC20(path[0]).approve(uniswapRouter, amountIn);
        
        // Execute the swap
        IUniswapV2Router02 router = IUniswapV2Router02(uniswapRouter);
        amounts = router.swapExactTokensForTokens(
            amountIn,
            amountOutMin,
            path,
            userAddress,  // Send the output tokens directly to the user
            deadline
        );
        
        return amounts;
    }
    
    /**
     * @dev Gets the current nonce for a user
     * @param user The address of the user
     * @return The current nonce
     */
    function getNonce(address user) public view returns (uint256) {
        return nonces[user];
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