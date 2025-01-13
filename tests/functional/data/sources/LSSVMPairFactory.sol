// SPDX-License-Identifier: AGPL-3.0
pragma solidity >=0.8.0 ^0.8.0 ^0.8.1 ^0.8.2 ^0.8.4;

// lib/openzeppelin-contracts/contracts/token/ERC721/IERC721Receiver.sol

// OpenZeppelin Contracts (last updated v4.6.0) (token/ERC721/IERC721Receiver.sol)

/**
 * @title ERC721 token receiver interface
 * @dev Interface for any contract that wants to support safeTransfers
 * from ERC721 asset contracts.
 */
interface IERC721Receiver {
    /**
     * @dev Whenever an {IERC721} `tokenId` token is transferred to this contract via {IERC721-safeTransferFrom}
     * by `operator` from `from`, this function is called.
     *
     * It must return its Solidity selector to confirm the token transfer.
     * If any other value is returned or the interface is not implemented by the recipient, the transfer will be reverted.
     *
     * The selector can be obtained in Solidity with `IERC721Receiver.onERC721Received.selector`.
     */
    function onERC721Received(
        address operator,
        address from,
        uint256 tokenId,
        bytes calldata data
    ) external returns (bytes4);
}

// lib/openzeppelin-contracts/contracts/utils/Address.sol

// OpenZeppelin Contracts (last updated v4.8.0) (utils/Address.sol)

/**
 * @dev Collection of functions related to the address type
 */
library Address {
    /**
     * @dev Returns true if `account` is a contract.
     *
     * [IMPORTANT]
     * ====
     * It is unsafe to assume that an address for which this function returns
     * false is an externally-owned account (EOA) and not a contract.
     *
     * Among others, `isContract` will return false for the following
     * types of addresses:
     *
     *  - an externally-owned account
     *  - a contract in construction
     *  - an address where a contract will be created
     *  - an address where a contract lived, but was destroyed
     * ====
     *
     * [IMPORTANT]
     * ====
     * You shouldn't rely on `isContract` to protect against flash loan attacks!
     *
     * Preventing calls from contracts is highly discouraged. It breaks composability, breaks support for smart wallets
     * like Gnosis Safe, and does not provide security since it can be circumvented by calling from a contract
     * constructor.
     * ====
     */
    function isContract(address account) internal view returns (bool) {
        // This method relies on extcodesize/address.code.length, which returns 0
        // for contracts in construction, since the code is only stored at the end
        // of the constructor execution.

        return account.code.length > 0;
    }

    /**
     * @dev Replacement for Solidity's `transfer`: sends `amount` wei to
     * `recipient`, forwarding all available gas and reverting on errors.
     *
     * https://eips.ethereum.org/EIPS/eip-1884[EIP1884] increases the gas cost
     * of certain opcodes, possibly making contracts go over the 2300 gas limit
     * imposed by `transfer`, making them unable to receive funds via
     * `transfer`. {sendValue} removes this limitation.
     *
     * https://consensys.net/diligence/blog/2019/09/stop-using-soliditys-transfer-now/[Learn more].
     *
     * IMPORTANT: because control is transferred to `recipient`, care must be
     * taken to not create reentrancy vulnerabilities. Consider using
     * {ReentrancyGuard} or the
     * https://solidity.readthedocs.io/en/v0.5.11/security-considerations.html#use-the-checks-effects-interactions-pattern[checks-effects-interactions pattern].
     */
    function sendValue(address payable recipient, uint256 amount) internal {
        require(address(this).balance >= amount, "Address: insufficient balance");

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "Address: unable to send value, recipient may have reverted");
    }

    /**
     * @dev Performs a Solidity function call using a low level `call`. A
     * plain `call` is an unsafe replacement for a function call: use this
     * function instead.
     *
     * If `target` reverts with a revert reason, it is bubbled up by this
     * function (like regular Solidity function calls).
     *
     * Returns the raw returned data. To convert to the expected return value,
     * use https://solidity.readthedocs.io/en/latest/units-and-global-variables.html?highlight=abi.decode#abi-encoding-and-decoding-functions[`abi.decode`].
     *
     * Requirements:
     *
     * - `target` must be a contract.
     * - calling `target` with `data` must not revert.
     *
     * _Available since v3.1._
     */
    function functionCall(address target, bytes memory data) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, "Address: low-level call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`], but with
     * `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but also transferring `value` wei to `target`.
     *
     * Requirements:
     *
     * - the calling contract must have an ETH balance of at least `value`.
     * - the called Solidity function must be `payable`.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(
        address target,
        bytes memory data,
        uint256 value
    ) internal returns (bytes memory) {
        return functionCallWithValue(target, data, value, "Address: low-level call with value failed");
    }

    /**
     * @dev Same as {xref-Address-functionCallWithValue-address-bytes-uint256-}[`functionCallWithValue`], but
     * with `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(
        address target,
        bytes memory data,
        uint256 value,
        string memory errorMessage
    ) internal returns (bytes memory) {
        require(address(this).balance >= value, "Address: insufficient balance for call");
        (bool success, bytes memory returndata) = target.call{value: value}(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(address target, bytes memory data) internal view returns (bytes memory) {
        return functionStaticCall(target, data, "Address: low-level static call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-string-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        (bool success, bytes memory returndata) = target.staticcall(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but performing a delegate call.
     *
     * _Available since v3.4._
     */
    function functionDelegateCall(address target, bytes memory data) internal returns (bytes memory) {
        return functionDelegateCall(target, data, "Address: low-level delegate call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-string-}[`functionCall`],
     * but performing a delegate call.
     *
     * _Available since v3.4._
     */
    function functionDelegateCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal returns (bytes memory) {
        (bool success, bytes memory returndata) = target.delegatecall(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Tool to verify that a low level call to smart-contract was successful, and revert (either by bubbling
     * the revert reason or using the provided one) in case of unsuccessful call or if target was not a contract.
     *
     * _Available since v4.8._
     */
    function verifyCallResultFromTarget(
        address target,
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        if (success) {
            if (returndata.length == 0) {
                // only check isContract if the call was successful and the return data is empty
                // otherwise we already know that it was a contract
                require(isContract(target), "Address: call to non-contract");
            }
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    /**
     * @dev Tool to verify that a low level call was successful, and revert if it wasn't, either by bubbling the
     * revert reason or using the provided one.
     *
     * _Available since v4.3._
     */
    function verifyCallResult(
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal pure returns (bytes memory) {
        if (success) {
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    function _revert(bytes memory returndata, string memory errorMessage) private pure {
        // Look for revert reason and bubble it up if present
        if (returndata.length > 0) {
            // The easiest way to bubble the revert reason is using memory via assembly
            /// @solidity memory-safe-assembly
            assembly {
                let returndata_size := mload(returndata)
                revert(add(32, returndata), returndata_size)
            }
        } else {
            revert(errorMessage);
        }
    }
}

// lib/openzeppelin-contracts/contracts/utils/introspection/IERC165.sol

// OpenZeppelin Contracts v4.4.1 (utils/introspection/IERC165.sol)

/**
 * @dev Interface of the ERC165 standard, as defined in the
 * https://eips.ethereum.org/EIPS/eip-165[EIP].
 *
 * Implementers can declare support of contract interfaces, which can then be
 * queried by others ({ERC165Checker}).
 *
 * For an implementation, see {ERC165}.
 */
interface IERC165 {
    /**
     * @dev Returns true if this contract implements the interface defined by
     * `interfaceId`. See the corresponding
     * https://eips.ethereum.org/EIPS/eip-165#how-interfaces-are-identified[EIP section]
     * to learn more about how these ids are created.
     *
     * This function call must use less than 30 000 gas.
     */
    function supportsInterface(bytes4 interfaceId) external view returns (bool);
}

// lib/openzeppelin-contracts-upgradeable/contracts/access/IAccessControlUpgradeable.sol

// OpenZeppelin Contracts v4.4.1 (access/IAccessControl.sol)

/**
 * @dev External interface of AccessControl declared to support ERC165 detection.
 */
interface IAccessControlUpgradeable {
    /**
     * @dev Emitted when `newAdminRole` is set as ``role``'s admin role, replacing `previousAdminRole`
     *
     * `DEFAULT_ADMIN_ROLE` is the starting admin for all roles, despite
     * {RoleAdminChanged} not being emitted signaling this.
     *
     * _Available since v3.1._
     */
    event RoleAdminChanged(bytes32 indexed role, bytes32 indexed previousAdminRole, bytes32 indexed newAdminRole);

    /**
     * @dev Emitted when `account` is granted `role`.
     *
     * `sender` is the account that originated the contract call, an admin role
     * bearer except when using {AccessControl-_setupRole}.
     */
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);

    /**
     * @dev Emitted when `account` is revoked `role`.
     *
     * `sender` is the account that originated the contract call:
     *   - if using `revokeRole`, it is the admin role bearer
     *   - if using `renounceRole`, it is the role bearer (i.e. `account`)
     */
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);

    /**
     * @dev Returns `true` if `account` has been granted `role`.
     */
    function hasRole(bytes32 role, address account) external view returns (bool);

    /**
     * @dev Returns the admin role that controls `role`. See {grantRole} and
     * {revokeRole}.
     *
     * To change a role's admin, use {AccessControl-_setRoleAdmin}.
     */
    function getRoleAdmin(bytes32 role) external view returns (bytes32);

    /**
     * @dev Grants `role` to `account`.
     *
     * If `account` had not been already granted `role`, emits a {RoleGranted}
     * event.
     *
     * Requirements:
     *
     * - the caller must have ``role``'s admin role.
     */
    function grantRole(bytes32 role, address account) external;

    /**
     * @dev Revokes `role` from `account`.
     *
     * If `account` had been granted `role`, emits a {RoleRevoked} event.
     *
     * Requirements:
     *
     * - the caller must have ``role``'s admin role.
     */
    function revokeRole(bytes32 role, address account) external;

    /**
     * @dev Revokes `role` from the calling account.
     *
     * Roles are often managed via {grantRole} and {revokeRole}: this function's
     * purpose is to provide a mechanism for accounts to lose their privileges
     * if they are compromised (such as when a trusted device is misplaced).
     *
     * If the calling account had been granted `role`, emits a {RoleRevoked}
     * event.
     *
     * Requirements:
     *
     * - the caller must be `account`.
     */
    function renounceRole(bytes32 role, address account) external;
}

// lib/openzeppelin-contracts-upgradeable/contracts/utils/AddressUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.7.0) (utils/Address.sol)

/**
 * @dev Collection of functions related to the address type
 */
library AddressUpgradeable {
    /**
     * @dev Returns true if `account` is a contract.
     *
     * [IMPORTANT]
     * ====
     * It is unsafe to assume that an address for which this function returns
     * false is an externally-owned account (EOA) and not a contract.
     *
     * Among others, `isContract` will return false for the following
     * types of addresses:
     *
     *  - an externally-owned account
     *  - a contract in construction
     *  - an address where a contract will be created
     *  - an address where a contract lived, but was destroyed
     * ====
     *
     * [IMPORTANT]
     * ====
     * You shouldn't rely on `isContract` to protect against flash loan attacks!
     *
     * Preventing calls from contracts is highly discouraged. It breaks composability, breaks support for smart wallets
     * like Gnosis Safe, and does not provide security since it can be circumvented by calling from a contract
     * constructor.
     * ====
     */
    function isContract(address account) internal view returns (bool) {
        // This method relies on extcodesize/address.code.length, which returns 0
        // for contracts in construction, since the code is only stored at the end
        // of the constructor execution.

        return account.code.length > 0;
    }

    /**
     * @dev Replacement for Solidity's `transfer`: sends `amount` wei to
     * `recipient`, forwarding all available gas and reverting on errors.
     *
     * https://eips.ethereum.org/EIPS/eip-1884[EIP1884] increases the gas cost
     * of certain opcodes, possibly making contracts go over the 2300 gas limit
     * imposed by `transfer`, making them unable to receive funds via
     * `transfer`. {sendValue} removes this limitation.
     *
     * https://consensys.net/diligence/blog/2019/09/stop-using-soliditys-transfer-now/[Learn more].
     *
     * IMPORTANT: because control is transferred to `recipient`, care must be
     * taken to not create reentrancy vulnerabilities. Consider using
     * {ReentrancyGuard} or the
     * https://solidity.readthedocs.io/en/v0.5.11/security-considerations.html#use-the-checks-effects-interactions-pattern[checks-effects-interactions pattern].
     */
    function sendValue(address payable recipient, uint256 amount) internal {
        require(address(this).balance >= amount, "Address: insufficient balance");

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "Address: unable to send value, recipient may have reverted");
    }

    /**
     * @dev Performs a Solidity function call using a low level `call`. A
     * plain `call` is an unsafe replacement for a function call: use this
     * function instead.
     *
     * If `target` reverts with a revert reason, it is bubbled up by this
     * function (like regular Solidity function calls).
     *
     * Returns the raw returned data. To convert to the expected return value,
     * use https://solidity.readthedocs.io/en/latest/units-and-global-variables.html?highlight=abi.decode#abi-encoding-and-decoding-functions[`abi.decode`].
     *
     * Requirements:
     *
     * - `target` must be a contract.
     * - calling `target` with `data` must not revert.
     *
     * _Available since v3.1._
     */
    function functionCall(address target, bytes memory data) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, "Address: low-level call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`], but with
     * `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but also transferring `value` wei to `target`.
     *
     * Requirements:
     *
     * - the calling contract must have an ETH balance of at least `value`.
     * - the called Solidity function must be `payable`.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(
        address target,
        bytes memory data,
        uint256 value
    ) internal returns (bytes memory) {
        return functionCallWithValue(target, data, value, "Address: low-level call with value failed");
    }

    /**
     * @dev Same as {xref-Address-functionCallWithValue-address-bytes-uint256-}[`functionCallWithValue`], but
     * with `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(
        address target,
        bytes memory data,
        uint256 value,
        string memory errorMessage
    ) internal returns (bytes memory) {
        require(address(this).balance >= value, "Address: insufficient balance for call");
        (bool success, bytes memory returndata) = target.call{value: value}(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(address target, bytes memory data) internal view returns (bytes memory) {
        return functionStaticCall(target, data, "Address: low-level static call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-string-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        (bool success, bytes memory returndata) = target.staticcall(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Tool to verify that a low level call to smart-contract was successful, and revert (either by bubbling
     * the revert reason or using the provided one) in case of unsuccessful call or if target was not a contract.
     *
     * _Available since v4.8._
     */
    function verifyCallResultFromTarget(
        address target,
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        if (success) {
            if (returndata.length == 0) {
                // only check isContract if the call was successful and the return data is empty
                // otherwise we already know that it was a contract
                require(isContract(target), "Address: call to non-contract");
            }
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    /**
     * @dev Tool to verify that a low level call was successful, and revert if it wasn't, either by bubbling the
     * revert reason or using the provided one.
     *
     * _Available since v4.3._
     */
    function verifyCallResult(
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal pure returns (bytes memory) {
        if (success) {
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    function _revert(bytes memory returndata, string memory errorMessage) private pure {
        // Look for revert reason and bubble it up if present
        if (returndata.length > 0) {
            // The easiest way to bubble the revert reason is using memory via assembly
            /// @solidity memory-safe-assembly
            assembly {
                let returndata_size := mload(returndata)
                revert(add(32, returndata), returndata_size)
            }
        } else {
            revert(errorMessage);
        }
    }
}

// lib/solmate/src/auth/Owned.sol

/// @notice Simple single owner authorization mixin.
/// @author Solmate (https://github.com/transmissions11/solmate/blob/main/src/auth/Owned.sol)
abstract contract Owned {
    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    event OwnershipTransferred(address indexed user, address indexed newOwner);

    /*//////////////////////////////////////////////////////////////
                            OWNERSHIP STORAGE
    //////////////////////////////////////////////////////////////*/

    address public owner;

    modifier onlyOwner() virtual {
        require(msg.sender == owner, "UNAUTHORIZED");

        _;
    }

    /*//////////////////////////////////////////////////////////////
                               CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    constructor(address _owner) {
        owner = _owner;

        emit OwnershipTransferred(address(0), _owner);
    }

    /*//////////////////////////////////////////////////////////////
                             OWNERSHIP LOGIC
    //////////////////////////////////////////////////////////////*/

    function transferOwnership(address newOwner) public virtual onlyOwner {
        owner = newOwner;

        emit OwnershipTransferred(msg.sender, newOwner);
    }
}

// lib/solmate/src/tokens/ERC20.sol

/// @notice Modern and gas efficient ERC20 + EIP-2612 implementation.
/// @author Solmate (https://github.com/transmissions11/solmate/blob/main/src/tokens/ERC20.sol)
/// @author Modified from Uniswap (https://github.com/Uniswap/uniswap-v2-core/blob/master/contracts/UniswapV2ERC20.sol)
/// @dev Do not manually set balances without updating totalSupply, as the sum of all user balances must not exceed it.
abstract contract ERC20 {
    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    event Transfer(address indexed from, address indexed to, uint256 amount);

    event Approval(address indexed owner, address indexed spender, uint256 amount);

    /*//////////////////////////////////////////////////////////////
                            METADATA STORAGE
    //////////////////////////////////////////////////////////////*/

    string public name;

    string public symbol;

    uint8 public immutable decimals;

    /*//////////////////////////////////////////////////////////////
                              ERC20 STORAGE
    //////////////////////////////////////////////////////////////*/

    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;

    mapping(address => mapping(address => uint256)) public allowance;

    /*//////////////////////////////////////////////////////////////
                            EIP-2612 STORAGE
    //////////////////////////////////////////////////////////////*/

    uint256 internal immutable INITIAL_CHAIN_ID;

    bytes32 internal immutable INITIAL_DOMAIN_SEPARATOR;

    mapping(address => uint256) public nonces;

    /*//////////////////////////////////////////////////////////////
                               CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    constructor(
        string memory _name,
        string memory _symbol,
        uint8 _decimals
    ) {
        name = _name;
        symbol = _symbol;
        decimals = _decimals;

        INITIAL_CHAIN_ID = block.chainid;
        INITIAL_DOMAIN_SEPARATOR = computeDomainSeparator();
    }

    /*//////////////////////////////////////////////////////////////
                               ERC20 LOGIC
    //////////////////////////////////////////////////////////////*/

    function approve(address spender, uint256 amount) public virtual returns (bool) {
        allowance[msg.sender][spender] = amount;

        emit Approval(msg.sender, spender, amount);

        return true;
    }

    function transfer(address to, uint256 amount) public virtual returns (bool) {
        balanceOf[msg.sender] -= amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(msg.sender, to, amount);

        return true;
    }

    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) public virtual returns (bool) {
        uint256 allowed = allowance[from][msg.sender]; // Saves gas for limited approvals.

        if (allowed != type(uint256).max) allowance[from][msg.sender] = allowed - amount;

        balanceOf[from] -= amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(from, to, amount);

        return true;
    }

    /*//////////////////////////////////////////////////////////////
                             EIP-2612 LOGIC
    //////////////////////////////////////////////////////////////*/

    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) public virtual {
        require(deadline >= block.timestamp, "PERMIT_DEADLINE_EXPIRED");

        // Unchecked because the only math done is incrementing
        // the owner's nonce which cannot realistically overflow.
        unchecked {
            address recoveredAddress = ecrecover(
                keccak256(
                    abi.encodePacked(
                        "\x19\x01",
                        DOMAIN_SEPARATOR(),
                        keccak256(
                            abi.encode(
                                keccak256(
                                    "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
                                ),
                                owner,
                                spender,
                                value,
                                nonces[owner]++,
                                deadline
                            )
                        )
                    )
                ),
                v,
                r,
                s
            );

            require(recoveredAddress != address(0) && recoveredAddress == owner, "INVALID_SIGNER");

            allowance[recoveredAddress][spender] = value;
        }

        emit Approval(owner, spender, value);
    }

    function DOMAIN_SEPARATOR() public view virtual returns (bytes32) {
        return block.chainid == INITIAL_CHAIN_ID ? INITIAL_DOMAIN_SEPARATOR : computeDomainSeparator();
    }

    function computeDomainSeparator() internal view virtual returns (bytes32) {
        return
            keccak256(
                abi.encode(
                    keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                    keccak256(bytes(name)),
                    keccak256("1"),
                    block.chainid,
                    address(this)
                )
            );
    }

    /*//////////////////////////////////////////////////////////////
                        INTERNAL MINT/BURN LOGIC
    //////////////////////////////////////////////////////////////*/

    function _mint(address to, uint256 amount) internal virtual {
        totalSupply += amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(address(0), to, amount);
    }

    function _burn(address from, uint256 amount) internal virtual {
        balanceOf[from] -= amount;

        // Cannot underflow because a user's balance
        // will never be larger than the total supply.
        unchecked {
            totalSupply -= amount;
        }

        emit Transfer(from, address(0), amount);
    }
}

// src/bonding-curves/CurveErrorCodes.sol

contract CurveErrorCodes {
    enum Error {
        OK, // No error
        INVALID_NUMITEMS, // The numItem value is 0
        SPOT_PRICE_OVERFLOW, // The updated spot price doesn't fit into 128 bits
        DELTA_OVERFLOW, // The updated delta doesn't fit into 128 bits
        SPOT_PRICE_UNDERFLOW, // The updated spot price goes too low
        AUCTION_ENDED // The auction has ended
    }
}

// src/lib/IOwnershipTransferReceiver.sol

interface IOwnershipTransferReceiver {
    function onOwnershipTransferred(address oldOwner, bytes memory data) external payable;
}

// src/property-checking/IPropertyChecker.sol

interface IPropertyChecker {
    function hasProperties(uint256[] calldata ids, bytes calldata params) external returns (bool);
}

// src/royalty-auth/IArtBlocks.sol

/**
 * @dev Art Blocks nfts
 */
interface IArtBlocks {
    // document getter function of public variable
    function admin() external view returns (address);
}

// src/royalty-auth/IDigitalax.sol

/**
 * @dev Digitalax nfts
 */
interface IDigitalax {
    function accessControls() external view returns (address);
}

/**
 * @dev Digitalax Access Controls Simple
 */
interface IDigitalaxAccessControls {
    function hasAdminRole(address _account) external view returns (bool);
}

// src/royalty-auth/IFoundation.sol

interface IFoundation {
    /*
     *  bytes4(keccak256('getFees(uint256)')) == 0xd5a06d4c
     *
     *  => 0xd5a06d4c = 0xd5a06d4c
     */
    function getFees(uint256 tokenId) external view returns (address payable[] memory, uint256[] memory);
}

interface IFoundationTreasuryNode {
    function getFoundationTreasury() external view returns (address payable);
}

interface IFoundationTreasury {
    function isAdmin(address account) external view returns (bool);
}

// src/royalty-auth/INiftyGateway.sol

/**
 * @dev Nifty builder instance
 */
interface INiftyBuilderInstance {
    function niftyRegistryContract() external view returns (address);
}

/**
 * @dev Nifty registry
 */
interface INiftyRegistry {
    /**
     * @dev function to see if sending key is valid
     */
    function isValidNiftySender(address sending_key) external view returns (bool);
}

// src/settings/ISettings.sol

interface ISettings {
    struct PairInfo {
        address prevOwner;
        uint96 unlockTime;
        address prevFeeRecipient;
    }

    function getFeeSplitBps() external pure returns (uint64);

    function getRoyaltyInfo(address pairAddress) external view returns (bool, uint96);

    function settingsFeeRecipient() external returns (address payable);

    function getPrevFeeRecipientForPair(address pairAddress) external returns (address);
}

// lib/libraries-solidity/contracts/access/IAdminControl.sol

/// @author: manifold.xyz

/**
 * @dev Interface for admin control
 */
interface IAdminControl is IERC165 {

    event AdminApproved(address indexed account, address indexed sender);
    event AdminRevoked(address indexed account, address indexed sender);

    /**
     * @dev gets address of all admins
     */
    function getAdmins() external view returns (address[] memory);

    /**
     * @dev add an admin.  Can only be called by contract owner.
     */
    function approveAdmin(address admin) external;

    /**
     * @dev remove an admin.  Can only be called by contract owner.
     */
    function revokeAdmin(address admin) external;

    /**
     * @dev checks whether or not given address is an admin
     * Returns True if they are
     */
    function isAdmin(address admin) external view returns (bool);

}

// lib/openzeppelin-contracts/contracts/token/ERC1155/IERC1155.sol

// OpenZeppelin Contracts (last updated v4.7.0) (token/ERC1155/IERC1155.sol)

/**
 * @dev Required interface of an ERC1155 compliant contract, as defined in the
 * https://eips.ethereum.org/EIPS/eip-1155[EIP].
 *
 * _Available since v3.1._
 */
interface IERC1155 is IERC165 {
    /**
     * @dev Emitted when `value` tokens of token type `id` are transferred from `from` to `to` by `operator`.
     */
    event TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value);

    /**
     * @dev Equivalent to multiple {TransferSingle} events, where `operator`, `from` and `to` are the same for all
     * transfers.
     */
    event TransferBatch(
        address indexed operator,
        address indexed from,
        address indexed to,
        uint256[] ids,
        uint256[] values
    );

    /**
     * @dev Emitted when `account` grants or revokes permission to `operator` to transfer their tokens, according to
     * `approved`.
     */
    event ApprovalForAll(address indexed account, address indexed operator, bool approved);

    /**
     * @dev Emitted when the URI for token type `id` changes to `value`, if it is a non-programmatic URI.
     *
     * If an {URI} event was emitted for `id`, the standard
     * https://eips.ethereum.org/EIPS/eip-1155#metadata-extensions[guarantees] that `value` will equal the value
     * returned by {IERC1155MetadataURI-uri}.
     */
    event URI(string value, uint256 indexed id);

    /**
     * @dev Returns the amount of tokens of token type `id` owned by `account`.
     *
     * Requirements:
     *
     * - `account` cannot be the zero address.
     */
    function balanceOf(address account, uint256 id) external view returns (uint256);

    /**
     * @dev xref:ROOT:erc1155.adoc#batch-operations[Batched] version of {balanceOf}.
     *
     * Requirements:
     *
     * - `accounts` and `ids` must have the same length.
     */
    function balanceOfBatch(address[] calldata accounts, uint256[] calldata ids)
        external
        view
        returns (uint256[] memory);

    /**
     * @dev Grants or revokes permission to `operator` to transfer the caller's tokens, according to `approved`,
     *
     * Emits an {ApprovalForAll} event.
     *
     * Requirements:
     *
     * - `operator` cannot be the caller.
     */
    function setApprovalForAll(address operator, bool approved) external;

    /**
     * @dev Returns true if `operator` is approved to transfer ``account``'s tokens.
     *
     * See {setApprovalForAll}.
     */
    function isApprovedForAll(address account, address operator) external view returns (bool);

    /**
     * @dev Transfers `amount` tokens of token type `id` from `from` to `to`.
     *
     * Emits a {TransferSingle} event.
     *
     * Requirements:
     *
     * - `to` cannot be the zero address.
     * - If the caller is not `from`, it must have been approved to spend ``from``'s tokens via {setApprovalForAll}.
     * - `from` must have a balance of tokens of type `id` of at least `amount`.
     * - If `to` refers to a smart contract, it must implement {IERC1155Receiver-onERC1155Received} and return the
     * acceptance magic value.
     */
    function safeTransferFrom(
        address from,
        address to,
        uint256 id,
        uint256 amount,
        bytes calldata data
    ) external;

    /**
     * @dev xref:ROOT:erc1155.adoc#batch-operations[Batched] version of {safeTransferFrom}.
     *
     * Emits a {TransferBatch} event.
     *
     * Requirements:
     *
     * - `ids` and `amounts` must have the same length.
     * - If `to` refers to a smart contract, it must implement {IERC1155Receiver-onERC1155BatchReceived} and return the
     * acceptance magic value.
     */
    function safeBatchTransferFrom(
        address from,
        address to,
        uint256[] calldata ids,
        uint256[] calldata amounts,
        bytes calldata data
    ) external;
}

// lib/openzeppelin-contracts/contracts/token/ERC1155/IERC1155Receiver.sol

// OpenZeppelin Contracts (last updated v4.5.0) (token/ERC1155/IERC1155Receiver.sol)

/**
 * @dev _Available since v3.1._
 */
interface IERC1155Receiver is IERC165 {
    /**
     * @dev Handles the receipt of a single ERC1155 token type. This function is
     * called at the end of a `safeTransferFrom` after the balance has been updated.
     *
     * NOTE: To accept the transfer, this must return
     * `bytes4(keccak256("onERC1155Received(address,address,uint256,uint256,bytes)"))`
     * (i.e. 0xf23a6e61, or its own function selector).
     *
     * @param operator The address which initiated the transfer (i.e. msg.sender)
     * @param from The address which previously owned the token
     * @param id The ID of the token being transferred
     * @param value The amount of tokens being transferred
     * @param data Additional data with no specified format
     * @return `bytes4(keccak256("onERC1155Received(address,address,uint256,uint256,bytes)"))` if transfer is allowed
     */
    function onERC1155Received(
        address operator,
        address from,
        uint256 id,
        uint256 value,
        bytes calldata data
    ) external returns (bytes4);

    /**
     * @dev Handles the receipt of a multiple ERC1155 token types. This function
     * is called at the end of a `safeBatchTransferFrom` after the balances have
     * been updated.
     *
     * NOTE: To accept the transfer(s), this must return
     * `bytes4(keccak256("onERC1155BatchReceived(address,address,uint256[],uint256[],bytes)"))`
     * (i.e. 0xbc197c81, or its own function selector).
     *
     * @param operator The address which initiated the batch transfer (i.e. msg.sender)
     * @param from The address which previously owned the token
     * @param ids An array containing ids of each token being transferred (order and length must match values array)
     * @param values An array containing amounts of each token being transferred (order and length must match ids array)
     * @param data Additional data with no specified format
     * @return `bytes4(keccak256("onERC1155BatchReceived(address,address,uint256[],uint256[],bytes)"))` if transfer is allowed
     */
    function onERC1155BatchReceived(
        address operator,
        address from,
        uint256[] calldata ids,
        uint256[] calldata values,
        bytes calldata data
    ) external returns (bytes4);
}

// lib/openzeppelin-contracts/contracts/token/ERC721/IERC721.sol

// OpenZeppelin Contracts (last updated v4.8.0) (token/ERC721/IERC721.sol)

/**
 * @dev Required interface of an ERC721 compliant contract.
 */
interface IERC721 is IERC165 {
    /**
     * @dev Emitted when `tokenId` token is transferred from `from` to `to`.
     */
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);

    /**
     * @dev Emitted when `owner` enables `approved` to manage the `tokenId` token.
     */
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);

    /**
     * @dev Emitted when `owner` enables or disables (`approved`) `operator` to manage all of its assets.
     */
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    /**
     * @dev Returns the number of tokens in ``owner``'s account.
     */
    function balanceOf(address owner) external view returns (uint256 balance);

    /**
     * @dev Returns the owner of the `tokenId` token.
     *
     * Requirements:
     *
     * - `tokenId` must exist.
     */
    function ownerOf(uint256 tokenId) external view returns (address owner);

    /**
     * @dev Safely transfers `tokenId` token from `from` to `to`.
     *
     * Requirements:
     *
     * - `from` cannot be the zero address.
     * - `to` cannot be the zero address.
     * - `tokenId` token must exist and be owned by `from`.
     * - If the caller is not `from`, it must be approved to move this token by either {approve} or {setApprovalForAll}.
     * - If `to` refers to a smart contract, it must implement {IERC721Receiver-onERC721Received}, which is called upon a safe transfer.
     *
     * Emits a {Transfer} event.
     */
    function safeTransferFrom(
        address from,
        address to,
        uint256 tokenId,
        bytes calldata data
    ) external;

    /**
     * @dev Safely transfers `tokenId` token from `from` to `to`, checking first that contract recipients
     * are aware of the ERC721 protocol to prevent tokens from being forever locked.
     *
     * Requirements:
     *
     * - `from` cannot be the zero address.
     * - `to` cannot be the zero address.
     * - `tokenId` token must exist and be owned by `from`.
     * - If the caller is not `from`, it must have been allowed to move this token by either {approve} or {setApprovalForAll}.
     * - If `to` refers to a smart contract, it must implement {IERC721Receiver-onERC721Received}, which is called upon a safe transfer.
     *
     * Emits a {Transfer} event.
     */
    function safeTransferFrom(
        address from,
        address to,
        uint256 tokenId
    ) external;

    /**
     * @dev Transfers `tokenId` token from `from` to `to`.
     *
     * WARNING: Note that the caller is responsible to confirm that the recipient is capable of receiving ERC721
     * or else they may be permanently lost. Usage of {safeTransferFrom} prevents loss, though the caller must
     * understand this adds an external call which potentially creates a reentrancy vulnerability.
     *
     * Requirements:
     *
     * - `from` cannot be the zero address.
     * - `to` cannot be the zero address.
     * - `tokenId` token must be owned by `from`.
     * - If the caller is not `from`, it must be approved to move this token by either {approve} or {setApprovalForAll}.
     *
     * Emits a {Transfer} event.
     */
    function transferFrom(
        address from,
        address to,
        uint256 tokenId
    ) external;

    /**
     * @dev Gives permission to `to` to transfer `tokenId` token to another account.
     * The approval is cleared when the token is transferred.
     *
     * Only a single account can be approved at a time, so approving the zero address clears previous approvals.
     *
     * Requirements:
     *
     * - The caller must own the token or be an approved operator.
     * - `tokenId` must exist.
     *
     * Emits an {Approval} event.
     */
    function approve(address to, uint256 tokenId) external;

    /**
     * @dev Approve or remove `operator` as an operator for the caller.
     * Operators can call {transferFrom} or {safeTransferFrom} for any token owned by the caller.
     *
     * Requirements:
     *
     * - The `operator` cannot be the caller.
     *
     * Emits an {ApprovalForAll} event.
     */
    function setApprovalForAll(address operator, bool _approved) external;

    /**
     * @dev Returns the account approved for `tokenId` token.
     *
     * Requirements:
     *
     * - `tokenId` must exist.
     */
    function getApproved(uint256 tokenId) external view returns (address operator);

    /**
     * @dev Returns if the `operator` is allowed to manage all of the assets of `owner`.
     *
     * See {setApprovalForAll}
     */
    function isApprovedForAll(address owner, address operator) external view returns (bool);
}

// lib/openzeppelin-contracts/contracts/token/ERC721/utils/ERC721Holder.sol

// OpenZeppelin Contracts v4.4.1 (token/ERC721/utils/ERC721Holder.sol)

/**
 * @dev Implementation of the {IERC721Receiver} interface.
 *
 * Accepts all token transfers.
 * Make sure the contract is able to use its token with {IERC721-safeTransferFrom}, {IERC721-approve} or {IERC721-setApprovalForAll}.
 */
contract ERC721Holder is IERC721Receiver {
    /**
     * @dev See {IERC721Receiver-onERC721Received}.
     *
     * Always returns `IERC721Receiver.onERC721Received.selector`.
     */
    function onERC721Received(
        address,
        address,
        uint256,
        bytes memory
    ) public virtual override returns (bytes4) {
        return this.onERC721Received.selector;
    }
}

// lib/openzeppelin-contracts/contracts/utils/introspection/ERC165.sol

// OpenZeppelin Contracts v4.4.1 (utils/introspection/ERC165.sol)

/**
 * @dev Implementation of the {IERC165} interface.
 *
 * Contracts that want to implement ERC165 should inherit from this contract and override {supportsInterface} to check
 * for the additional interface id that will be supported. For example:
 *
 * ```solidity
 * function supportsInterface(bytes4 interfaceId) public view virtual override returns (bool) {
 *     return interfaceId == type(MyInterface).interfaceId || super.supportsInterface(interfaceId);
 * }
 * ```
 *
 * Alternatively, {ERC165Storage} provides an easier to use but more expensive implementation.
 */
abstract contract ERC165 is IERC165 {
    /**
     * @dev See {IERC165-supportsInterface}.
     */
    function supportsInterface(bytes4 interfaceId) public view virtual override returns (bool) {
        return interfaceId == type(IERC165).interfaceId;
    }
}

// lib/openzeppelin-contracts/contracts/utils/introspection/ERC165Checker.sol

// OpenZeppelin Contracts (last updated v4.8.0) (utils/introspection/ERC165Checker.sol)

/**
 * @dev Library used to query support of an interface declared via {IERC165}.
 *
 * Note that these functions return the actual result of the query: they do not
 * `revert` if an interface is not supported. It is up to the caller to decide
 * what to do in these cases.
 */
library ERC165Checker {
    // As per the EIP-165 spec, no interface should ever match 0xffffffff
    bytes4 private constant _INTERFACE_ID_INVALID = 0xffffffff;

    /**
     * @dev Returns true if `account` supports the {IERC165} interface.
     */
    function supportsERC165(address account) internal view returns (bool) {
        // Any contract that implements ERC165 must explicitly indicate support of
        // InterfaceId_ERC165 and explicitly indicate non-support of InterfaceId_Invalid
        return
            supportsERC165InterfaceUnchecked(account, type(IERC165).interfaceId) &&
            !supportsERC165InterfaceUnchecked(account, _INTERFACE_ID_INVALID);
    }

    /**
     * @dev Returns true if `account` supports the interface defined by
     * `interfaceId`. Support for {IERC165} itself is queried automatically.
     *
     * See {IERC165-supportsInterface}.
     */
    function supportsInterface(address account, bytes4 interfaceId) internal view returns (bool) {
        // query support of both ERC165 as per the spec and support of _interfaceId
        return supportsERC165(account) && supportsERC165InterfaceUnchecked(account, interfaceId);
    }

    /**
     * @dev Returns a boolean array where each value corresponds to the
     * interfaces passed in and whether they're supported or not. This allows
     * you to batch check interfaces for a contract where your expectation
     * is that some interfaces may not be supported.
     *
     * See {IERC165-supportsInterface}.
     *
     * _Available since v3.4._
     */
    function getSupportedInterfaces(address account, bytes4[] memory interfaceIds)
        internal
        view
        returns (bool[] memory)
    {
        // an array of booleans corresponding to interfaceIds and whether they're supported or not
        bool[] memory interfaceIdsSupported = new bool[](interfaceIds.length);

        // query support of ERC165 itself
        if (supportsERC165(account)) {
            // query support of each interface in interfaceIds
            for (uint256 i = 0; i < interfaceIds.length; i++) {
                interfaceIdsSupported[i] = supportsERC165InterfaceUnchecked(account, interfaceIds[i]);
            }
        }

        return interfaceIdsSupported;
    }

    /**
     * @dev Returns true if `account` supports all the interfaces defined in
     * `interfaceIds`. Support for {IERC165} itself is queried automatically.
     *
     * Batch-querying can lead to gas savings by skipping repeated checks for
     * {IERC165} support.
     *
     * See {IERC165-supportsInterface}.
     */
    function supportsAllInterfaces(address account, bytes4[] memory interfaceIds) internal view returns (bool) {
        // query support of ERC165 itself
        if (!supportsERC165(account)) {
            return false;
        }

        // query support of each interface in interfaceIds
        for (uint256 i = 0; i < interfaceIds.length; i++) {
            if (!supportsERC165InterfaceUnchecked(account, interfaceIds[i])) {
                return false;
            }
        }

        // all interfaces supported
        return true;
    }

    /**
     * @notice Query if a contract implements an interface, does not check ERC165 support
     * @param account The address of the contract to query for support of an interface
     * @param interfaceId The interface identifier, as specified in ERC-165
     * @return true if the contract at account indicates support of the interface with
     * identifier interfaceId, false otherwise
     * @dev Assumes that account contains a contract that supports ERC165, otherwise
     * the behavior of this method is undefined. This precondition can be checked
     * with {supportsERC165}.
     * Interface identification is specified in ERC-165.
     */
    function supportsERC165InterfaceUnchecked(address account, bytes4 interfaceId) internal view returns (bool) {
        // prepare call
        bytes memory encodedParams = abi.encodeWithSelector(IERC165.supportsInterface.selector, interfaceId);

        // perform static call
        bool success;
        uint256 returnSize;
        uint256 returnValue;
        assembly {
            success := staticcall(30000, account, add(encodedParams, 0x20), mload(encodedParams), 0x00, 0x20)
            returnSize := returndatasize()
            returnValue := mload(0x00)
        }

        return success && returnSize >= 0x20 && returnValue > 0;
    }
}

// lib/openzeppelin-contracts-upgradeable/contracts/proxy/utils/Initializable.sol

// OpenZeppelin Contracts (last updated v4.7.0) (proxy/utils/Initializable.sol)

/**
 * @dev This is a base contract to aid in writing upgradeable contracts, or any kind of contract that will be deployed
 * behind a proxy. Since proxied contracts do not make use of a constructor, it's common to move constructor logic to an
 * external initializer function, usually called `initialize`. It then becomes necessary to protect this initializer
 * function so it can only be called once. The {initializer} modifier provided by this contract will have this effect.
 *
 * The initialization functions use a version number. Once a version number is used, it is consumed and cannot be
 * reused. This mechanism prevents re-execution of each "step" but allows the creation of new initialization steps in
 * case an upgrade adds a module that needs to be initialized.
 *
 * For example:
 *
 * [.hljs-theme-light.nopadding]
 * ```
 * contract MyToken is ERC20Upgradeable {
 *     function initialize() initializer public {
 *         __ERC20_init("MyToken", "MTK");
 *     }
 * }
 * contract MyTokenV2 is MyToken, ERC20PermitUpgradeable {
 *     function initializeV2() reinitializer(2) public {
 *         __ERC20Permit_init("MyToken");
 *     }
 * }
 * ```
 *
 * TIP: To avoid leaving the proxy in an uninitialized state, the initializer function should be called as early as
 * possible by providing the encoded function call as the `_data` argument to {ERC1967Proxy-constructor}.
 *
 * CAUTION: When used with inheritance, manual care must be taken to not invoke a parent initializer twice, or to ensure
 * that all initializers are idempotent. This is not verified automatically as constructors are by Solidity.
 *
 * [CAUTION]
 * ====
 * Avoid leaving a contract uninitialized.
 *
 * An uninitialized contract can be taken over by an attacker. This applies to both a proxy and its implementation
 * contract, which may impact the proxy. To prevent the implementation contract from being used, you should invoke
 * the {_disableInitializers} function in the constructor to automatically lock it when it is deployed:
 *
 * [.hljs-theme-light.nopadding]
 * ```
 * /// @custom:oz-upgrades-unsafe-allow constructor
 * constructor() {
 *     _disableInitializers();
 * }
 * ```
 * ====
 */
abstract contract Initializable {
    /**
     * @dev Indicates that the contract has been initialized.
     * @custom:oz-retyped-from bool
     */
    uint8 private _initialized;

    /**
     * @dev Indicates that the contract is in the process of being initialized.
     */
    bool private _initializing;

    /**
     * @dev Triggered when the contract has been initialized or reinitialized.
     */
    event Initialized(uint8 version);

    /**
     * @dev A modifier that defines a protected initializer function that can be invoked at most once. In its scope,
     * `onlyInitializing` functions can be used to initialize parent contracts.
     *
     * Similar to `reinitializer(1)`, except that functions marked with `initializer` can be nested in the context of a
     * constructor.
     *
     * Emits an {Initialized} event.
     */
    modifier initializer() {
        bool isTopLevelCall = !_initializing;
        require(
            (isTopLevelCall && _initialized < 1) || (!AddressUpgradeable.isContract(address(this)) && _initialized == 1),
            "Initializable: contract is already initialized"
        );
        _initialized = 1;
        if (isTopLevelCall) {
            _initializing = true;
        }
        _;
        if (isTopLevelCall) {
            _initializing = false;
            emit Initialized(1);
        }
    }

    /**
     * @dev A modifier that defines a protected reinitializer function that can be invoked at most once, and only if the
     * contract hasn't been initialized to a greater version before. In its scope, `onlyInitializing` functions can be
     * used to initialize parent contracts.
     *
     * A reinitializer may be used after the original initialization step. This is essential to configure modules that
     * are added through upgrades and that require initialization.
     *
     * When `version` is 1, this modifier is similar to `initializer`, except that functions marked with `reinitializer`
     * cannot be nested. If one is invoked in the context of another, execution will revert.
     *
     * Note that versions can jump in increments greater than 1; this implies that if multiple reinitializers coexist in
     * a contract, executing them in the right order is up to the developer or operator.
     *
     * WARNING: setting the version to 255 will prevent any future reinitialization.
     *
     * Emits an {Initialized} event.
     */
    modifier reinitializer(uint8 version) {
        require(!_initializing && _initialized < version, "Initializable: contract is already initialized");
        _initialized = version;
        _initializing = true;
        _;
        _initializing = false;
        emit Initialized(version);
    }

    /**
     * @dev Modifier to protect an initialization function so that it can only be invoked by functions with the
     * {initializer} and {reinitializer} modifiers, directly or indirectly.
     */
    modifier onlyInitializing() {
        require(_initializing, "Initializable: contract is not initializing");
        _;
    }

    /**
     * @dev Locks the contract, preventing any future reinitialization. This cannot be part of an initializer call.
     * Calling this in the constructor of a contract will prevent that contract from being initialized or reinitialized
     * to any version. It is recommended to use this to lock implementation contracts that are designed to be called
     * through proxies.
     *
     * Emits an {Initialized} event the first time it is successfully executed.
     */
    function _disableInitializers() internal virtual {
        require(!_initializing, "Initializable: contract is initializing");
        if (_initialized != type(uint8).max) {
            _initialized = type(uint8).max;
            emit Initialized(type(uint8).max);
        }
    }

    /**
     * @dev Internal function that returns the initialized version. Returns `_initialized`
     */
    function _getInitializedVersion() internal view returns (uint8) {
        return _initialized;
    }

    /**
     * @dev Internal function that returns the initialized version. Returns `_initializing`
     */
    function _isInitializing() internal view returns (bool) {
        return _initializing;
    }
}

// lib/royalty-registry-solidity/contracts/IRoyaltyEngineV1.sol

/// @author: manifold.xyz

/**
 * @dev Lookup engine interface
 */
interface IRoyaltyEngineV1 is IERC165 {
    /**
     * Get the royalty for a given token (address, id) and value amount.  Does not cache the bps/amounts.  Caches the spec for a given token address
     *
     * @param tokenAddress - The address of the token
     * @param tokenId      - The id of the token
     * @param value        - The value you wish to get the royalty of
     *
     * returns Two arrays of equal length, royalty recipients and the corresponding amount each recipient should get
     */
    function getRoyalty(address tokenAddress, uint256 tokenId, uint256 value)
        external
        returns (address payable[] memory recipients, uint256[] memory amounts);

    /**
     * View only version of getRoyalty
     *
     * @param tokenAddress - The address of the token
     * @param tokenId      - The id of the token
     * @param value        - The value you wish to get the royalty of
     *
     * returns Two arrays of equal length, royalty recipients and the corresponding amount each recipient should get
     */
    function getRoyaltyView(address tokenAddress, uint256 tokenId, uint256 value)
        external
        view
        returns (address payable[] memory recipients, uint256[] memory amounts);
}

// lib/solmate/src/utils/SafeTransferLib.sol

/// @notice Safe ETH and ERC20 transfer library that gracefully handles missing return values.
/// @author Solmate (https://github.com/transmissions11/solmate/blob/main/src/utils/SafeTransferLib.sol)
/// @dev Use with caution! Some functions in this library knowingly create dirty bits at the destination of the free memory pointer.
/// @dev Note that none of the functions in this library check that a token has code at all! That responsibility is delegated to the caller.
library SafeTransferLib {
    /*//////////////////////////////////////////////////////////////
                             ETH OPERATIONS
    //////////////////////////////////////////////////////////////*/

    function safeTransferETH(address to, uint256 amount) internal {
        bool success;

        /// @solidity memory-safe-assembly
        assembly {
            // Transfer the ETH and store if it succeeded or not.
            success := call(gas(), to, amount, 0, 0, 0, 0)
        }

        require(success, "ETH_TRANSFER_FAILED");
    }

    /*//////////////////////////////////////////////////////////////
                            ERC20 OPERATIONS
    //////////////////////////////////////////////////////////////*/

    function safeTransferFrom(
        ERC20 token,
        address from,
        address to,
        uint256 amount
    ) internal {
        bool success;

        /// @solidity memory-safe-assembly
        assembly {
            // Get a pointer to some free memory.
            let freeMemoryPointer := mload(0x40)

            // Write the abi-encoded calldata into memory, beginning with the function selector.
            mstore(freeMemoryPointer, 0x23b872dd00000000000000000000000000000000000000000000000000000000)
            mstore(add(freeMemoryPointer, 4), from) // Append the "from" argument.
            mstore(add(freeMemoryPointer, 36), to) // Append the "to" argument.
            mstore(add(freeMemoryPointer, 68), amount) // Append the "amount" argument.

            success := and(
                // Set success to whether the call reverted, if not we check it either
                // returned exactly 1 (can't just be non-zero data), or had no return data.
                or(and(eq(mload(0), 1), gt(returndatasize(), 31)), iszero(returndatasize())),
                // We use 100 because the length of our calldata totals up like so: 4 + 32 * 3.
                // We use 0 and 32 to copy up to 32 bytes of return data into the scratch space.
                // Counterintuitively, this call must be positioned second to the or() call in the
                // surrounding and() call or else returndatasize() will be zero during the computation.
                call(gas(), token, 0, freeMemoryPointer, 100, 0, 32)
            )
        }

        require(success, "TRANSFER_FROM_FAILED");
    }

    function safeTransfer(
        ERC20 token,
        address to,
        uint256 amount
    ) internal {
        bool success;

        /// @solidity memory-safe-assembly
        assembly {
            // Get a pointer to some free memory.
            let freeMemoryPointer := mload(0x40)

            // Write the abi-encoded calldata into memory, beginning with the function selector.
            mstore(freeMemoryPointer, 0xa9059cbb00000000000000000000000000000000000000000000000000000000)
            mstore(add(freeMemoryPointer, 4), to) // Append the "to" argument.
            mstore(add(freeMemoryPointer, 36), amount) // Append the "amount" argument.

            success := and(
                // Set success to whether the call reverted, if not we check it either
                // returned exactly 1 (can't just be non-zero data), or had no return data.
                or(and(eq(mload(0), 1), gt(returndatasize(), 31)), iszero(returndatasize())),
                // We use 68 because the length of our calldata totals up like so: 4 + 32 * 2.
                // We use 0 and 32 to copy up to 32 bytes of return data into the scratch space.
                // Counterintuitively, this call must be positioned second to the or() call in the
                // surrounding and() call or else returndatasize() will be zero during the computation.
                call(gas(), token, 0, freeMemoryPointer, 68, 0, 32)
            )
        }

        require(success, "TRANSFER_FAILED");
    }

    function safeApprove(
        ERC20 token,
        address to,
        uint256 amount
    ) internal {
        bool success;

        /// @solidity memory-safe-assembly
        assembly {
            // Get a pointer to some free memory.
            let freeMemoryPointer := mload(0x40)

            // Write the abi-encoded calldata into memory, beginning with the function selector.
            mstore(freeMemoryPointer, 0x095ea7b300000000000000000000000000000000000000000000000000000000)
            mstore(add(freeMemoryPointer, 4), to) // Append the "to" argument.
            mstore(add(freeMemoryPointer, 36), amount) // Append the "amount" argument.

            success := and(
                // Set success to whether the call reverted, if not we check it either
                // returned exactly 1 (can't just be non-zero data), or had no return data.
                or(and(eq(mload(0), 1), gt(returndatasize(), 31)), iszero(returndatasize())),
                // We use 68 because the length of our calldata totals up like so: 4 + 32 * 2.
                // We use 0 and 32 to copy up to 32 bytes of return data into the scratch space.
                // Counterintuitively, this call must be positioned second to the or() call in the
                // surrounding and() call or else returndatasize() will be zero during the computation.
                call(gas(), token, 0, freeMemoryPointer, 68, 0, 32)
            )
        }

        require(success, "APPROVE_FAILED");
    }
}

// src/bonding-curves/ICurve.sol

interface ICurve {
    /**
     * @notice Validates if a delta value is valid for the curve. The criteria for
     * validity can be different for each type of curve, for instance ExponentialCurve
     * requires delta to be greater than 1.
     * @param delta The delta value to be validated
     * @return valid True if delta is valid, false otherwise
     */
    function validateDelta(uint128 delta) external pure returns (bool valid);

    /**
     * @notice Validates if a new spot price is valid for the curve. Spot price is generally assumed to be the immediate sell price of 1 NFT to the pool, in units of the pool's paired token.
     * @param newSpotPrice The new spot price to be set
     * @return valid True if the new spot price is valid, false otherwise
     */
    function validateSpotPrice(uint128 newSpotPrice) external view returns (bool valid);

    /**
     * @notice Given the current state of the pair and the trade, computes how much the user
     * should pay to purchase an NFT from the pair, the new spot price, and other values.
     * @param spotPrice The current selling spot price of the pair, in tokens
     * @param delta The delta parameter of the pair, what it means depends on the curve
     * @param numItems The number of NFTs the user is buying from the pair
     * @param feeMultiplier Determines how much fee the LP takes from this trade, 18 decimals
     * @param protocolFeeMultiplier Determines how much fee the protocol takes from this trade, 18 decimals
     * @return error Any math calculation errors, only Error.OK means the returned values are valid
     * @return newSpotPrice The updated selling spot price, in tokens
     * @return newDelta The updated delta, used to parameterize the bonding curve
     * @return inputValue The amount that the user should pay, in tokens
     * @return tradeFee The amount that is sent to the trade fee recipient
     * @return protocolFee The amount of fee to send to the protocol, in tokens
     */
    function getBuyInfo(
        uint128 spotPrice,
        uint128 delta,
        uint256 numItems,
        uint256 feeMultiplier,
        uint256 protocolFeeMultiplier
    )
        external
        view
        returns (
            CurveErrorCodes.Error error,
            uint128 newSpotPrice,
            uint128 newDelta,
            uint256 inputValue,
            uint256 tradeFee,
            uint256 protocolFee
        );

    /**
     * @notice Given the current state of the pair and the trade, computes how much the user
     * should receive when selling NFTs to the pair, the new spot price, and other values.
     * @param spotPrice The current selling spot price of the pair, in tokens
     * @param delta The delta parameter of the pair, what it means depends on the curve
     * @param numItems The number of NFTs the user is selling to the pair
     * @param feeMultiplier Determines how much fee the LP takes from this trade, 18 decimals
     * @param protocolFeeMultiplier Determines how much fee the protocol takes from this trade, 18 decimals
     * @return error Any math calculation errors, only Error.OK means the returned values are valid
     * @return newSpotPrice The updated selling spot price, in tokens
     * @return newDelta The updated delta, used to parameterize the bonding curve
     * @return outputValue The amount that the user should receive, in tokens
     * @return tradeFee The amount that is sent to the trade fee recipient
     * @return protocolFee The amount of fee to send to the protocol, in tokens
     */
    function getSellInfo(
        uint128 spotPrice,
        uint128 delta,
        uint256 numItems,
        uint256 feeMultiplier,
        uint256 protocolFeeMultiplier
    )
        external
        view
        returns (
            CurveErrorCodes.Error error,
            uint128 newSpotPrice,
            uint128 newDelta,
            uint256 outputValue,
            uint256 tradeFee,
            uint256 protocolFee
        );
}

// lib/openzeppelin-contracts-upgradeable/contracts/utils/ContextUpgradeable.sol

// OpenZeppelin Contracts v4.4.1 (utils/Context.sol)

/**
 * @dev Provides information about the current execution context, including the
 * sender of the transaction and its data. While these are generally available
 * via msg.sender and msg.data, they should not be accessed in such a direct
 * manner, since when dealing with meta-transactions the account sending and
 * paying for execution may not be the actual sender (as far as an application
 * is concerned).
 *
 * This contract is only required for intermediate, library-like contracts.
 */
abstract contract ContextUpgradeable is Initializable {
    function __Context_init() internal onlyInitializing {
    }

    function __Context_init_unchained() internal onlyInitializing {
    }
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    function _msgData() internal view virtual returns (bytes calldata) {
        return msg.data;
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[50] private __gap;
}

// lib/openzeppelin-contracts/contracts/token/ERC1155/utils/ERC1155Receiver.sol

// OpenZeppelin Contracts v4.4.1 (token/ERC1155/utils/ERC1155Receiver.sol)

/**
 * @dev _Available since v3.1._
 */
abstract contract ERC1155Receiver is ERC165, IERC1155Receiver {
    /**
     * @dev See {IERC165-supportsInterface}.
     */
    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC165, IERC165) returns (bool) {
        return interfaceId == type(IERC1155Receiver).interfaceId || super.supportsInterface(interfaceId);
    }
}

// lib/openzeppelin-contracts-upgradeable/contracts/access/OwnableUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.7.0) (access/Ownable.sol)

/**
 * @dev Contract module which provides a basic access control mechanism, where
 * there is an account (an owner) that can be granted exclusive access to
 * specific functions.
 *
 * By default, the owner account will be the one that deploys the contract. This
 * can later be changed with {transferOwnership}.
 *
 * This module is used through inheritance. It will make available the modifier
 * `onlyOwner`, which can be applied to your functions to restrict their use to
 * the owner.
 */
abstract contract OwnableUpgradeable is Initializable, ContextUpgradeable {
    address private _owner;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    /**
     * @dev Initializes the contract setting the deployer as the initial owner.
     */
    function __Ownable_init() internal onlyInitializing {
        __Ownable_init_unchained();
    }

    function __Ownable_init_unchained() internal onlyInitializing {
        _transferOwnership(_msgSender());
    }

    /**
     * @dev Throws if called by any account other than the owner.
     */
    modifier onlyOwner() {
        _checkOwner();
        _;
    }

    /**
     * @dev Returns the address of the current owner.
     */
    function owner() public view virtual returns (address) {
        return _owner;
    }

    /**
     * @dev Throws if the sender is not the owner.
     */
    function _checkOwner() internal view virtual {
        require(owner() == _msgSender(), "Ownable: caller is not the owner");
    }

    /**
     * @dev Leaves the contract without owner. It will not be possible to call
     * `onlyOwner` functions anymore. Can only be called by the current owner.
     *
     * NOTE: Renouncing ownership will leave the contract without an owner,
     * thereby removing any functionality that is only available to the owner.
     */
    function renounceOwnership() public virtual onlyOwner {
        _transferOwnership(address(0));
    }

    /**
     * @dev Transfers ownership of the contract to a new account (`newOwner`).
     * Can only be called by the current owner.
     */
    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable: new owner is the zero address");
        _transferOwnership(newOwner);
    }

    /**
     * @dev Transfers ownership of the contract to a new account (`newOwner`).
     * Internal function without access restriction.
     */
    function _transferOwnership(address newOwner) internal virtual {
        address oldOwner = _owner;
        _owner = newOwner;
        emit OwnershipTransferred(oldOwner, newOwner);
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[49] private __gap;
}

// lib/openzeppelin-contracts/contracts/token/ERC1155/utils/ERC1155Holder.sol

// OpenZeppelin Contracts (last updated v4.5.0) (token/ERC1155/utils/ERC1155Holder.sol)

/**
 * Simple implementation of `ERC1155Receiver` that will allow a contract to hold ERC1155 tokens.
 *
 * IMPORTANT: When inheriting this contract, you must include a way to use the received tokens, otherwise they will be
 * stuck.
 *
 * @dev _Available since v3.1._
 */
contract ERC1155Holder is ERC1155Receiver {
    function onERC1155Received(
        address,
        address,
        uint256,
        uint256,
        bytes memory
    ) public virtual override returns (bytes4) {
        return this.onERC1155Received.selector;
    }

    function onERC1155BatchReceived(
        address,
        address,
        uint256[] memory,
        uint256[] memory,
        bytes memory
    ) public virtual override returns (bytes4) {
        return this.onERC1155BatchReceived.selector;
    }
}

// src/lib/OwnableWithTransferCallback.sol

abstract contract OwnableWithTransferCallback {
    using ERC165Checker for address;
    using Address for address;

    bytes4 constant TRANSFER_CALLBACK = type(IOwnershipTransferReceiver).interfaceId;

    error Ownable_NotOwner();
    error Ownable_NewOwnerZeroAddress();

    address private _owner;

    event OwnershipTransferred(address indexed newOwner);

    /**
     * @dev Initializes the contract setting the deployer as the initial owner.
     */
    function __Ownable_init(address initialOwner) internal {
        _owner = initialOwner;
    }

    /**
     * @dev Returns the address of the current owner.
     */
    function owner() public view virtual returns (address) {
        return _owner;
    }

    /**
     * @dev Throws if called by any account other than the owner.
     */
    modifier onlyOwner() {
        if (owner() != msg.sender) revert Ownable_NotOwner();
        _;
    }

    /**
     * @dev Transfers ownership of the contract to a new account (`newOwner`).
     * @param newOwner The new address to become owner
     * @param data Any additional data to send to the ownership received callback.
     * Disallows setting to the zero address as a way to more gas-efficiently avoid reinitialization.
     * When ownership is transferred, if the new owner implements IOwnershipTransferCallback, we make a callback.
     * Can only be called by the current owner.
     */
    function transferOwnership(address newOwner, bytes calldata data) public payable virtual onlyOwner {
        if (newOwner == address(0)) revert Ownable_NewOwnerZeroAddress();
        _transferOwnership(newOwner);

        if (newOwner.isContract()) {
            try IOwnershipTransferReceiver(newOwner).onOwnershipTransferred{value: msg.value}(msg.sender, data) {}
            // If revert...
            catch (bytes memory reason) {
                // If we just transferred to a contract w/ no callback, this is fine
                if (reason.length == 0) {
                    // i.e., no need to revert
                }
                // Otherwise, the callback had an error, and we should revert
                else {
                    /// @solidity memory-safe-assembly
                    assembly {
                        revert(add(32, reason), mload(reason))
                    }
                }
            }
        }
    }

    /**
     * @notice Transfers ownership of the contract to a new account (`newOwner`).
     * @dev Internal function without access restriction.
     */
    function _transferOwnership(address newOwner) internal virtual {
        _owner = newOwner;
        emit OwnershipTransferred(newOwner);
    }
}

// src/ILSSVMPairFactoryLike.sol

interface ILSSVMPairFactoryLike {
    struct Settings {
        uint96 bps;
        address pairAddress;
    }

    enum PairNFTType {
        ERC721,
        ERC1155
    }

    enum PairTokenType {
        ETH,
        ERC20
    }

    enum PairVariant {
        ERC721_ETH,
        ERC721_ERC20,
        ERC1155_ETH,
        ERC1155_ERC20
    }

    function protocolFeeMultiplier() external view returns (uint256);

    function protocolFeeRecipient() external view returns (address payable);

    function callAllowed(address target) external view returns (bool);

    function authAllowedForToken(address tokenAddress, address proposedAuthAddress) external view returns (bool);

    function getSettingsForPair(address pairAddress) external view returns (bool settingsEnabled, uint96 bps);

    function enableSettingsForPair(address settings, address pairAddress) external;

    function disableSettingsForPair(address settings, address pairAddress) external;

    function routerStatus(LSSVMRouter router) external view returns (bool allowed, bool wasEverTouched);

    function isValidPair(address pairAddress) external view returns (bool);

    function getPairNFTType(address pairAddress) external pure returns (PairNFTType);

    function getPairTokenType(address pairAddress) external pure returns (PairTokenType);

    function openLock() external;

    function closeLock() external;
}

// src/LSSVMPair.sol

/**
 * @title The base contract for an NFT/TOKEN AMM pair
 * @author boredGenius, 0xmons, 0xCygaar
 * @notice This implements the core swap logic from NFT to TOKEN
 */
abstract contract LSSVMPair is OwnableWithTransferCallback, ERC721Holder, ERC1155Holder {
    /**
     * Library usage **
     */

    using Address for address;

    /**
     *  Enums **
     */

    enum PoolType {
        TOKEN,
        NFT,
        TRADE
    }

    /**
     * Constants **
     */

    /**
     * @dev 50%, must <= 1 - MAX_PROTOCOL_FEE (set in LSSVMPairFactory)
     */
    uint256 internal constant MAX_TRADE_FEE = 0.5e18;

    /**
     *  Immutable params **
     */

    /**
     * @notice Sudoswap Royalty Engine
     */
    IRoyaltyEngineV1 public immutable ROYALTY_ENGINE;

    /**
     *  Storage variables **
     */

    /**
     * @dev This is generally used to mean the immediate sell price for the next marginal NFT.
     * However, this should NOT be assumed, as bonding curves may use spotPrice in different ways.
     * Use getBuyNFTQuote and getSellNFTQuote for accurate pricing info.
     */
    uint128 public spotPrice;

    /**
     * @notice The parameter for the pair's bonding curve.
     * Units and meaning are bonding curve dependent.
     */
    uint128 public delta;

    /**
     * @notice The spread between buy and sell prices, set to be a multiplier we apply to the buy price
     * Fee is only relevant for TRADE pools. Units are in base 1e18.
     */
    uint96 public fee;

    /**
     * @notice The address that swapped assets are sent to.
     * For TRADE pools, assets are always sent to the pool, so this is used to track trade fee.
     * If set to address(0), will default to owner() for NFT and TOKEN pools.
     */
    address payable internal assetRecipient;

    /**
     *  Events
     */

    event SwapNFTInPair(uint256 amountOut, uint256[] ids);
    event SwapNFTInPair(uint256 amountOut, uint256 numNFTs);
    event SwapNFTOutPair(uint256 amountIn, uint256[] ids);
    event SwapNFTOutPair(uint256 amountIn, uint256 numNFTs);
    event SpotPriceUpdate(uint128 newSpotPrice);
    event TokenDeposit(uint256 amount);
    event TokenWithdrawal(uint256 amount);
    event NFTWithdrawal(uint256[] ids);
    event NFTWithdrawal(uint256 numNFTs);
    event DeltaUpdate(uint128 newDelta);
    event FeeUpdate(uint96 newFee);
    event AssetRecipientChange(address indexed a);

    /**
     *  Errors
     */

    error LSSVMPair__NotRouter();
    error LSSVMPair__CallFailed();
    error LSSVMPair__InvalidDelta();
    error LSSVMPair__WrongPoolType();
    error LSSVMPair__OutputTooSmall();
    error LSSVMPair__ZeroSwapAmount();
    error LSSVMPair__RoyaltyTooLarge();
    error LSSVMPair__TradeFeeTooLarge();
    error LSSVMPair__InvalidSpotPrice();
    error LSSVMPair__TargetNotAllowed();
    error LSSVMPair__NftNotTransferred();
    error LSSVMPair__AlreadyInitialized();
    error LSSVMPair__FunctionNotAllowed();
    error LSSVMPair__DemandedInputTooLarge();
    error LSSVMPair__NonTradePoolWithTradeFee();
    error LSSVMPair__BondingCurveError(CurveErrorCodes.Error error);

    constructor(IRoyaltyEngineV1 royaltyEngine) {
        ROYALTY_ENGINE = royaltyEngine;
    }

    /**
     * @notice Called during pair creation to set initial parameters
     * @dev Only called once by factory to initialize.
     * We verify this by making sure that the current owner is address(0).
     * The Ownable library we use disallows setting the owner to be address(0), so this condition
     * should only be valid before the first initialize call.
     * @param _owner The owner of the pair
     * @param _assetRecipient The address that will receive the TOKEN or NFT sent to this pair during swaps. NOTE: If set to address(0), they will go to the pair itself.
     * @param _delta The initial delta of the bonding curve
     * @param _fee The initial % fee taken, if this is a trade pair
     * @param _spotPrice The initial price to sell an asset into the pair
     */
    function initialize(
        address _owner,
        address payable _assetRecipient,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice
    ) external {
        if (owner() != address(0)) revert LSSVMPair__AlreadyInitialized();
        __Ownable_init(_owner);

        ICurve _bondingCurve = bondingCurve();
        PoolType _poolType = poolType();
        if (_poolType != PoolType.TRADE) {
            if (_fee != 0) revert LSSVMPair__NonTradePoolWithTradeFee();
        } else {
            if (_fee > MAX_TRADE_FEE) revert LSSVMPair__TradeFeeTooLarge();
            fee = _fee;
        }

        assetRecipient = _assetRecipient;

        if (!_bondingCurve.validateDelta(_delta)) revert LSSVMPair__InvalidDelta();
        if (!_bondingCurve.validateSpotPrice(_spotPrice)) revert LSSVMPair__InvalidSpotPrice();
        delta = _delta;
        spotPrice = _spotPrice;
    }

    /**
     * External state-changing functions
     */

    /**
     * @notice Sends token to the pair in exchange for a specific set of NFTs
     * @dev To compute the amount of token to send, call bondingCurve.getBuyInfo
     * This swap is meant for users who want specific IDs. Also higher chance of
     * reverting if some of the specified IDs leave the pool before the swap goes through.
     * @param nftIds The list of IDs of the NFTs to purchase
     * @param maxExpectedTokenInput The maximum acceptable cost from the sender. If the actual
     * amount is greater than this value, the transaction will be reverted.
     * @param nftRecipient The recipient of the NFTs
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for ETH pairs.
     * @return - The amount of token used for purchase
     */
    function swapTokenForSpecificNFTs(
        uint256[] calldata nftIds,
        uint256 maxExpectedTokenInput,
        address nftRecipient,
        bool isRouter,
        address routerCaller
    ) external payable virtual returns (uint256);

    /**
     * @notice Sends a set of NFTs to the pair in exchange for token
     * @dev To compute the amount of token to that will be received, call bondingCurve.getSellInfo.
     * @param nftIds The list of IDs of the NFTs to sell to the pair
     * @param minExpectedTokenOutput The minimum acceptable token received by the sender. If the actual
     * amount is less than this value, the transaction will be reverted.
     * @param tokenRecipient The recipient of the token output
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for
     * ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for
     * ETH pairs.
     * @return outputAmount The amount of token received
     */
    function swapNFTsForToken(
        uint256[] calldata nftIds,
        uint256 minExpectedTokenOutput,
        address payable tokenRecipient,
        bool isRouter,
        address routerCaller
    ) external virtual returns (uint256 outputAmount);

    /**
     * View functions
     */

    /**
     * @dev Used as read function to query the bonding curve for buy pricing info
     * @param numNFTs The number of NFTs to buy from the pair
     */
    function getBuyNFTQuote(uint256 assetId, uint256 numNFTs)
        external
        view
        returns (
            CurveErrorCodes.Error error,
            uint256 newSpotPrice,
            uint256 newDelta,
            uint256 inputAmount,
            uint256 protocolFee,
            uint256 royaltyAmount
        )
    {
        uint256 tradeFee;
        (error, newSpotPrice, newDelta, inputAmount, tradeFee, protocolFee) =
            bondingCurve().getBuyInfo(spotPrice, delta, numNFTs, fee, factory().protocolFeeMultiplier());

        if (numNFTs != 0) {
            // Calculate the inputAmount minus tradeFee and protocolFee
            uint256 inputAmountMinusFees = inputAmount - tradeFee - protocolFee;

            // Compute royalties
            (,, royaltyAmount) = calculateRoyaltiesView(assetId, inputAmountMinusFees);

            inputAmount += royaltyAmount;
        }
    }

    /**
     * @dev Used as read function to query the bonding curve for sell pricing info including royalties
     * @param numNFTs The number of NFTs to sell to the pair
     */
    function getSellNFTQuote(uint256 assetId, uint256 numNFTs)
        external
        view
        returns (
            CurveErrorCodes.Error error,
            uint256 newSpotPrice,
            uint256 newDelta,
            uint256 outputAmount,
            uint256 protocolFee,
            uint256 royaltyAmount
        )
    {
        (error, newSpotPrice, newDelta, outputAmount, /* tradeFee */, protocolFee) =
            bondingCurve().getSellInfo(spotPrice, delta, numNFTs, fee, factory().protocolFeeMultiplier());

        if (numNFTs != 0) {
            // Compute royalties
            (,, royaltyAmount) = calculateRoyaltiesView(assetId, outputAmount);

            // Deduct royalties from outputAmount
            unchecked {
                // Safe because we already require outputAmount >= royaltyAmount in _calculateRoyalties()
                outputAmount -= royaltyAmount;
            }
        }
    }

    /**
     * @notice Returns the pair's variant (Pair uses ETH or ERC20)
     */
    function pairVariant() public pure virtual returns (ILSSVMPairFactoryLike.PairVariant);

    function factory() public pure returns (ILSSVMPairFactoryLike _factory) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            _factory := shr(0x60, calldataload(sub(calldatasize(), paramsLength)))
        }
    }

    /**
     * @notice Returns the type of bonding curve that parameterizes the pair
     */
    function bondingCurve() public pure returns (ICurve _bondingCurve) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            _bondingCurve := shr(0x60, calldataload(add(sub(calldatasize(), paramsLength), 20)))
        }
    }

    /**
     * @notice Returns the address of NFT collection that parameterizes the pair
     */
    function nft() public pure returns (address _nft) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            _nft := shr(0x60, calldataload(add(sub(calldatasize(), paramsLength), 40)))
        }
    }

    /**
     * @notice Returns the pair's type (TOKEN/NFT/TRADE)
     */
    function poolType() public pure returns (PoolType _poolType) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            _poolType := shr(0xf8, calldataload(add(sub(calldatasize(), paramsLength), 60)))
        }
    }

    /**
     * @notice Returns the address that receives assets when a swap is done with this pair
     * Can be set to another address by the owner, but has no effect on TRADE pools
     * If set to address(0), defaults to owner() for NFT/TOKEN pools
     */
    function getAssetRecipient() public view returns (address payable) {
        // TRADE pools will always receive the asset themselves
        if (poolType() == PoolType.TRADE) {
            return payable(address(this));
        }

        address payable _assetRecipient = assetRecipient;

        // Otherwise, we return the recipient if it's been set
        // Or, we replace it with owner() if it's address(0)
        if (_assetRecipient == address(0)) {
            return payable(owner());
        }
        return _assetRecipient;
    }

    /**
     * @notice Returns the address that receives trade fees when a swap is done with this pair
     * Only relevant for TRADE pools
     * If set to address(0), defaults to the pair itself
     */
    function getFeeRecipient() public view returns (address payable _feeRecipient) {
        _feeRecipient = assetRecipient;
        if (_feeRecipient == address(0)) {
            _feeRecipient = payable(address(this));
        }
    }

    /**
     * Internal functions
     */

    /**
     * @notice Calculates the amount needed to be sent into the pair for a buy and adjusts spot price or delta if necessary
     * @param numNFTs The amount of NFTs to purchase from the pair
     * @param _bondingCurve The bonding curve to use for price calculation
     * @param _factory The factory to use for protocol fee lookup
     * @return tradeFee The amount of tokens to send as trade fee
     * @return protocolFee The amount of tokens to send as protocol fee
     * @return inputAmount The amount of tokens total tokens receive
     */
    function _calculateBuyInfoAndUpdatePoolParams(uint256 numNFTs, ICurve _bondingCurve, ILSSVMPairFactoryLike _factory)
        internal
        returns (uint256 tradeFee, uint256 protocolFee, uint256 inputAmount)
    {
        CurveErrorCodes.Error error;
        // Save on 2 SLOADs by caching
        uint128 currentSpotPrice = spotPrice;
        uint128 currentDelta = delta;
        uint128 newDelta;
        uint128 newSpotPrice;
        (error, newSpotPrice, newDelta, inputAmount, tradeFee, protocolFee) =
            _bondingCurve.getBuyInfo(currentSpotPrice, currentDelta, numNFTs, fee, _factory.protocolFeeMultiplier());

        // Revert if bonding curve had an error
        if (error != CurveErrorCodes.Error.OK) {
            revert LSSVMPair__BondingCurveError(error);
        }

        // Consolidate writes to save gas
        if (currentSpotPrice != newSpotPrice || currentDelta != newDelta) {
            spotPrice = newSpotPrice;
            delta = newDelta;
        }

        // Emit spot price update if it has been updated
        if (currentSpotPrice != newSpotPrice) {
            emit SpotPriceUpdate(newSpotPrice);
        }

        // Emit delta update if it has been updated
        if (currentDelta != newDelta) {
            emit DeltaUpdate(newDelta);
        }
    }

    /**
     * @notice Calculates the amount needed to be sent by the pair for a sell and adjusts spot price or delta if necessary
     * @param numNFTs The amount of NFTs to send to the the pair
     * @param _bondingCurve The bonding curve to use for price calculation
     * @param _factory The factory to use for protocol fee lookup
     * @return protocolFee The amount of tokens to send as protocol fee
     * @return outputAmount The amount of tokens total tokens receive
     */
    function _calculateSellInfoAndUpdatePoolParams(
        uint256 numNFTs,
        ICurve _bondingCurve,
        ILSSVMPairFactoryLike _factory
    ) internal returns (uint256 protocolFee, uint256 outputAmount) {
        CurveErrorCodes.Error error;
        // Save on 2 SLOADs by caching
        uint128 currentSpotPrice = spotPrice;
        uint128 currentDelta = delta;
        uint128 newSpotPrice;
        uint128 newDelta;
        (error, newSpotPrice, newDelta, outputAmount, /*tradeFee*/, protocolFee) =
            _bondingCurve.getSellInfo(currentSpotPrice, currentDelta, numNFTs, fee, _factory.protocolFeeMultiplier());

        // Revert if bonding curve had an error
        if (error != CurveErrorCodes.Error.OK) {
            revert LSSVMPair__BondingCurveError(error);
        }

        // Consolidate writes to save gas
        if (currentSpotPrice != newSpotPrice || currentDelta != newDelta) {
            spotPrice = newSpotPrice;
            delta = newDelta;
        }

        // Emit spot price update if it has been updated
        if (currentSpotPrice != newSpotPrice) {
            emit SpotPriceUpdate(newSpotPrice);
        }

        // Emit delta update if it has been updated
        if (currentDelta != newDelta) {
            emit DeltaUpdate(newDelta);
        }
    }

    /**
     * @notice Pulls the token input of a trade from the trader (including all royalties and fees)
     * @param inputAmountExcludingRoyalty The amount of tokens to be sent, excluding the royalty (includes protocol fee)
     * @param royaltyAmounts The amounts of tokens to be sent as royalties
     * @param royaltyRecipients The recipients of the royalties
     * @param royaltyTotal The sum of all royaltyAmounts
     * @param tradeFeeAmount The amount of tokens to be sent as trade fee (if applicable)
     * @param isRouter Whether or not the caller is LSSVMRouter
     * @param routerCaller If called from LSSVMRouter, store the original caller
     * @param protocolFee The protocol fee to be paid
     */
    function _pullTokenInputs(
        uint256 inputAmountExcludingRoyalty,
        uint256[] memory royaltyAmounts,
        address payable[] memory royaltyRecipients,
        uint256 royaltyTotal,
        uint256 tradeFeeAmount,
        bool isRouter,
        address routerCaller,
        uint256 protocolFee
    ) internal virtual;

    /**
     * @notice Sends excess tokens back to the caller (if applicable)
     * @dev Swap callers interacting with an ETH pair must be able to receive ETH (e.g. if the caller sends too much ETH)
     */
    function _refundTokenToSender(uint256 inputAmount) internal virtual;

    /**
     * @notice Sends tokens to a recipient
     * @param tokenRecipient The address receiving the tokens
     * @param outputAmount The amount of tokens to send
     */
    function _sendTokenOutput(address payable tokenRecipient, uint256 outputAmount) internal virtual;

    /**
     * @dev Used internally to grab pair parameters from calldata, see LSSVMPairCloner for technical details
     */
    function _immutableParamsLength() internal pure virtual returns (uint256);

    /**
     * Royalty support functions
     */

    function _calculateRoyalties(uint256 assetId, uint256 saleAmount)
        internal
        returns (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal)
    {
        (address payable[] memory recipients, uint256[] memory amounts) =
            ROYALTY_ENGINE.getRoyalty(nft(), assetId, saleAmount);
        return _calculateRoyaltiesLogic(recipients, amounts, saleAmount);
    }

    /**
     * @dev Same as _calculateRoyalties, but uses getRoyaltyView to avoid state mutations and is public for external callers
     */
    function calculateRoyaltiesView(uint256 assetId, uint256 saleAmount)
        public
        view
        returns (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal)
    {
        (address payable[] memory recipients, uint256[] memory amounts) =
            ROYALTY_ENGINE.getRoyaltyView(nft(), assetId, saleAmount);
        return _calculateRoyaltiesLogic(recipients, amounts, saleAmount);
    }

    /**
     * @dev Common logic used by _calculateRoyalties() and calculateRoyaltiesView()
     */
    function _calculateRoyaltiesLogic(address payable[] memory recipients, uint256[] memory amounts, uint256 saleAmount)
        internal
        view
        returns (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal)
    {
        // Cache to save gas
        uint256 numRecipients = recipients.length;

        if (numRecipients != 0) {
            // If a pair has custom Settings, use the overridden royalty amount and only use the first receiver
            try factory().getSettingsForPair(address(this)) returns (bool settingsEnabled, uint96 bps) {
                if (settingsEnabled) {
                    royaltyRecipients = new address payable[](1);
                    royaltyRecipients[0] = recipients[0];
                    royaltyAmounts = new uint256[](1);
                    royaltyAmounts[0] = (saleAmount * bps) / 10000;

                    // Update numRecipients to match new recipients list
                    numRecipients = 1;
                } else {
                    royaltyRecipients = recipients;
                    royaltyAmounts = amounts;
                }
            } catch {
                // Use the input values to calculate royalties if factory call fails
                royaltyRecipients = recipients;
                royaltyAmounts = amounts;
            }
        }

        for (uint256 i; i < numRecipients;) {
            royaltyTotal += royaltyAmounts[i];
            unchecked {
                ++i;
            }
        }

        // Ensure royalty total is at most 25% of the sale amount
        // This defends against a rogue Manifold registry that charges extremely high royalties
        if (royaltyTotal > saleAmount >> 2) {
            revert LSSVMPair__RoyaltyTooLarge();
        }
    }

    /**
     * Owner functions
     */

    /**
     * @notice Rescues a specified set of NFTs owned by the pair to the owner address. (onlyOwnable modifier is in the implemented function)
     * @param a The NFT to transfer
     * @param nftIds The list of IDs of the NFTs to send to the owner
     */
    function withdrawERC721(IERC721 a, uint256[] calldata nftIds) external virtual;

    /**
     * @notice Rescues ERC20 tokens from the pair to the owner. Only callable by the owner (onlyOwnable modifier is in the implemented function).
     * @param a The token to transfer
     * @param amount The amount of tokens to send to the owner
     */
    function withdrawERC20(ERC20 a, uint256 amount) external virtual;

    /**
     * @notice Rescues ERC1155 tokens from the pair to the owner. Only callable by the owner.
     * @param a The NFT to transfer
     * @param ids The NFT ids to transfer
     * @param amounts The amounts of each id to transfer
     */
    function withdrawERC1155(IERC1155 a, uint256[] calldata ids, uint256[] calldata amounts) external virtual;

    /**
     * @notice Updates the selling spot price. Only callable by the owner.
     * @param newSpotPrice The new selling spot price value, in Token
     */
    function changeSpotPrice(uint128 newSpotPrice) external onlyOwner {
        ICurve _bondingCurve = bondingCurve();
        if (!_bondingCurve.validateSpotPrice(newSpotPrice)) revert LSSVMPair__InvalidSpotPrice();
        if (spotPrice != newSpotPrice) {
            spotPrice = newSpotPrice;
            emit SpotPriceUpdate(newSpotPrice);
        }
    }

    /**
     * @notice Updates the delta parameter. Only callable by the owner.
     * @param newDelta The new delta parameter
     */
    function changeDelta(uint128 newDelta) external onlyOwner {
        ICurve _bondingCurve = bondingCurve();
        if (!_bondingCurve.validateDelta(newDelta)) revert LSSVMPair__InvalidDelta();
        if (delta != newDelta) {
            delta = newDelta;
            emit DeltaUpdate(newDelta);
        }
    }

    /**
     * @notice Updates the fee taken by the LP. Only callable by the owner.
     * Only callable if the pool is a Trade pool. Reverts if the fee is >= MAX_FEE.
     * @param newFee The new LP fee percentage, 18 decimals
     */
    function changeFee(uint96 newFee) external onlyOwner {
        PoolType _poolType = poolType();
        if (_poolType != PoolType.TRADE) revert LSSVMPair__NonTradePoolWithTradeFee();
        if (newFee > MAX_TRADE_FEE) revert LSSVMPair__TradeFeeTooLarge();
        if (fee != newFee) {
            fee = newFee;
            emit FeeUpdate(newFee);
        }
    }

    /**
     * @notice Changes the address that will receive assets received from
     * trades. Only callable by the owner.
     * @param newRecipient The new asset recipient
     */
    function changeAssetRecipient(address payable newRecipient) external onlyOwner {
        if (assetRecipient != newRecipient) {
            assetRecipient = newRecipient;
            emit AssetRecipientChange(newRecipient);
        }
    }

    function _preCallCheck(address target) internal virtual;

    /**
     * @notice Allows the pair to make arbitrary external calls to contracts
     * whitelisted by the protocol. Only callable by the owner.
     * @param target The contract to call
     * @param data The calldata to pass to the contract
     */
    function call(address payable target, bytes calldata data) external onlyOwner {
        ILSSVMPairFactoryLike _factory = factory();
        if (!_factory.callAllowed(target)) revert LSSVMPair__TargetNotAllowed();

        // Ensure the call isn't calling a banned function
        bytes4 sig = bytes4(data[:4]);
        if (
            sig == IOwnershipTransferReceiver.onOwnershipTransferred.selector
                || sig == LSSVMRouter.pairTransferERC20From.selector || sig == LSSVMRouter.pairTransferNFTFrom.selector
                || sig == LSSVMRouter.pairTransferERC1155From.selector || sig == ILSSVMPairFactoryLike.openLock.selector
                || sig == ILSSVMPairFactoryLike.closeLock.selector
        ) {
            revert LSSVMPair__FunctionNotAllowed();
        }

        // Prevent calling the pair's underlying nft
        // (We ban calling the underlying NFT/ERC20 to avoid maliciously transferring assets approved for the pair to spend)
        if (target == nft()) revert LSSVMPair__TargetNotAllowed();

        _preCallCheck(target);

        (bool success,) = target.call{value: 0}(data);
        if (!success) revert LSSVMPair__CallFailed();
    }

    /**
     * @notice Allows owner to batch multiple calls, forked from: https://github.com/boringcrypto/BoringSolidity/blob/master/contracts/BoringBatchable.sol
     * @notice The revert handling is forked from: https://github.com/OpenZeppelin/openzeppelin-contracts/blob/c239e1af8d1a1296577108dd6989a17b57434f8e/contracts/utils/Address.sol#L201
     * @dev Intended for withdrawing/altering pool pricing in one tx, only callable by owner, cannot change owner
     * @param calls The calldata for each call to make
     * @param revertOnFail Whether or not to revert the entire tx if any of the calls fail. Calls to transferOwnership will revert regardless.
     */
    function multicall(bytes[] calldata calls, bool revertOnFail) external onlyOwner {
        for (uint256 i; i < calls.length;) {
            bytes4 sig = bytes4(calls[i][:4]);
            // We ban calling transferOwnership when ownership
            if (sig == transferOwnership.selector) revert LSSVMPair__FunctionNotAllowed();

            (bool success, bytes memory result) = address(this).delegatecall(calls[i]);
            if (!success && revertOnFail) {
                assembly {
                    revert(add(0x20, result), mload(result))
                }
            }

            unchecked {
                ++i;
            }
        }
    }
}

// src/LSSVMRouter.sol

contract LSSVMRouter {
    using SafeTransferLib for address payable;
    using SafeTransferLib for ERC20;

    struct PairSwapSpecific {
        LSSVMPair pair;
        uint256[] nftIds;
    }

    struct RobustPairSwapSpecific {
        PairSwapSpecific swapInfo;
        uint256 maxCost;
    }

    struct RobustPairSwapSpecificForToken {
        PairSwapSpecific swapInfo;
        uint256 minOutput;
    }

    struct NFTsForSpecificNFTsTrade {
        PairSwapSpecific[] nftToTokenTrades;
        PairSwapSpecific[] tokenToNFTTrades;
    }

    struct RobustPairNFTsFoTokenAndTokenforNFTsTrade {
        RobustPairSwapSpecific[] tokenToNFTTrades;
        RobustPairSwapSpecificForToken[] nftToTokenTrades;
        uint256 inputAmount;
        address payable tokenRecipient;
        address nftRecipient;
    }

    modifier checkDeadline(uint256 deadline) {
        _checkDeadline(deadline);
        _;
    }

    ILSSVMPairFactoryLike public immutable factory;

    constructor(ILSSVMPairFactoryLike _factory) {
        factory = _factory;
    }

    /**
     * ETH swaps
     */

    /**
     * @notice Swaps ETH into specific NFTs using multiple pairs.
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to buy from each.
     * @param ethRecipient The address that will receive the unspent ETH input
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return remainingValue The unspent ETH amount
     */
    function swapETHForSpecificNFTs(
        PairSwapSpecific[] calldata swapList,
        address payable ethRecipient,
        address nftRecipient,
        uint256 deadline
    ) external payable checkDeadline(deadline) returns (uint256 remainingValue) {
        return _swapETHForSpecificNFTs(swapList, msg.value, ethRecipient, nftRecipient);
    }

    /**
     * @notice Swaps one set of NFTs into another set of specific NFTs using multiple pairs, using
     * ETH as the intermediary.
     * @param trade The struct containing all NFT-to-ETH swaps and ETH-to-NFT swaps.
     * @param minOutput The minimum acceptable total excess ETH received
     * @param ethRecipient The address that will receive the ETH output
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return outputAmount The total ETH received
     */
    function swapNFTsForSpecificNFTsThroughETH(
        NFTsForSpecificNFTsTrade calldata trade,
        uint256 minOutput,
        address payable ethRecipient,
        address nftRecipient,
        uint256 deadline
    ) external payable checkDeadline(deadline) returns (uint256 outputAmount) {
        // Swap NFTs for ETH
        // minOutput of swap set to 0 since we're doing an aggregate slippage check
        outputAmount = _swapNFTsForToken(trade.nftToTokenTrades, 0, payable(address(this)));

        // Add extra value to buy NFTs
        outputAmount += msg.value;

        // Swap ETH for specific NFTs
        // cost <= inputValue = outputAmount - minOutput, so outputAmount' = (outputAmount - minOutput - cost) + minOutput >= minOutput
        outputAmount = _swapETHForSpecificNFTs(
            trade.tokenToNFTTrades, outputAmount - minOutput, ethRecipient, nftRecipient
        ) + minOutput;
    }

    /**
     * ERC20 swaps
     *
     * Note: All ERC20 swaps assume that a single ERC20 token is used for all the pairs involved.
     * Swapping using multiple tokens in the same transaction is possible, but the slippage checks
     * & the return values will be meaningless, and may lead to undefined behavior.
     *
     * Note: The sender should ideally grant infinite token approval to the router in order for NFT-to-NFT
     * swaps to work smoothly.
     */

    /**
     * @notice Swaps ERC20 tokens into specific NFTs using multiple pairs.
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to buy from each.
     * @param inputAmount The amount of ERC20 tokens to add to the ERC20-to-NFT swaps
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return remainingValue The unspent token amount
     */
    function swapERC20ForSpecificNFTs(
        PairSwapSpecific[] calldata swapList,
        uint256 inputAmount,
        address nftRecipient,
        uint256 deadline
    ) external checkDeadline(deadline) returns (uint256 remainingValue) {
        return _swapERC20ForSpecificNFTs(swapList, inputAmount, nftRecipient);
    }

    /**
     * @notice Swaps NFTs into ETH/ERC20 using multiple pairs.
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to sell to each.
     * @param minOutput The minimum acceptable total tokens received
     * @param tokenRecipient The address that will receive the token output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return outputAmount The total tokens received
     */
    function swapNFTsForToken(
        PairSwapSpecific[] calldata swapList,
        uint256 minOutput,
        address tokenRecipient,
        uint256 deadline
    ) external checkDeadline(deadline) returns (uint256 outputAmount) {
        return _swapNFTsForToken(swapList, minOutput, payable(tokenRecipient));
    }

    /**
     * @notice Swaps one set of NFTs into another set of specific NFTs using multiple pairs, using
     * an ERC20 token as the intermediary.
     * @param trade The struct containing all NFT-to-ERC20 swaps and ERC20-to-NFT swaps.
     * @param inputAmount The amount of ERC20 tokens to add to the ERC20-to-NFT swaps
     * @param minOutput The minimum acceptable total excess tokens received
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return outputAmount The total ERC20 tokens received
     */
    function swapNFTsForSpecificNFTsThroughERC20(
        NFTsForSpecificNFTsTrade calldata trade,
        uint256 inputAmount,
        uint256 minOutput,
        address nftRecipient,
        uint256 deadline
    ) external checkDeadline(deadline) returns (uint256 outputAmount) {
        // Swap NFTs for ERC20
        // minOutput of swap set to 0 since we're doing an aggregate slippage check
        // output tokens are sent to msg.sender
        outputAmount = _swapNFTsForToken(trade.nftToTokenTrades, 0, payable(msg.sender));

        // Add extra value to buy NFTs
        outputAmount += inputAmount;

        // Swap ERC20 for specific NFTs
        // cost <= maxCost = outputAmount - minOutput, so outputAmount' = outputAmount - cost >= minOutput
        // input tokens are taken directly from msg.sender
        outputAmount =
            _swapERC20ForSpecificNFTs(trade.tokenToNFTTrades, outputAmount - minOutput, nftRecipient) + minOutput;
    }

    /**
     * Robust Swaps
     * These are "robust" versions of the NFT<>Token swap functions which will never revert due to slippage
     * Instead, users specify a per-swap max cost. If the price changes more than the user specifies, no swap is attempted. This allows users to specify a batch of swaps, and execute as many of them as possible.
     */

    /**
     * @dev Ensure msg.value >= sum of values in maxCostPerPair to make sure the transaction doesn't revert
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to buy from each.
     * @param ethRecipient The address that will receive the unspent ETH input
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return remainingValue The unspent token amount
     */
    function robustSwapETHForSpecificNFTs(
        RobustPairSwapSpecific[] calldata swapList,
        address payable ethRecipient,
        address nftRecipient,
        uint256 deadline
    ) public payable virtual checkDeadline(deadline) returns (uint256 remainingValue) {
        remainingValue = msg.value;
        uint256 pairCost;
        CurveErrorCodes.Error error;

        // Try doing each swap
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            // Calculate actual cost per swap
            (error,,, pairCost,,) = swapList[i].swapInfo.pair.getBuyNFTQuote(
                swapList[i].swapInfo.nftIds[0], swapList[i].swapInfo.nftIds.length
            );

            // If within our maxCost and no error, proceed
            if (pairCost <= swapList[i].maxCost && error == CurveErrorCodes.Error.OK) {
                // We know how much ETH to send because we already did the math above
                // So we just send that much
                remainingValue -= swapList[i].swapInfo.pair.swapTokenForSpecificNFTs{value: pairCost}(
                    swapList[i].swapInfo.nftIds, pairCost, nftRecipient, true, msg.sender
                );
            }

            unchecked {
                ++i;
            }
        }

        // Return remaining value to sender
        if (remainingValue > 0) {
            ethRecipient.safeTransferETH(remainingValue);
        }
    }

    /**
     * @notice Swaps as many ERC20 tokens for specific NFTs as possible, respecting the per-swap max cost.
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to buy from each.
     * @param inputAmount The amount of ERC20 tokens to add to the ERC20-to-NFT swaps
     * @param nftRecipient The address that will receive the NFT output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return remainingValue The unspent token amount
     */
    function robustSwapERC20ForSpecificNFTs(
        RobustPairSwapSpecific[] calldata swapList,
        uint256 inputAmount,
        address nftRecipient,
        uint256 deadline
    ) public virtual checkDeadline(deadline) returns (uint256 remainingValue) {
        remainingValue = inputAmount;
        uint256 pairCost;
        CurveErrorCodes.Error error;

        // Try doing each swap
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            // Calculate actual cost per swap
            (error,,, pairCost,,) = swapList[i].swapInfo.pair.getBuyNFTQuote(
                swapList[i].swapInfo.nftIds[0], swapList[i].swapInfo.nftIds.length
            );

            // If within our maxCost and no error, proceed
            if (pairCost <= swapList[i].maxCost && error == CurveErrorCodes.Error.OK) {
                remainingValue -= swapList[i].swapInfo.pair.swapTokenForSpecificNFTs(
                    swapList[i].swapInfo.nftIds, pairCost, nftRecipient, true, msg.sender
                );
            }

            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Swaps as many NFTs for tokens as possible, respecting the per-swap min output
     * @param swapList The list of pairs to trade with and the IDs of the NFTs to sell to each.
     * @param tokenRecipient The address that will receive the token output
     * @param deadline The Unix timestamp (in seconds) at/after which the swap will revert
     * @return outputAmount The total ETH/ERC20 received
     */
    function robustSwapNFTsForToken(
        RobustPairSwapSpecificForToken[] calldata swapList,
        address payable tokenRecipient,
        uint256 deadline
    ) public virtual checkDeadline(deadline) returns (uint256 outputAmount) {
        // Try doing each swap
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            uint256 pairOutput;

            // Locally scoped to avoid stack too deep error
            {
                CurveErrorCodes.Error error;
                uint256[] memory nftIds = swapList[i].swapInfo.nftIds;
                if (nftIds.length == 0) {
                    unchecked {
                        ++i;
                    }
                    continue;
                }
                (error,,, pairOutput,,) = swapList[i].swapInfo.pair.getSellNFTQuote(nftIds[0], nftIds.length);
                if (error != CurveErrorCodes.Error.OK) {
                    unchecked {
                        ++i;
                    }
                    continue;
                }
            }

            // If at least equal to our minOutput, proceed
            if (pairOutput >= swapList[i].minOutput) {
                // Do the swap and update outputAmount with how many tokens we got
                outputAmount += swapList[i].swapInfo.pair.swapNFTsForToken(
                    swapList[i].swapInfo.nftIds, 0, tokenRecipient, true, msg.sender
                );
            }

            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Buys NFTs with ETH and sells them for tokens in one transaction
     * @param params All the parameters for the swap (packed in struct to avoid stack too deep), containing:
     * - ethToNFTSwapList The list of NFTs to buy
     * - nftToTokenSwapList The list of NFTs to sell
     * - inputAmount The max amount of tokens to send (if ERC20)
     * - tokenRecipient The address that receives tokens from the NFTs sold
     * - nftRecipient The address that receives NFTs
     * - deadline UNIX timestamp deadline for the swap
     */
    function robustSwapETHForSpecificNFTsAndNFTsToToken(RobustPairNFTsFoTokenAndTokenforNFTsTrade calldata params)
        external
        payable
        virtual
        returns (uint256 remainingValue, uint256 outputAmount)
    {
        {
            remainingValue = msg.value;
            uint256 pairCost;
            CurveErrorCodes.Error error;

            // Try doing each swap
            uint256 numSwaps = params.tokenToNFTTrades.length;
            for (uint256 i; i < numSwaps;) {
                // Calculate actual cost per swap
                (error,,, pairCost,,) = params.tokenToNFTTrades[i].swapInfo.pair.getBuyNFTQuote(
                    params.tokenToNFTTrades[i].swapInfo.nftIds[0], params.tokenToNFTTrades[i].swapInfo.nftIds.length
                );

                // If within our maxCost and no error, proceed
                if (pairCost <= params.tokenToNFTTrades[i].maxCost && error == CurveErrorCodes.Error.OK) {
                    // We know how much ETH to send because we already did the math above
                    // So we just send that much
                    remainingValue -= params.tokenToNFTTrades[i].swapInfo.pair.swapTokenForSpecificNFTs{value: pairCost}(
                        params.tokenToNFTTrades[i].swapInfo.nftIds, pairCost, params.nftRecipient, true, msg.sender
                    );
                }

                unchecked {
                    ++i;
                }
            }

            // Return remaining value to sender
            if (remainingValue > 0) {
                params.tokenRecipient.safeTransferETH(remainingValue);
            }
        }
        {
            // Try doing each swap
            uint256 numSwaps = params.nftToTokenTrades.length;
            for (uint256 i; i < numSwaps;) {
                uint256 pairOutput;

                // Locally scoped to avoid stack too deep error
                {
                    CurveErrorCodes.Error error;
                    uint256 assetId = params.nftToTokenTrades[i].swapInfo.nftIds[0];
                    (error,,, pairOutput,,) = params.nftToTokenTrades[i].swapInfo.pair.getSellNFTQuote(
                        assetId, params.nftToTokenTrades[i].swapInfo.nftIds.length
                    );
                    if (error != CurveErrorCodes.Error.OK) {
                        unchecked {
                            ++i;
                        }
                        continue;
                    }
                }

                // If at least equal to our minOutput, proceed
                if (pairOutput >= params.nftToTokenTrades[i].minOutput) {
                    // Do the swap and update outputAmount with how many tokens we got
                    outputAmount += params.nftToTokenTrades[i].swapInfo.pair.swapNFTsForToken(
                        params.nftToTokenTrades[i].swapInfo.nftIds, 0, params.tokenRecipient, true, msg.sender
                    );
                }

                unchecked {
                    ++i;
                }
            }
        }
    }

    /**
     * @notice Buys NFTs with ERC20, and sells them for tokens in one transaction
     * @param params All the parameters for the swap (packed in struct to avoid stack too deep), containing:
     * - ethToNFTSwapList The list of NFTs to buy
     * - nftToTokenSwapList The list of NFTs to sell
     * - inputAmount The max amount of tokens to send (if ERC20)
     * - tokenRecipient The address that receives tokens from the NFTs sold
     * - nftRecipient The address that receives NFTs
     * - deadline UNIX timestamp deadline for the swap
     */
    function robustSwapERC20ForSpecificNFTsAndNFTsToToken(RobustPairNFTsFoTokenAndTokenforNFTsTrade calldata params)
        external
        virtual
        returns (uint256 remainingValue, uint256 outputAmount)
    {
        {
            remainingValue = params.inputAmount;
            uint256 pairCost;
            CurveErrorCodes.Error error;

            // Try doing each swap
            uint256 numSwaps = params.tokenToNFTTrades.length;
            for (uint256 i; i < numSwaps;) {
                // Calculate actual cost per swap
                (error,,, pairCost,,) = params.tokenToNFTTrades[i].swapInfo.pair.getBuyNFTQuote(
                    params.tokenToNFTTrades[i].swapInfo.nftIds[0], params.tokenToNFTTrades[i].swapInfo.nftIds.length
                );

                // If within our maxCost and no error, proceed
                if (pairCost <= params.tokenToNFTTrades[i].maxCost && error == CurveErrorCodes.Error.OK) {
                    remainingValue -= params.tokenToNFTTrades[i].swapInfo.pair.swapTokenForSpecificNFTs(
                        params.tokenToNFTTrades[i].swapInfo.nftIds, pairCost, params.nftRecipient, true, msg.sender
                    );
                }

                unchecked {
                    ++i;
                }
            }
        }
        {
            // Try doing each swap
            uint256 numSwaps = params.nftToTokenTrades.length;
            for (uint256 i; i < numSwaps;) {
                uint256 pairOutput;

                // Locally scoped to avoid stack too deep error
                {
                    CurveErrorCodes.Error error;
                    uint256 assetId = params.nftToTokenTrades[i].swapInfo.nftIds[0];
                    (error,,, pairOutput,,) = params.nftToTokenTrades[i].swapInfo.pair.getSellNFTQuote(
                        assetId, params.nftToTokenTrades[i].swapInfo.nftIds.length
                    );
                    if (error != CurveErrorCodes.Error.OK) {
                        unchecked {
                            ++i;
                        }
                        continue;
                    }
                }

                // If at least equal to our minOutput, proceed
                if (pairOutput >= params.nftToTokenTrades[i].minOutput) {
                    // Do the swap and update outputAmount with how many tokens we got
                    outputAmount += params.nftToTokenTrades[i].swapInfo.pair.swapNFTsForToken(
                        params.nftToTokenTrades[i].swapInfo.nftIds, 0, params.tokenRecipient, true, msg.sender
                    );
                }

                unchecked {
                    ++i;
                }
            }
        }
    }

    receive() external payable {}

    /**
     * Restricted functions
     */

    /**
     * @dev Allows an ERC20 pair contract to transfer ERC20 tokens directly from
     * the sender, in order to minimize the number of token transfers. Only callable by an ERC20 pair.
     * @param token The ERC20 token to transfer
     * @param from The address to transfer tokens from
     * @param to The address to transfer tokens to
     * @param amount The amount of tokens to transfer
     */
    function pairTransferERC20From(ERC20 token, address from, address to, uint256 amount) external {
        // verify caller is a trusted pair contract
        require(factory.isValidPair(msg.sender), "Not pair");
        // verify caller is an ERC20 pair
        require(factory.getPairTokenType(msg.sender) == ILSSVMPairFactoryLike.PairTokenType.ERC20, "Not ERC20 pair");

        // transfer tokens to pair
        token.safeTransferFrom(from, to, amount);
    }

    /**
     * @dev Allows a pair contract to transfer ERC721 NFTs directly from
     * the sender, in order to minimize the number of token transfers. Only callable by a pair.
     * @param nft The ERC721 NFT to transfer
     * @param from The address to transfer tokens from
     * @param to The address to transfer tokens to
     * @param id The ID of the NFT to transfer
     */
    function pairTransferNFTFrom(IERC721 nft, address from, address to, uint256 id) external {
        // verify caller is a trusted pair contract
        require(factory.isValidPair(msg.sender), "Not pair");

        // transfer NFTs to pair
        nft.transferFrom(from, to, id);
    }

    function pairTransferERC1155From(
        IERC1155 nft,
        address from,
        address to,
        uint256[] calldata ids,
        uint256[] calldata amounts
    ) external {
        // verify caller is a trusted pair contract
        require(factory.isValidPair(msg.sender), "Not pair");

        nft.safeBatchTransferFrom(from, to, ids, amounts, bytes(""));
    }

    /**
     * Internal functions
     */

    /**
     * @param deadline The last valid time for a swap
     */
    function _checkDeadline(uint256 deadline) internal view {
        require(block.timestamp <= deadline, "Deadline passed");
    }

    /**
     * @notice Internal function used to swap ETH for a specific set of NFTs
     * @param swapList The list of pairs and swap calldata
     * @param inputAmount The total amount of ETH to send
     * @param ethRecipient The address receiving excess ETH
     * @param nftRecipient The address receiving the NFTs from the pairs
     * @return remainingValue The unspent token amount
     */
    function _swapETHForSpecificNFTs(
        PairSwapSpecific[] calldata swapList,
        uint256 inputAmount,
        address payable ethRecipient,
        address nftRecipient
    ) internal virtual returns (uint256 remainingValue) {
        remainingValue = inputAmount;

        uint256 pairCost;
        CurveErrorCodes.Error error;

        // Do swaps
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            // Calculate the cost per swap first to send exact amount of ETH over, saves gas by avoiding the need to send back excess ETH
            (error,,, pairCost,,) = swapList[i].pair.getBuyNFTQuote(swapList[i].nftIds[0], swapList[i].nftIds.length);

            // Require no errors
            require(error == CurveErrorCodes.Error.OK, "Bonding curve error");

            // Total ETH taken from sender cannot exceed inputAmount
            // because otherwise the deduction from remainingValue will fail
            remainingValue -= swapList[i].pair.swapTokenForSpecificNFTs{value: pairCost}(
                swapList[i].nftIds, remainingValue, nftRecipient, true, msg.sender
            );

            unchecked {
                ++i;
            }
        }

        // Return remaining value to sender
        if (remainingValue > 0) {
            ethRecipient.safeTransferETH(remainingValue);
        }
    }

    /**
     * @notice Internal function used to swap an ERC20 token for specific NFTs
     * @dev Note that we don't need to query the pair's bonding curve first for pricing data because
     * we just calculate and take the required amount from the caller during swap time.
     * However, we can't "pull" ETH, which is why for the ETH->NFT swaps, we need to calculate the pricing info
     * to figure out how much the router should send to the pool.
     * @param swapList The list of pairs and swap calldata
     * @param inputAmount The total amount of ERC20 tokens to send
     * @param nftRecipient The address receiving the NFTs from the pairs
     * @return remainingValue The unspent token amount
     */
    function _swapERC20ForSpecificNFTs(PairSwapSpecific[] calldata swapList, uint256 inputAmount, address nftRecipient)
        internal
        virtual
        returns (uint256 remainingValue)
    {
        remainingValue = inputAmount;

        // Do swaps
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            // Tokens are transferred in by the pair calling router.pairTransferERC20From
            // Total tokens taken from sender cannot exceed inputAmount
            // because otherwise the deduction from remainingValue will fail
            remainingValue -= swapList[i].pair.swapTokenForSpecificNFTs(
                swapList[i].nftIds, remainingValue, nftRecipient, true, msg.sender
            );

            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Swaps NFTs for tokens, designed to be used for 1 token at a time
     * @dev Calling with multiple tokens is permitted, BUT minOutput will be
     * far from enough of a safety check because different tokens almost certainly have different unit prices.
     * @param swapList The list of pairs and swap calldata
     * @param minOutput The minimum number of tokens to be receieved from the swaps
     * @param tokenRecipient The address that receives the tokens
     * @return outputAmount The number of tokens to be received
     */
    function _swapNFTsForToken(PairSwapSpecific[] calldata swapList, uint256 minOutput, address payable tokenRecipient)
        internal
        virtual
        returns (uint256 outputAmount)
    {
        // Do swaps
        uint256 numSwaps = swapList.length;
        for (uint256 i; i < numSwaps;) {
            // Do the swap for token and then update outputAmount
            // Note: minExpectedTokenOutput is set to 0 since we're doing an aggregate slippage check below
            outputAmount += swapList[i].pair.swapNFTsForToken(swapList[i].nftIds, 0, tokenRecipient, true, msg.sender);

            unchecked {
                ++i;
            }
        }

        // Aggregate slippage check
        require(outputAmount >= minOutput, "outputAmount too low");
    }
}

// src/LSSVMPairERC20.sol

/**
 * @title An NFT/Token pair where the token is an ERC20
 * @author boredGenius, 0xmons, 0xCygaar
 */
abstract contract LSSVMPairERC20 is LSSVMPair {
    using SafeTransferLib for ERC20;

    error LSSVMPairERC20__RoyaltyNotPaid();
    error LSSVMPairERC20__MsgValueNotZero();
    error LSSVMPairERC20__AssetRecipientNotPaid();

    /**
     * @notice Returns the ERC20 token associated with the pair
     * @dev See LSSVMPairCloner for an explanation on how this works
     * @dev The last 20 bytes of the immutable data contain the ERC20 token address
     */
    function token() public pure returns (ERC20 _token) {
        assembly {
            _token := shr(0x60, calldataload(sub(calldatasize(), 20)))
        }
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function _pullTokenInputs(
        uint256 inputAmountExcludingRoyalty,
        uint256[] memory royaltyAmounts,
        address payable[] memory royaltyRecipients,
        uint256, /* royaltyTotal */
        uint256 tradeFeeAmount,
        bool isRouter,
        address routerCaller,
        uint256 protocolFee
    ) internal override {
        address _assetRecipient = getAssetRecipient();

        // Transfer tokens
        if (isRouter) {
            // Verify if router is allowed
            // Locally scoped to avoid stack too deep
            {
                (bool routerAllowed,) = factory().routerStatus(LSSVMRouter(payable(msg.sender)));
                if (!routerAllowed) revert LSSVMPair__NotRouter();
            }

            // Cache state and then call router to transfer tokens from user
            uint256 beforeBalance = token().balanceOf(_assetRecipient);
            LSSVMRouter(payable(msg.sender)).pairTransferERC20From(
                token(), routerCaller, _assetRecipient, inputAmountExcludingRoyalty - protocolFee
            );

            // Verify token transfer (protect pair against malicious router)
            ERC20 token_ = token();
            if (token_.balanceOf(_assetRecipient) - beforeBalance != (inputAmountExcludingRoyalty - protocolFee)) {
                revert LSSVMPairERC20__AssetRecipientNotPaid();
            }

            // Transfer royalties (if they exist)
            for (uint256 i; i < royaltyRecipients.length;) {
                beforeBalance = token_.balanceOf(royaltyRecipients[i]);
                LSSVMRouter(payable(msg.sender)).pairTransferERC20From(
                    token_, routerCaller, royaltyRecipients[i], royaltyAmounts[i]
                );
                if (token_.balanceOf(royaltyRecipients[i]) - beforeBalance != royaltyAmounts[i]) {
                    revert LSSVMPairERC20__RoyaltyNotPaid();
                }
                unchecked {
                    ++i;
                }
            }

            // Take protocol fee (if it exists)
            if (protocolFee != 0) {
                LSSVMRouter(payable(msg.sender)).pairTransferERC20From(
                    token_, routerCaller, address(factory()), protocolFee
                );
            }
        } else {
            // Transfer tokens directly (sans the protocol fee)
            ERC20 token_ = token();
            token_.safeTransferFrom(msg.sender, _assetRecipient, inputAmountExcludingRoyalty - protocolFee);

            // Transfer royalties (if they exists)
            for (uint256 i; i < royaltyRecipients.length;) {
                token_.safeTransferFrom(msg.sender, royaltyRecipients[i], royaltyAmounts[i]);
                unchecked {
                    ++i;
                }
            }

            // Take protocol fee (if it exists)
            if (protocolFee != 0) {
                token_.safeTransferFrom(msg.sender, address(factory()), protocolFee);
            }
        }
        // Send trade fee if it exists, is TRADE pool, and fee recipient != pool address
        // @dev: (note that tokens are sent from the pool and not the caller)
        if (poolType() == PoolType.TRADE && tradeFeeAmount != 0) {
            address payable _feeRecipient = getFeeRecipient();
            if (_feeRecipient != _assetRecipient) {
                token().safeTransfer(_feeRecipient, tradeFeeAmount);
            }
        }
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function _refundTokenToSender(uint256 inputAmount) internal override {
        // Do nothing since we transferred the exact input amount
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function _sendTokenOutput(address payable tokenRecipient, uint256 outputAmount) internal override {
        // Send tokens to caller
        if (outputAmount != 0) {
            token().safeTransfer(tokenRecipient, outputAmount);
        }
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function withdrawERC20(ERC20 a, uint256 amount) external override onlyOwner {
        a.safeTransfer(msg.sender, amount);

        if (a == token()) {
            // emit event since it is the pair token
            emit TokenWithdrawal(amount);
        }
    }

    function _preCallCheck(address target) internal pure override {
        if (target == address(token())) revert LSSVMPair__TargetNotAllowed();
    }
}

// src/LSSVMPairETH.sol

/**
 * @title An NFT/Token pair where the token is ETH
 * @author boredGenius, 0xmons, 0xCygaar
 */
abstract contract LSSVMPairETH is LSSVMPair {
    using SafeTransferLib for address payable;
    using SafeTransferLib for ERC20;

    error LSSVMPairETH__InsufficientInput();

    /**
     * @inheritdoc LSSVMPair
     */
    function _pullTokenInputs(
        uint256 inputAmountExcludingRoyalty,
        uint256[] memory royaltyAmounts,
        address payable[] memory royaltyRecipients,
        uint256 royaltyTotal,
        uint256 tradeFeeAmount,
        bool, /*isRouter*/
        address, /*routerCaller*/
        uint256 protocolFee
    ) internal override {
        // Require that the input amount is sufficient to pay for the sale amount, royalties, and fees
        if (msg.value < (royaltyTotal + inputAmountExcludingRoyalty)) revert LSSVMPairETH__InsufficientInput();

        // Transfer inputAmountExcludingRoyalty ETH to assetRecipient if it has been set
        address payable _assetRecipient = getAssetRecipient();

        // Attempt to transfer trade fees only if TRADE pool and they exist
        if (poolType() == PoolType.TRADE && tradeFeeAmount != 0) {
            address payable _feeRecipient = getFeeRecipient();

            // Only send and deduct tradeFeeAmount if the fee recipient is not the asset recipient (i.e. the pool)
            if (_feeRecipient != _assetRecipient) {
                inputAmountExcludingRoyalty -= tradeFeeAmount;
                _feeRecipient.safeTransferETH(tradeFeeAmount);
            }
            // In the else case, we would want to ensure that inputAmountExcludingRoyalty >= tradeFeeAmount / 2
            // to avoid underpaying the trade fee, but it is always true because the max royalty
            // is 25%, the max protocol fee is 10%, and the max trade fee is 50%, meaning they can
            // never add up to more than 100%.
        }

        if (_assetRecipient != address(this)) {
            _assetRecipient.safeTransferETH(inputAmountExcludingRoyalty - protocolFee);
        }

        // Transfer royalties
        for (uint256 i; i < royaltyRecipients.length;) {
            royaltyRecipients[i].safeTransferETH(royaltyAmounts[i]);
            unchecked {
                ++i;
            }
        }

        // Take protocol fee
        if (protocolFee != 0) {
            payable(address(factory())).safeTransferETH(protocolFee);
        }
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function _refundTokenToSender(uint256 inputAmount) internal override {
        // Give excess ETH back to caller
        if (msg.value > inputAmount) {
            payable(msg.sender).safeTransferETH(msg.value - inputAmount);
        }
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function _sendTokenOutput(address payable tokenRecipient, uint256 outputAmount) internal override {
        // Send ETH to caller
        if (outputAmount != 0) {
            tokenRecipient.safeTransferETH(outputAmount);
        }
    }

    /**
     * @notice Withdraws all token owned by the pair to the owner address.
     * @dev Only callable by the owner.
     */
    function withdrawAllETH() external onlyOwner {
        withdrawETH(address(this).balance);
    }

    /**
     * @notice Withdraws a specified amount of token owned by the pair to the owner address.
     * @dev Only callable by the owner.
     * @param amount The amount of token to send to the owner. If the pair's balance is less than
     * this value, the transaction will be reverted.
     */
    function withdrawETH(uint256 amount) public onlyOwner {
        payable(msg.sender).safeTransferETH(amount);

        // emit event since ETH is the pair token
        emit TokenWithdrawal(amount);
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function withdrawERC20(ERC20 a, uint256 amount) external override onlyOwner {
        a.safeTransfer(msg.sender, amount);
    }

    /**
     * @dev All ETH transfers into the pair are accepted. This is the main method
     * for the owner to top up the pair's token reserves.
     */
    receive() external payable {
        emit TokenDeposit(msg.value);
    }

    /**
     * @dev All ETH transfers into the pair are accepted. This is the main method
     * for the owner to top up the pair's token reserves.
     */
    fallback() external payable {
        // Only allow calls without function selector
        require(msg.data.length == _immutableParamsLength());
        emit TokenDeposit(msg.value);
    }

    function _preCallCheck(address) internal pure override {}
}

// src/erc1155/LSSVMPairERC1155.sol

/**
 * @title LSSVMPairERC1155
 * @author boredGenius, 0xmons, 0xCygaar
 * @notice An NFT/Token pair for an ERC1155 NFT where NFTs with the same ID are considered fungible.
 */
abstract contract LSSVMPairERC1155 is LSSVMPair {
    /**
     * External state-changing functions
     */

    /**
     * @notice Sends token to the pair in exchange for any `numNFTs` NFTs
     * @dev To compute the amount of token to send, call bondingCurve.getBuyInfo.
     * This swap function is meant for users who are ID agnostic
     * @param numNFTs The number of NFTs to purchase
     * @param maxExpectedTokenInput The maximum acceptable cost from the sender. If the actual
     * amount is greater than this value, the transaction will be reverted.
     * @param nftRecipient The recipient of the NFTs
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for ETH pairs.
     * @return inputAmount The amount of token used for purchase
     */
    function swapTokenForSpecificNFTs(
        uint256[] calldata numNFTs,
        uint256 maxExpectedTokenInput,
        address nftRecipient,
        bool isRouter,
        address routerCaller
    ) external payable virtual override returns (uint256) {
        // Store locally to remove extra calls
        factory().openLock();

        // Input validation
        {
            if (poolType() == PoolType.TOKEN) revert LSSVMPair__WrongPoolType();
            if (numNFTs.length != 1 || numNFTs[0] == 0) revert LSSVMPair__ZeroSwapAmount();
        }

        // Call bonding curve for pricing information
        uint256 tradeFee;
        uint256 protocolFee;
        uint256 inputAmountExcludingRoyalty;
        (tradeFee, protocolFee, inputAmountExcludingRoyalty) =
            _calculateBuyInfoAndUpdatePoolParams(numNFTs[0], bondingCurve(), factory());

        (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal) =
            _calculateRoyalties(nftId(), inputAmountExcludingRoyalty - protocolFee - tradeFee);

        // Revert if the input amount is too large
        if (royaltyTotal + inputAmountExcludingRoyalty > maxExpectedTokenInput) {
            revert LSSVMPair__DemandedInputTooLarge();
        }

        _pullTokenInputs({
            inputAmountExcludingRoyalty: inputAmountExcludingRoyalty,
            royaltyRecipients: royaltyRecipients,
            royaltyAmounts: royaltyAmounts,
            royaltyTotal: royaltyTotal,
            tradeFeeAmount: 2 * tradeFee,
            isRouter: isRouter,
            routerCaller: routerCaller,
            protocolFee: protocolFee
        });

        _sendAnyNFTsToRecipient(IERC1155(nft()), nftRecipient, numNFTs[0]);

        _refundTokenToSender(royaltyTotal + inputAmountExcludingRoyalty);

        factory().closeLock();

        emit SwapNFTOutPair(royaltyTotal + inputAmountExcludingRoyalty, numNFTs[0]);

        return (royaltyTotal + inputAmountExcludingRoyalty);
    }

    /**
     * @notice Sends a set of NFTs to the pair in exchange for token
     * @dev To compute the amount of token to that will be received, call bondingCurve.getSellInfo.
     * @param numNFTs The number of NFTs to swap
     * @param minExpectedTokenOutput The minimum acceptable token received by the sender. If the actual
     * amount is less than this value, the transaction will be reverted.
     * @param tokenRecipient The recipient of the token output
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for ETH pairs.
     * @return outputAmount The amount of token received
     */
    function swapNFTsForToken(
        uint256[] calldata numNFTs, // @dev this is a bit hacky, to allow for better interop w/ other pair interfaces
        uint256 minExpectedTokenOutput,
        address payable tokenRecipient,
        bool isRouter,
        address routerCaller
    ) external virtual override returns (uint256 outputAmount) {
        // Store locally to remove extra calls
        ILSSVMPairFactoryLike _factory = factory();

        _factory.openLock();

        ICurve _bondingCurve = bondingCurve();

        // Input validation
        {
            if (poolType() == PoolType.NFT) revert LSSVMPair__WrongPoolType();
            if (numNFTs.length != 1 || numNFTs[0] == 0) revert LSSVMPair__ZeroSwapAmount();
        }

        // Call bonding curve for pricing information
        uint256 protocolFee;
        (protocolFee, outputAmount) = _calculateSellInfoAndUpdatePoolParams(numNFTs[0], _bondingCurve, _factory);

        // Compute royalties
        (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal) =
            _calculateRoyalties(nftId(), outputAmount);

        // Deduct royalties from outputAmount
        unchecked {
            // Safe because we already require outputAmount >= royaltyTotal in calculateRoyalties()
            outputAmount -= royaltyTotal;
        }

        if (outputAmount < minExpectedTokenOutput) revert LSSVMPair__OutputTooSmall();

        _takeNFTsFromSender(IERC1155(nft()), numNFTs[0], _factory, isRouter, routerCaller);

        _sendTokenOutput(tokenRecipient, outputAmount);

        for (uint256 i; i < royaltyRecipients.length;) {
            _sendTokenOutput(royaltyRecipients[i], royaltyAmounts[i]);
            unchecked {
                ++i;
            }
        }

        _sendTokenOutput(payable(address(_factory)), protocolFee);

        _factory.closeLock();

        emit SwapNFTInPair(outputAmount, numNFTs[0]);
    }

    /**
     * View functions
     */

    /**
     * @notice Returns the ERC-1155 NFT ID this pool uses
     */
    function nftId() public pure returns (uint256 id) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            id := calldataload(add(sub(calldatasize(), paramsLength), 61))
        }
    }

    /**
     * Internal functions
     */

    /**
     * @notice Sends some number of NFTs to a recipient address
     * @dev Even though we specify the NFT address here, this internal function is only
     * used to send NFTs associated with this specific pool.
     * @param _nft The address of the NFT to send
     * @param nftRecipient The receiving address for the NFTs
     * @param numNFTs The number of NFTs to send
     */
    function _sendAnyNFTsToRecipient(IERC1155 _nft, address nftRecipient, uint256 numNFTs) internal virtual {
        _nft.safeTransferFrom(address(this), nftRecipient, nftId(), numNFTs, bytes(""));
    }

    /**
     * @notice Takes NFTs from the caller and sends them into the pair's asset recipient
     * @dev This is used by the LSSVMPair's swapNFTForToken function.
     * @param _nft The NFT collection to take from
     * @param numNFTs The number of NFTs to take
     * @param isRouter Whether or not to use the router pull flow
     * @param routerCaller If the caller is a router, passes in which address to pull from (i.e. the router's caller)
     */
    function _takeNFTsFromSender(
        IERC1155 _nft,
        uint256 numNFTs,
        ILSSVMPairFactoryLike factory,
        bool isRouter,
        address routerCaller
    ) internal virtual {
        address _assetRecipient = getAssetRecipient();

        if (isRouter) {
            // Verify if router is allowed
            LSSVMRouter router = LSSVMRouter(payable(msg.sender));
            (bool routerAllowed,) = factory.routerStatus(router);
            if (!routerAllowed) revert LSSVMPair__NotRouter();

            uint256 _nftId = nftId();
            uint256 beforeBalance = _nft.balanceOf(_assetRecipient, _nftId);
            uint256[] memory ids = new uint256[](1);
            ids[0] = _nftId;
            uint256[] memory amounts = new uint256[](1);
            amounts[0] = numNFTs;
            router.pairTransferERC1155From(_nft, routerCaller, _assetRecipient, ids, amounts);
            if (_nft.balanceOf(_assetRecipient, _nftId) - beforeBalance != numNFTs) {
                revert LSSVMPair__NftNotTransferred();
            }
        } else {
            // Pull NFTs directly from sender
            _nft.safeTransferFrom(msg.sender, _assetRecipient, nftId(), numNFTs, bytes(""));
        }
    }

    /**
     * Owner functions
     */

    /**
     * @notice Rescues a specified set of NFTs owned by the pair to the owner address. Only callable by the owner.
     * @param a The NFT to transfer
     * @param nftIds The list of IDs of the NFTs to send to the owner
     */
    function withdrawERC721(IERC721 a, uint256[] calldata nftIds) external virtual override onlyOwner {
        uint256 numNFTs = nftIds.length;
        for (uint256 i; i < numNFTs;) {
            a.safeTransferFrom(address(this), msg.sender, nftIds[i]);
            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Transfers ERC1155 tokens from the pair to the owner. Only callable by the owner.
     * @param a The NFT to transfer
     * @param ids The NFT ids to transfer
     * @param amounts The amounts of each id to transfer
     */
    function withdrawERC1155(IERC1155 a, uint256[] calldata ids, uint256[] calldata amounts)
        external
        virtual
        override
        onlyOwner
    {
        if (a == IERC1155(nft())) {
            // Check if we need to emit an event for withdrawing the NFT this pool is trading
            uint256 _nftId = nftId();
            uint256 numNFTs = ids.length;
            uint256 numPairNFTsWithdrawn;
            for (uint256 i; i < numNFTs;) {
                if (ids[i] == _nftId) {
                    numPairNFTsWithdrawn += amounts[i];
                }
                unchecked {
                    ++i;
                }
            }

            if (numPairNFTsWithdrawn != 0) {
                // Only emit for the pair's NFT
                emit NFTWithdrawal(numPairNFTsWithdrawn);
            }
        }

        a.safeBatchTransferFrom(address(this), msg.sender, ids, amounts, bytes(""));
    }
}

// src/lib/LSSVMPairCloner.sol

library LSSVMPairCloner {
    /**
     * @dev Deploys and returns the address of a clone that mimics the behaviour of `implementation`.
     *
     * This function uses the create opcode, which should never revert.
     *
     * During the delegate call, extra data is copied into the calldata which can then be
     * accessed by the implementation contract.
     *
     * @return instance The address of the new pair instance
     */
    function cloneERC721ETHPair(
        address implementation,
        ILSSVMPairFactoryLike factory,
        ICurve bondingCurve,
        IERC721 nft,
        uint8 poolType,
        address propertyChecker
    ) internal returns (address instance) {
        assembly {
            let ptr := mload(0x40)

            // -------------------------------------------------------------------------------------------------------------
            // CREATION (9 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // creation size = 09
            // runtime size = 86
            // 60 runtime  | PUSH1 runtime (r)     | r                       | –
            // 3d          | RETURNDATASIZE        | 0 r                     | –
            // 81          | DUP2                  | r 0 r                   | –
            // 60 creation | PUSH1 creation (c)    | c r 0 r                 | –
            // 3d          | RETURNDATASIZE        | 0 c r 0 r               | –
            // 39          | CODECOPY              | 0 r                     | [0-runSize): runtime code
            // f3          | RETURN                |                         | [0-runSize): runtime code

            // -------------------------------------------------------------------------------------------------------------
            // RUNTIME (53 bytes of code + 81 bytes of extra data = 134 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // extra data size = 51
            // 3d          | RETURNDATASIZE        | 0                       | –
            // 3d          | RETURNDATASIZE        | 0 0                     | –
            // 3d          | RETURNDATASIZE        | 0 0 0                   | –
            // 3d          | RETURNDATASIZE        | 0 0 0 0                 | –
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | –
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | –
            // 3d          | RETURNDATASIZE        | 0 0 cds 0 0 0 0         | –
            // 37          | CALLDATACOPY          | 0 0 0 0                 | [0, cds) = calldata
            // 60 extra    | PUSH1 extra           | extra 0 0 0 0           | [0, cds) = calldata
            // 60 0x35     | PUSH1 0x35            | 0x35 extra 0 0 0 0      | [0, cds) = calldata // 0x35 (53) is runtime size - data
            // 36          | CALLDATASIZE          | cds 0x35 extra 0 0 0 0  | [0, cds) = calldata
            // 39          | CODECOPY              | 0 0 0 0                 | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 60 extra    | PUSH1 extra           | extra cds 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 01          | ADD                   | cds+extra 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0 0      | [0, cds) = calldata, [cds, cds+0x35) = extraData
            mstore(ptr, hex"60863d8160093d39f33d3d3d3d363d3d37605160353639366051013d73000000")
            mstore(add(ptr, 0x1d), shl(0x60, implementation))

            // 5a          | GAS                   | gas addr 0 cds 0 0 0 0  | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // f4          | DELEGATECALL          | success 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds success 0 0         | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds rds success 0 0     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 93          | SWAP4                 | 0 rds success 0 rds     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 80          | DUP1                  | 0 0 rds success 0 rds   | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3e          | RETURNDATACOPY        | success 0 rds           | [0, rds) = return data (there might be some irrelevant leftovers in memory [rds, cds+0x35) when rds < cds+0x35)
            // 60 0x33     | PUSH1 0x33            | 0x33 success 0 rds      | [0, rds) = return data
            // 57          | JUMPI                 | 0 rds                   | [0, rds) = return data
            // fd          | REVERT                | –                       | [0, rds) = return data
            // 5b          | JUMPDEST              | 0 rds                   | [0, rds) = return data
            // f3          | RETURN                | –                       | [0, rds) = return data
            mstore(add(ptr, 0x31), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")

            // -------------------------------------------------------------------------------------------------------------
            // EXTRA DATA (81 bytes)
            // -------------------------------------------------------------------------------------------------------------

            mstore(add(ptr, 0x3e), shl(0x60, factory))
            mstore(add(ptr, 0x52), shl(0x60, bondingCurve))
            mstore(add(ptr, 0x66), shl(0x60, nft))
            mstore8(add(ptr, 0x7a), poolType)
            mstore(add(ptr, 0x7b), shl(0x60, propertyChecker))

            // -------------------------------------------------------------------------------------------------------------
            // Total length is 143 (8f) bytes
            // -------------------------------------------------------------------------------------------------------------

            instance := create(0, ptr, 0x8f)
        }
    }

    /**
     * @dev Deploys and returns the address of a clone that mimics the behaviour of `implementation`.
     *
     * This function uses the create opcode, which should never revert.
     *
     * During the delegate call, extra data is copied into the calldata which can then be
     * accessed by the implementation contract.
     *
     * @return instance The address of the new pair instance
     */
    function cloneERC721ERC20Pair(
        address implementation,
        ILSSVMPairFactoryLike factory,
        ICurve bondingCurve,
        IERC721 nft,
        uint8 poolType,
        address propertyChecker,
        ERC20 token
    ) internal returns (address instance) {
        assembly {
            let ptr := mload(0x40)

            // -------------------------------------------------------------------------------------------------------------
            // CREATION (9 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // creation size = 09
            // runtime size = 9a
            // 60 runtime  | PUSH1 runtime (r)     | r                       | –
            // 3d          | RETURNDATASIZE        | 0 r                     | –
            // 81          | DUP2                  | r 0 r                   | –
            // 60 creation | PUSH1 creation (c)    | c r 0 r                 | –
            // 3d          | RETURNDATASIZE        | 0 c r 0 r               | –
            // 39          | CODECOPY              | 0 r                     | [0-runSize): runtime code
            // f3          | RETURN                |                         | [0-runSize): runtime code

            // -------------------------------------------------------------------------------------------------------------
            // RUNTIME (53 bytes of code + 101 bytes of extra data = 154 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // extra data size = 65
            // 3d          | RETURNDATASIZE        | 0                       | –
            // 3d          | RETURNDATASIZE        | 0 0                     | –
            // 3d          | RETURNDATASIZE        | 0 0 0                   | –
            // 3d          | RETURNDATASIZE        | 0 0 0 0                 | –
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | –
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | –
            // 3d          | RETURNDATASIZE        | 0 0 cds 0 0 0 0         | –
            // 37          | CALLDATACOPY          | 0 0 0 0                 | [0, cds) = calldata
            // 60 extra    | PUSH1 extra           | extra 0 0 0 0           | [0, cds) = calldata
            // 60 0x35     | PUSH1 0x35            | 0x35 extra 0 0 0 0      | [0, cds) = calldata // 0x35 (53) is runtime size - data
            // 36          | CALLDATASIZE          | cds 0x35 extra 0 0 0 0  | [0, cds) = calldata
            // 39          | CODECOPY              | 0 0 0 0                 | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 60 extra    | PUSH1 extra           | extra cds 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 01          | ADD                   | cds+extra 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0 0      | [0, cds) = calldata, [cds, cds+0x35) = extraData
            mstore(ptr, hex"609a3d8160093d39f33d3d3d3d363d3d37606560353639366065013d73000000")
            mstore(add(ptr, 0x1d), shl(0x60, implementation))

            // 5a          | GAS                   | gas addr 0 cds 0 0 0 0  | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // f4          | DELEGATECALL          | success 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds success 0 0         | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds rds success 0 0     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 93          | SWAP4                 | 0 rds success 0 rds     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 80          | DUP1                  | 0 0 rds success 0 rds   | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3e          | RETURNDATACOPY        | success 0 rds           | [0, rds) = return data (there might be some irrelevant leftovers in memory [rds, cds+0x37) when rds < cds+0x37)
            // 60 0x33     | PUSH1 0x33            | 0x33 success 0 rds      | [0, rds) = return data
            // 57          | JUMPI                 | 0 rds                   | [0, rds) = return data
            // fd          | REVERT                | –                       | [0, rds) = return data
            // 5b          | JUMPDEST              | 0 rds                   | [0, rds) = return data
            // f3          | RETURN                | –                       | [0, rds) = return data
            mstore(add(ptr, 0x31), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")

            // -------------------------------------------------------------------------------------------------------------
            // EXTRA DATA (101 bytes)
            // -------------------------------------------------------------------------------------------------------------

            mstore(add(ptr, 0x3e), shl(0x60, factory))
            mstore(add(ptr, 0x52), shl(0x60, bondingCurve))
            mstore(add(ptr, 0x66), shl(0x60, nft))
            mstore8(add(ptr, 0x7a), poolType)
            mstore(add(ptr, 0x7b), shl(0x60, propertyChecker))
            mstore(add(ptr, 0x8f), shl(0x60, token))

            // -------------------------------------------------------------------------------------------------------------
            // Total length is 163 (a3) bytes
            // -------------------------------------------------------------------------------------------------------------

            instance := create(0, ptr, 0xa3)
        }
    }

    /**
     * @notice Checks if a contract is a clone of a LSSVMPairETH.
     * @dev Only checks the runtime bytecode, does not check the extra data.
     * @param factory the factory that deployed the clone
     * @param implementation the LSSVMPairETH implementation contract
     * @param query the contract to check
     * @return result True if the contract is a clone, false otherwise
     */
    function isERC721ETHPairClone(address factory, address implementation, address query)
        internal
        view
        returns (bool result)
    {
        // solhint-disable-next-line no-inline-assembly
        assembly {
            let ptr := mload(0x40)
            mstore(ptr, hex"3d3d3d3d363d3d37605160353639366051013d73000000000000000000000000")
            mstore(add(ptr, 0x14), shl(0x60, implementation))
            mstore(add(ptr, 0x28), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")
            mstore(add(ptr, 0x35), shl(0x60, factory))

            // compare expected bytecode with that of the queried contract
            let other := add(ptr, 0x49)
            extcodecopy(query, other, 0, 0x49)
            result :=
                and(
                    eq(mload(ptr), mload(other)),
                    and(
                        eq(mload(add(ptr, 0x20)), mload(add(other, 0x20))),
                        eq(mload(add(ptr, 0x29)), mload(add(other, 0x29)))
                    )
                )
        }
    }

    /**
     * @notice Checks if a contract is a clone of a LSSVMPairERC20.
     * @dev Only checks the runtime bytecode, does not check the extra data.
     * @param implementation the LSSVMPairERC20 implementation contract
     * @param query the contract to check
     * @return result True if the contract is a clone, false otherwise
     */
    function isERC721ERC20PairClone(address factory, address implementation, address query)
        internal
        view
        returns (bool result)
    {
        // solhint-disable-next-line no-inline-assembly
        assembly {
            let ptr := mload(0x40)
            mstore(ptr, hex"3d3d3d3d363d3d37606560353639366065013d73000000000000000000000000")
            mstore(add(ptr, 0x14), shl(0x60, implementation))
            mstore(add(ptr, 0x28), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")
            mstore(add(ptr, 0x35), shl(0x60, factory))

            // compare expected bytecode with that of the queried contract
            let other := add(ptr, 0x49)
            extcodecopy(query, other, 0, 0x49)
            result :=
                and(
                    eq(mload(ptr), mload(other)),
                    and(
                        eq(mload(add(ptr, 0x20)), mload(add(other, 0x20))),
                        eq(mload(add(ptr, 0x29)), mload(add(other, 0x29)))
                    )
                )
        }
    }

    /**
     * @dev Deploys and returns the address of a clone that mimics the behaviour of `implementation`.
     *
     * This function uses the create opcode, which should never revert.
     *
     * During the delegate call, extra data is copied into the calldata which can then be
     * accessed by the implementation contract.
     *
     * @return instance The address of the new pair instance
     */
    function cloneERC1155ETHPair(
        address implementation,
        ILSSVMPairFactoryLike factory,
        ICurve bondingCurve,
        IERC1155 nft,
        uint8 poolType,
        uint256 nftId
    ) internal returns (address instance) {
        assembly {
            let ptr := mload(0x40)

            // -------------------------------------------------------------------------------------------------------------
            // CREATION (9 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // creation size = 09
            // runtime size = 92
            // 60 runtime  | PUSH1 runtime (r)     | r                       | –
            // 3d          | RETURNDATASIZE        | 0 r                     | –
            // 81          | DUP2                  | r 0 r                   | –
            // 60 creation | PUSH1 creation (c)    | c r 0 r                 | –
            // 3d          | RETURNDATASIZE        | 0 c r 0 r               | –
            // 39          | CODECOPY              | 0 r                     | [0-runSize): runtime code
            // f3          | RETURN                |                         | [0-runSize): runtime code

            // -------------------------------------------------------------------------------------------------------------
            // RUNTIME (53 bytes of code + 93 bytes of extra data = 146 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // extra data size = 5d
            // 3d          | RETURNDATASIZE        | 0                       | –
            // 3d          | RETURNDATASIZE        | 0 0                     | –
            // 3d          | RETURNDATASIZE        | 0 0 0                   | –
            // 3d          | RETURNDATASIZE        | 0 0 0 0                 | –
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | –
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | –
            // 3d          | RETURNDATASIZE        | 0 0 cds 0 0 0 0         | –
            // 37          | CALLDATACOPY          | 0 0 0 0                 | [0, cds) = calldata
            // 60 extra    | PUSH1 extra           | extra 0 0 0 0           | [0, cds) = calldata
            // 60 0x35     | PUSH1 0x35            | 0x35 extra 0 0 0 0      | [0, cds) = calldata // 0x35 (53) is runtime size - data
            // 36          | CALLDATASIZE          | cds 0x35 extra 0 0 0 0  | [0, cds) = calldata
            // 39          | CODECOPY              | 0 0 0 0                 | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 60 extra    | PUSH1 extra           | extra cds 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 01          | ADD                   | cds+extra 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0 0      | [0, cds) = calldata, [cds, cds+0x35) = extraData
            mstore(ptr, hex"60923d8160093d39f33d3d3d3d363d3d37605d6035363936605d013d73000000")
            mstore(add(ptr, 0x1d), shl(0x60, implementation))

            // 5a          | GAS                   | gas addr 0 cds 0 0 0 0  | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // f4          | DELEGATECALL          | success 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds success 0 0         | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds rds success 0 0     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 93          | SWAP4                 | 0 rds success 0 rds     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 80          | DUP1                  | 0 0 rds success 0 rds   | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3e          | RETURNDATACOPY        | success 0 rds           | [0, rds) = return data (there might be some irrelevant leftovers in memory [rds, cds+0x37) when rds < cds+0x37)
            // 60 0x33     | PUSH1 0x33            | 0x33 success 0 rds      | [0, rds) = return data
            // 57          | JUMPI                 | 0 rds                   | [0, rds) = return data
            // fd          | REVERT                | –                       | [0, rds) = return data
            // 5b          | JUMPDEST              | 0 rds                   | [0, rds) = return data
            // f3          | RETURN                | –                       | [0, rds) = return data
            mstore(add(ptr, 0x31), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")

            // -------------------------------------------------------------------------------------------------------------
            // EXTRA DATA (93 bytes)
            // -------------------------------------------------------------------------------------------------------------

            mstore(add(ptr, 0x3e), shl(0x60, factory))
            mstore(add(ptr, 0x52), shl(0x60, bondingCurve))
            mstore(add(ptr, 0x66), shl(0x60, nft))
            mstore8(add(ptr, 0x7a), poolType)
            mstore(add(ptr, 0x7b), nftId)

            instance := create(0, ptr, 0x9b)
        }
    }

    /**
     * @dev Deploys and returns the address of a clone that mimics the behaviour of `implementation`.
     *
     * This function uses the create opcode, which should never revert.
     *
     * During the delegate call, extra data is copied into the calldata which can then be
     * accessed by the implementation contract.
     *
     * @return instance The address of the new pair instance
     */
    function cloneERC1155ERC20Pair(
        address implementation,
        ILSSVMPairFactoryLike factory,
        ICurve bondingCurve,
        IERC1155 nft,
        uint8 poolType,
        uint256 nftId,
        ERC20 token
    ) internal returns (address instance) {
        assembly {
            let ptr := mload(0x40)

            // -------------------------------------------------------------------------------------------------------------
            // CREATION (9 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // creation size = 09
            // runtime size = a6
            // 60 runtime  | PUSH1 runtime (r)     | r                       | –
            // 3d          | RETURNDATASIZE        | 0 r                     | –
            // 81          | DUP2                  | r 0 r                   | –
            // 60 creation | PUSH1 creation (c)    | c r 0 r                 | –
            // 3d          | RETURNDATASIZE        | 0 c r 0 r               | –
            // 39          | CODECOPY              | 0 r                     | [0-runSize): runtime code
            // f3          | RETURN                |                         | [0-runSize): runtime code

            // -------------------------------------------------------------------------------------------------------------
            // RUNTIME (53 bytes of code + 113 bytes of extra data = 166 bytes)
            // -------------------------------------------------------------------------------------------------------------

            // extra data size = 71
            // 3d          | RETURNDATASIZE        | 0                       | –
            // 3d          | RETURNDATASIZE        | 0 0                     | –
            // 3d          | RETURNDATASIZE        | 0 0 0                   | –
            // 3d          | RETURNDATASIZE        | 0 0 0 0                 | –
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | –
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | –
            // 3d          | RETURNDATASIZE        | 0 0 cds 0 0 0 0         | –
            // 37          | CALLDATACOPY          | 0 0 0 0                 | [0, cds) = calldata
            // 60 extra    | PUSH1 extra           | extra 0 0 0 0           | [0, cds) = calldata
            // 60 0x35     | PUSH1 0x35            | 0x35 extra 0 0 0 0      | [0, cds) = calldata // 0x35 (53) is runtime size - data
            // 36          | CALLDATASIZE          | cds 0x35 extra 0 0 0 0  | [0, cds) = calldata
            // 39          | CODECOPY              | 0 0 0 0                 | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 36          | CALLDATASIZE          | cds 0 0 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 60 extra    | PUSH1 extra           | extra cds 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 01          | ADD                   | cds+extra 0 0 0 0       | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | 0 cds 0 0 0 0           | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0 0      | [0, cds) = calldata, [cds, cds+0x35) = extraData
            mstore(ptr, hex"60a63d8160093d39f33d3d3d3d363d3d37607160353639366071013d73000000")
            mstore(add(ptr, 0x1d), shl(0x60, implementation))

            // 5a          | GAS                   | gas addr 0 cds 0 0 0 0  | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // f4          | DELEGATECALL          | success 0 0             | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds success 0 0         | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3d          | RETURNDATASIZE        | rds rds success 0 0     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 93          | SWAP4                 | 0 rds success 0 rds     | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 80          | DUP1                  | 0 0 rds success 0 rds   | [0, cds) = calldata, [cds, cds+0x35) = extraData
            // 3e          | RETURNDATACOPY        | success 0 rds           | [0, rds) = return data (there might be some irrelevant leftovers in memory [rds, cds+0x37) when rds < cds+0x37)
            // 60 0x33     | PUSH1 0x33            | 0x33 success 0 rds      | [0, rds) = return data
            // 57          | JUMPI                 | 0 rds                   | [0, rds) = return data
            // fd          | REVERT                | –                       | [0, rds) = return data
            // 5b          | JUMPDEST              | 0 rds                   | [0, rds) = return data
            // f3          | RETURN                | –                       | [0, rds) = return data
            mstore(add(ptr, 0x31), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")

            // -------------------------------------------------------------------------------------------------------------
            // EXTRA DATA (113 bytes)
            // -------------------------------------------------------------------------------------------------------------

            mstore(add(ptr, 0x3e), shl(0x60, factory))
            mstore(add(ptr, 0x52), shl(0x60, bondingCurve))
            mstore(add(ptr, 0x66), shl(0x60, nft))
            mstore8(add(ptr, 0x7a), poolType)
            mstore(add(ptr, 0x7b), nftId)
            mstore(add(ptr, 0x9b), shl(0x60, token))

            instance := create(0, ptr, 0xaf)
        }
    }

    /**
     * @notice Checks if a contract is a clone of a LSSVMPairERC1155ETH.
     * @dev Only checks the runtime bytecode, does not check the extra data.
     * @param factory the factory that deployed the clone
     * @param implementation the LSSVMPairERC1155ETH implementation contract
     * @param query the contract to check
     * @return result True if the contract is a clone, false otherwise
     */
    function isERC1155ETHPairClone(address factory, address implementation, address query)
        internal
        view
        returns (bool result)
    {
        // solhint-disable-next-line no-inline-assembly
        assembly {
            let ptr := mload(0x40)
            mstore(ptr, hex"3d3d3d3d363d3d37605d6035363936605d013d73000000000000000000000000")
            mstore(add(ptr, 0x14), shl(0x60, implementation))
            mstore(add(ptr, 0x28), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")
            mstore(add(ptr, 0x35), shl(0x60, factory))

            // compare expected bytecode with that of the queried contract
            let other := add(ptr, 0x49)
            extcodecopy(query, other, 0, 0x49)
            result :=
                and(
                    eq(mload(ptr), mload(other)),
                    and(
                        eq(mload(add(ptr, 0x20)), mload(add(other, 0x20))),
                        eq(mload(add(ptr, 0x29)), mload(add(other, 0x29)))
                    )
                )
        }
    }

    /**
     * @notice Checks if a contract is a clone of a LSSVMPairERC1155ERC20.
     * @dev Only checks the runtime bytecode, does not check the extra data.
     * @param implementation the LSSVMPairERC1155ERC20 implementation contract
     * @param query the contract to check
     * @return result True if the contract is a clone, false otherwise
     */
    function isERC1155ERC20PairClone(address factory, address implementation, address query)
        internal
        view
        returns (bool result)
    {
        // solhint-disable-next-line no-inline-assembly
        assembly {
            let ptr := mload(0x40)
            mstore(ptr, hex"3d3d3d3d363d3d37607160353639366071013d73000000000000000000000000")
            mstore(add(ptr, 0x14), shl(0x60, implementation))
            mstore(add(ptr, 0x28), hex"5af43d3d93803e603357fd5bf300000000000000000000000000000000000000")
            mstore(add(ptr, 0x35), shl(0x60, factory))

            // compare expected bytecode with that of the queried contract
            let other := add(ptr, 0x49)
            extcodecopy(query, other, 0, 0x49)
            result :=
                and(
                    eq(mload(ptr), mload(other)),
                    and(
                        eq(mload(add(ptr, 0x20)), mload(add(other, 0x20))),
                        eq(mload(add(ptr, 0x29)), mload(add(other, 0x29)))
                    )
                )
        }
    }
}

// src/erc721/LSSVMPairERC721.sol

/**
 * @title LSSVMPairERC721
 * @author boredGenius, 0xmons, 0xCygaar
 * @notice An NFT/Token pair for an ERC721 NFT
 */
abstract contract LSSVMPairERC721 is LSSVMPair {
    error LSSVMPairERC721__PropertyCheckFailed();
    error LSSVMPairERC721__NeedPropertyChecking();

    /**
     * External state-changing functions
     */

    /**
     * @inheritdoc LSSVMPair
     */
    function swapTokenForSpecificNFTs(
        uint256[] calldata nftIds,
        uint256 maxExpectedTokenInput,
        address nftRecipient,
        bool isRouter,
        address routerCaller
    ) external payable virtual override returns (uint256) {
        // Store locally to remove extra calls
        factory().openLock();

        // Input validation
        {
            PoolType _poolType = poolType();
            if (_poolType == PoolType.TOKEN) revert LSSVMPair__WrongPoolType();
            if (nftIds.length == 0) revert LSSVMPair__ZeroSwapAmount();
        }

        // Call bonding curve for pricing information
        uint256 protocolFee;
        uint256 tradeFee;
        uint256 inputAmountExcludingRoyalty;
        (tradeFee, protocolFee, inputAmountExcludingRoyalty) =
            _calculateBuyInfoAndUpdatePoolParams(nftIds.length, bondingCurve(), factory());

        // Calculate royalties
        (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal) =
            _calculateRoyalties(nftIds[0], inputAmountExcludingRoyalty - protocolFee - tradeFee);

        // Revert if the input amount is too large
        if (royaltyTotal + inputAmountExcludingRoyalty > maxExpectedTokenInput) {
            revert LSSVMPair__DemandedInputTooLarge();
        }

        _pullTokenInputs({
            inputAmountExcludingRoyalty: inputAmountExcludingRoyalty,
            royaltyAmounts: royaltyAmounts,
            royaltyRecipients: royaltyRecipients,
            royaltyTotal: royaltyTotal,
            tradeFeeAmount: 2 * tradeFee,
            isRouter: isRouter,
            routerCaller: routerCaller,
            protocolFee: protocolFee
        });

        {
            _sendSpecificNFTsToRecipient(IERC721(nft()), nftRecipient, nftIds);
        }

        _refundTokenToSender(royaltyTotal + inputAmountExcludingRoyalty);

        factory().closeLock();

        emit SwapNFTOutPair(royaltyTotal + inputAmountExcludingRoyalty, nftIds);

        return (royaltyTotal + inputAmountExcludingRoyalty);
    }

    /**
     * @inheritdoc LSSVMPair
     */
    function swapNFTsForToken(
        uint256[] calldata nftIds,
        uint256 minExpectedTokenOutput,
        address payable tokenRecipient,
        bool isRouter,
        address routerCaller
    ) external virtual override returns (uint256 outputAmount) {
        if (propertyChecker() != address(0)) revert LSSVMPairERC721__NeedPropertyChecking();

        return _swapNFTsForToken(nftIds, minExpectedTokenOutput, tokenRecipient, isRouter, routerCaller);
    }

    /**
     * @notice Sends a set of NFTs to the pair in exchange for token
     * @dev To compute the amount of token to that will be received, call bondingCurve.getSellInfo.
     * @param nftIds The list of IDs of the NFTs to sell to the pair
     * @param minExpectedTokenOutput The minimum acceptable token received by the sender. If the actual
     * amount is less than this value, the transaction will be reverted.
     * @param tokenRecipient The recipient of the token output
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for
     * ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for
     * ETH pairs.
     * @param propertyCheckerParams Parameters to pass into the pair's underlying property checker
     * @return outputAmount The amount of token received
     */
    function swapNFTsForToken(
        uint256[] calldata nftIds,
        uint256 minExpectedTokenOutput,
        address payable tokenRecipient,
        bool isRouter,
        address routerCaller,
        bytes calldata propertyCheckerParams
    ) external virtual returns (uint256 outputAmount) {
        if (!IPropertyChecker(propertyChecker()).hasProperties(nftIds, propertyCheckerParams)) {
            revert LSSVMPairERC721__PropertyCheckFailed();
        }

        return _swapNFTsForToken(nftIds, minExpectedTokenOutput, tokenRecipient, isRouter, routerCaller);
    }

    /**
     * View functions
     */

    /**
     * @notice Returns the property checker address
     */
    function propertyChecker() public pure returns (address _propertyChecker) {
        uint256 paramsLength = _immutableParamsLength();
        assembly {
            _propertyChecker := shr(0x60, calldataload(add(sub(calldatasize(), paramsLength), 61)))
        }
    }

    /**
     * Internal functions
     */

    function _swapNFTsForToken(
        uint256[] calldata nftIds,
        uint256 minExpectedTokenOutput,
        address payable tokenRecipient,
        bool isRouter,
        address routerCaller
    ) internal virtual returns (uint256 outputAmount) {
        // Store locally to remove extra calls
        ILSSVMPairFactoryLike _factory = factory();

        _factory.openLock();

        // Input validation
        {
            PoolType _poolType = poolType();
            if (_poolType == PoolType.NFT) revert LSSVMPair__WrongPoolType();
            if (nftIds.length == 0) revert LSSVMPair__ZeroSwapAmount();
        }

        // Call bonding curve for pricing information
        uint256 protocolFee;
        (protocolFee, outputAmount) = _calculateSellInfoAndUpdatePoolParams(nftIds.length, bondingCurve(), _factory);

        // Compute royalties
        (address payable[] memory royaltyRecipients, uint256[] memory royaltyAmounts, uint256 royaltyTotal) =
            _calculateRoyalties(nftIds[0], outputAmount);

        // Deduct royalties from outputAmount
        unchecked {
            // Safe because we already require outputAmount >= royaltyTotal in calculateRoyalties()
            outputAmount -= royaltyTotal;
        }

        if (outputAmount < minExpectedTokenOutput) revert LSSVMPair__OutputTooSmall();

        _takeNFTsFromSender(IERC721(nft()), nftIds, _factory, isRouter, routerCaller);

        _sendTokenOutput(tokenRecipient, outputAmount);
        for (uint256 i; i < royaltyRecipients.length;) {
            _sendTokenOutput(royaltyRecipients[i], royaltyAmounts[i]);
            unchecked {
                ++i;
            }
        }

        _sendTokenOutput(payable(address(_factory)), protocolFee);

        _factory.closeLock();

        emit SwapNFTInPair(outputAmount, nftIds);
    }

    /**
     * @notice Sends specific NFTs to a recipient address
     * @dev Even though we specify the NFT address here, this internal function is only
     * used to send NFTs associated with this specific pool.
     * @param _nft The address of the NFT to send
     * @param nftRecipient The receiving address for the NFTs
     * @param nftIds The specific IDs of NFTs to send
     */
    function _sendSpecificNFTsToRecipient(IERC721 _nft, address nftRecipient, uint256[] calldata nftIds)
        internal
        virtual
    {
        // Send NFTs to recipient
        uint256 numNFTs = nftIds.length;
        for (uint256 i; i < numNFTs;) {
            _nft.transferFrom(address(this), nftRecipient, nftIds[i]);

            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Takes NFTs from the caller and sends them into the pair's asset recipient
     * @dev This is used by the LSSVMPair's swapNFTForToken function.
     * @param _nft The NFT collection to take from
     * @param nftIds The specific NFT IDs to take
     * @param isRouter True if calling from LSSVMRouter, false otherwise. Not used for ETH pairs.
     * @param routerCaller If isRouter is true, ERC20 tokens will be transferred from this address. Not used for ETH pairs.
     */
    function _takeNFTsFromSender(
        IERC721 _nft,
        uint256[] calldata nftIds,
        ILSSVMPairFactoryLike _factory,
        bool isRouter,
        address routerCaller
    ) internal virtual {
        {
            address _assetRecipient = getAssetRecipient();
            uint256 numNFTs = nftIds.length;

            if (isRouter) {
                // Verify if router is allowed
                LSSVMRouter router = LSSVMRouter(payable(msg.sender));
                (bool routerAllowed,) = _factory.routerStatus(router);
                if (!routerAllowed) revert LSSVMPair__NotRouter();

                // Call router to pull NFTs
                // If more than 1 NFT is being transfered, and there is no property checker, we can do a balance check
                // instead of an ownership check, as pools are indifferent between NFTs from the same collection
                if ((numNFTs > 1) && (propertyChecker() == address(0))) {
                    uint256 beforeBalance = _nft.balanceOf(_assetRecipient);
                    for (uint256 i; i < numNFTs;) {
                        router.pairTransferNFTFrom(_nft, routerCaller, _assetRecipient, nftIds[i]);

                        unchecked {
                            ++i;
                        }
                    }
                    if (_nft.balanceOf(_assetRecipient) - beforeBalance != numNFTs) {
                        revert LSSVMPair__NftNotTransferred();
                    }
                }
                // Otherwise we need to pull each asset 1 at a time and verify ownership
                else {
                    for (uint256 i; i < numNFTs;) {
                        router.pairTransferNFTFrom(_nft, routerCaller, _assetRecipient, nftIds[i]);
                        if (_nft.ownerOf(nftIds[i]) != _assetRecipient) revert LSSVMPair__NftNotTransferred();
                        unchecked {
                            ++i;
                        }
                    }
                }
            } else {
                // Pull NFTs directly from sender
                for (uint256 i; i < numNFTs;) {
                    _nft.transferFrom(msg.sender, _assetRecipient, nftIds[i]);
                    unchecked {
                        ++i;
                    }
                }
            }
        }
    }

    /**
     * Owner functions
     */

    /**
     * @notice Rescues a specified set of NFTs owned by the pair to the owner address. (onlyOwner modifier is in the implemented function)
     * @param a The NFT to transfer
     * @param nftIds The list of IDs of the NFTs to send to the owner
     */
    function withdrawERC721(IERC721 a, uint256[] calldata nftIds) external virtual override onlyOwner {
        uint256 numNFTs = nftIds.length;
        for (uint256 i; i < numNFTs;) {
            a.safeTransferFrom(address(this), msg.sender, nftIds[i]);
            unchecked {
                ++i;
            }
        }

        if (a == IERC721(nft())) {
            emit NFTWithdrawal(nftIds);
        }
    }

    /**
     * @notice Rescues ERC1155 tokens from the pair to the owner. Only callable by the owner.
     * @param a The NFT to transfer
     * @param ids The NFT ids to transfer
     * @param amounts The amounts of each id to transfer
     */
    function withdrawERC1155(IERC1155 a, uint256[] calldata ids, uint256[] calldata amounts)
        external
        virtual
        override
        onlyOwner
    {
        a.safeBatchTransferFrom(address(this), msg.sender, ids, amounts, "");
    }
}

// src/erc1155/LSSVMPairERC1155ERC20.sol

/**
 * @title An ERC1155 pair where the token is an ERC20
 * @author boredGenius, 0xmons, 0xCygaar
 */
contract LSSVMPairERC1155ERC20 is LSSVMPairERC1155, LSSVMPairERC20 {
    uint256 internal constant IMMUTABLE_PARAMS_LENGTH = 113;

    constructor(IRoyaltyEngineV1 royaltyEngine) LSSVMPair(royaltyEngine) {}

    /**
     * Public functions
     */

    /**
     * @inheritdoc LSSVMPair
     */
    function pairVariant() public pure virtual override returns (ILSSVMPairFactoryLike.PairVariant) {
        return ILSSVMPairFactoryLike.PairVariant.ERC1155_ERC20;
    }

    /**
     * Internal functions
     */

    /**
     * @inheritdoc LSSVMPair
     * @dev see LSSVMPairCloner for params length calculation
     */
    function _immutableParamsLength() internal pure override returns (uint256) {
        return IMMUTABLE_PARAMS_LENGTH;
    }
}

// src/erc1155/LSSVMPairERC1155ETH.sol

/**
 * @title An ERC1155 pair where the token is an ETH
 * @author boredGenius, 0xmons, 0xCygaar
 */
contract LSSVMPairERC1155ETH is LSSVMPairERC1155, LSSVMPairETH {
    uint256 internal constant IMMUTABLE_PARAMS_LENGTH = 93;

    constructor(IRoyaltyEngineV1 royaltyEngine) LSSVMPair(royaltyEngine) {}

    /**
     * Public functions
     */

    /**
     * @inheritdoc LSSVMPair
     */
    function pairVariant() public pure virtual override returns (ILSSVMPairFactoryLike.PairVariant) {
        return ILSSVMPairFactoryLike.PairVariant.ERC1155_ETH;
    }

    /**
     * Internal functions
     */

    /**
     * @inheritdoc LSSVMPair
     * @dev see LSSVMPairCloner for params length calculation
     */
    function _immutableParamsLength() internal pure override returns (uint256) {
        return IMMUTABLE_PARAMS_LENGTH;
    }
}

// src/erc721/LSSVMPairERC721ERC20.sol

/**
 * @title An NFT/Token pair where the token is an ERC20
 * @author boredGenius, 0xmons, 0xCygaar
 */
contract LSSVMPairERC721ERC20 is LSSVMPairERC721, LSSVMPairERC20 {
    uint256 internal constant IMMUTABLE_PARAMS_LENGTH = 101;

    constructor(IRoyaltyEngineV1 royaltyEngine) LSSVMPair(royaltyEngine) {}

    /**
     * Public functions
     */

    /**
     * @inheritdoc LSSVMPair
     */
    function pairVariant() public pure override returns (ILSSVMPairFactoryLike.PairVariant) {
        return ILSSVMPairFactoryLike.PairVariant.ERC721_ERC20;
    }

    /**
     * Internal functions
     */

    /**
     * @inheritdoc LSSVMPair
     * @dev see LSSVMPairCloner for params length calculation
     */
    function _immutableParamsLength() internal pure override returns (uint256) {
        return IMMUTABLE_PARAMS_LENGTH;
    }
}

// src/erc721/LSSVMPairERC721ETH.sol

/**
 * @title An NFT/Token pair where the token is ETH
 * @author boredGenius, 0xmons, 0xCygaar
 */
contract LSSVMPairERC721ETH is LSSVMPairERC721, LSSVMPairETH {
    uint256 internal constant IMMUTABLE_PARAMS_LENGTH = 81;

    constructor(IRoyaltyEngineV1 royaltyEngine) LSSVMPair(royaltyEngine) {}

    /**
     * Public functions
     */

    /**
     * @inheritdoc LSSVMPair
     */
    function pairVariant() public pure override returns (ILSSVMPairFactoryLike.PairVariant) {
        return ILSSVMPairFactoryLike.PairVariant.ERC721_ETH;
    }

    /**
     * Internal functions
     */

    /**
     * @inheritdoc LSSVMPair
     * @dev see LSSVMPairCloner for params length calculation
     */
    function _immutableParamsLength() internal pure override returns (uint256) {
        return IMMUTABLE_PARAMS_LENGTH;
    }
}

// src/LSSVMPairFactory.sol

/**
 * @notice Imports for authAllowedForToken (forked from manifold.xyz Royalty Registry)
 */

/**
 * @title The factory contract used to deploy new pairs
 * @author boredGenius, 0xmons, 0xCygaar
 */
contract LSSVMPairFactory is Owned, ILSSVMPairFactoryLike {
    using LSSVMPairCloner for address;
    using AddressUpgradeable for address;
    using SafeTransferLib for address payable;
    using SafeTransferLib for ERC20;

    uint256 internal constant MAX_PROTOCOL_FEE = 0.1e18; // 10%, must <= 1 - MAX_FEE

    LSSVMPairERC721ETH public immutable erc721ETHTemplate;
    LSSVMPairERC721ERC20 public immutable erc721ERC20Template;
    LSSVMPairERC1155ETH public immutable erc1155ETHTemplate;
    LSSVMPairERC1155ERC20 public immutable erc1155ERC20Template;
    address payable public override protocolFeeRecipient;

    // Units are in base 1e18
    uint256 public override protocolFeeMultiplier;

    mapping(ICurve => bool) public bondingCurveAllowed;
    mapping(address => bool) public override callAllowed;

    // Data structures for settings logic
    mapping(address => mapping(address => bool)) public settingsForCollection;
    mapping(address => address) public settingsForPair;

    struct RouterStatus {
        bool allowed;
        bool wasEverTouched;
    }

    mapping(LSSVMRouter => RouterStatus) public override routerStatus;

    address private constant _NOT_ENTERED = address(1);
    address private _caller;

    event NewERC721Pair(address indexed poolAddress, uint256[] initialIds);
    event NewERC1155Pair(address indexed poolAddress, uint256 initialBalance);
    event ERC20Deposit(address indexed poolAddress, uint256 amount);
    event NFTDeposit(address indexed poolAddress, uint256[] ids);
    event ERC1155Deposit(address indexed poolAddress, uint256 indexed id, uint256 amount);
    event ProtocolFeeRecipientUpdate(address indexed recipientAddress);
    event ProtocolFeeMultiplierUpdate(uint256 newMultiplier);
    event BondingCurveStatusUpdate(ICurve indexed bondingCurve, bool isAllowed);
    event CallTargetStatusUpdate(address indexed target, bool isAllowed);
    event RouterStatusUpdate(LSSVMRouter indexed router, bool isAllowed);

    error LSSVMPairFactory__FeeTooLarge();
    error LSSVMPairFactory__BondingCurveNotWhitelisted();
    error LSSVMPairFactory__ReentrantCall();
    error LSSVMPairFactory__ZeroAddress();
    error LSSVMPairFactory__CannotCallRouter();
    error LSSVMPairFactory__UnauthorizedCaller();
    error LSSVMPairFactory__InvalidPair();
    error LSSVMPairFactory__SettingsNotEnabledForCollection();
    error LSSVMPairFactory__SettingsNotEnabledForPair();

    constructor(
        LSSVMPairERC721ETH _erc721ETHTemplate,
        LSSVMPairERC721ERC20 _erc721ERC20Template,
        LSSVMPairERC1155ETH _erc1155ETHTemplate,
        LSSVMPairERC1155ERC20 _erc1155ERC20Template,
        address payable _protocolFeeRecipient,
        uint256 _protocolFeeMultiplier,
        address _owner
    ) Owned(_owner) {
        erc721ETHTemplate = _erc721ETHTemplate;
        erc721ERC20Template = _erc721ERC20Template;
        erc1155ETHTemplate = _erc1155ETHTemplate;
        erc1155ERC20Template = _erc1155ERC20Template;
        protocolFeeRecipient = _protocolFeeRecipient;
        if (_protocolFeeMultiplier > MAX_PROTOCOL_FEE) revert LSSVMPairFactory__FeeTooLarge();
        protocolFeeMultiplier = _protocolFeeMultiplier;
        _caller = _NOT_ENTERED;
    }

    /**
     * External functions
     */

    /**
     * @notice Creates a pair contract using EIP-1167.
     * @param _nft The NFT contract of the collection the pair trades
     * @param _bondingCurve The bonding curve for the pair to price NFTs, must be whitelisted
     * @param _assetRecipient The address that will receive the assets traders give during trades.
     * If set to address(0), assets will be sent to the pool address. Not available to TRADE pools.
     * @param _poolType TOKEN, NFT, or TRADE
     * @param _delta The delta value used by the bonding curve. The meaning of delta depends on the specific curve.
     * @param _fee The fee taken by the LP in each trade. Can only be non-zero if _poolType is Trade.
     * @param _spotPrice The initial selling spot price
     * @param _propertyChecker The contract to use for verifying properties of IDs sent in
     * @param _initialNFTIDs The list of IDs of NFTs to transfer from the sender to the pair
     * @return pair The new pair
     */
    function createPairERC721ETH(
        IERC721 _nft,
        ICurve _bondingCurve,
        address payable _assetRecipient,
        LSSVMPair.PoolType _poolType,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        address _propertyChecker,
        uint256[] calldata _initialNFTIDs
    ) external payable returns (LSSVMPairERC721ETH pair) {
        if (!bondingCurveAllowed[_bondingCurve]) revert LSSVMPairFactory__BondingCurveNotWhitelisted();

        pair = LSSVMPairERC721ETH(
            payable(
                address(erc721ETHTemplate).cloneERC721ETHPair(
                    this, _bondingCurve, _nft, uint8(_poolType), _propertyChecker
                )
            )
        );

        _initializePairERC721ETH(pair, _nft, _assetRecipient, _delta, _fee, _spotPrice, _initialNFTIDs);
        emit NewERC721Pair(address(pair), _initialNFTIDs);
    }

    struct CreateERC721ERC20PairParams {
        ERC20 token;
        IERC721 nft;
        ICurve bondingCurve;
        address payable assetRecipient;
        LSSVMPair.PoolType poolType;
        uint128 delta;
        uint96 fee;
        uint128 spotPrice;
        address propertyChecker;
        uint256[] initialNFTIDs;
        uint256 initialTokenBalance;
    }

    /**
     * @notice Creates a pair contract using EIP-1167.
     * @param params The info used to create a new pair. This includes:
     * - token: The ERC20 token the pair trades
     * - nft: The NFT contract of the collection the pair trades
     * - bondingCurve: The bonding curve for the pair to price NFTs, must be whitelisted
     * - assetRecipient: The address that will receive the assets traders give during trades.
     *   If set to address(0), assets will be sent to the pool address. Not available to TRADE pools.
     * - poolType: TOKEN, NFT, or TRADE
     * - delta: The delta value used by the bonding curve. The meaning of delta depends on the specific curve.
     * - fee: The fee taken by the LP in each trade. Can only be non-zero if poolType is Trade.
     * - spotPrice: Param 1 for the bonding curve, usually used for start price
     * - delta: Param 2 for the bonding curve, usually used for dynamic adjustment
     * - propertyChecker: The contract to use for verifying properties of IDs sent in
     * - initialNFTIDs: The list of IDs of NFTs to transfer from the sender to the pair
     * - initialTokenBalance: The initial token balance sent from the sender to the new pair
     * @return pair The new pair
     */
    function createPairERC721ERC20(CreateERC721ERC20PairParams calldata params)
        external
        returns (LSSVMPairERC721ERC20 pair)
    {
        if (!bondingCurveAllowed[params.bondingCurve]) revert LSSVMPairFactory__BondingCurveNotWhitelisted();

        pair = LSSVMPairERC721ERC20(
            payable(
                address(erc721ERC20Template).cloneERC721ERC20Pair(
                    this, params.bondingCurve, params.nft, uint8(params.poolType), params.propertyChecker, params.token
                )
            )
        );

        _initializePairERC721ERC20(
            pair,
            params.token,
            params.nft,
            params.assetRecipient,
            params.delta,
            params.fee,
            params.spotPrice,
            params.initialNFTIDs,
            params.initialTokenBalance
        );
        emit NewERC721Pair(address(pair), params.initialNFTIDs);
    }
    /**
     * @notice Creates a pair contract using EIP-1167.
     * @param _nft The NFT contract of the collection the pair trades
     * @param _bondingCurve The bonding curve for the pair to price NFTs, must be whitelisted
     * @param _assetRecipient The address that will receive the assets traders give during trades.
     * If set to address(0), assets will be sent to the pool address. Not available to TRADE pools.
     * @param _poolType TOKEN, NFT, or TRADE
     * @param _delta The delta value used by the bonding curve. The meaning of delta depends on the specific curve.
     * @param _fee The fee taken by the LP in each trade. Can only be non-zero if _poolType is Trade.
     * @param _spotPrice The initial selling spot price
     * @param _nftId The ID of the NFT to trade
     * @param _initialNFTBalance The amount of NFTs to transfer from the sender to the pair
     * @return pair The new pair
     */

    function createPairERC1155ETH(
        IERC1155 _nft,
        ICurve _bondingCurve,
        address payable _assetRecipient,
        LSSVMPair.PoolType _poolType,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        uint256 _nftId,
        uint256 _initialNFTBalance
    ) external payable returns (LSSVMPairERC1155ETH pair) {
        if (!bondingCurveAllowed[_bondingCurve]) revert LSSVMPairFactory__BondingCurveNotWhitelisted();

        pair = LSSVMPairERC1155ETH(
            payable(
                address(erc1155ETHTemplate).cloneERC1155ETHPair(this, _bondingCurve, _nft, uint8(_poolType), _nftId)
            )
        );

        _initializePairERC1155ETH(pair, _nft, _assetRecipient, _delta, _fee, _spotPrice, _nftId, _initialNFTBalance);
        emit NewERC1155Pair(address(pair), _initialNFTBalance);
    }

    struct CreateERC1155ERC20PairParams {
        ERC20 token;
        IERC1155 nft;
        ICurve bondingCurve;
        address payable assetRecipient;
        LSSVMPair.PoolType poolType;
        uint128 delta;
        uint96 fee;
        uint128 spotPrice;
        uint256 nftId;
        uint256 initialNFTBalance;
        uint256 initialTokenBalance;
    }

    /**
     * @notice Creates a pair contract using EIP-1167.
     * @param params The info used to create a new pair. This includes:
     * - token: The ERC20 token the pair trades
     * - nft: The NFT contract of the collection the pair trades
     * - bondingCurve: The bonding curve for the pair to price NFTs, must be whitelisted
     * - assetRecipient: The address that will receive the assets traders give during trades.
     *   If set to address(0), assets will be sent to the pool address. Not available to TRADE pools.
     * - poolType: TOKEN, NFT, or TRADE
     * - delta: The delta value used by the bonding curve. The meaning of delta depends on the specific curve.
     * - fee: The fee taken by the LP in each trade. Can only be non-zero if poolType is Trade.
     * - spotPrice: Param 1 for the bonding curve, usually used for start price
     * - nftId: The ERC1155 nft id that this pair trades
     * - initialNFTBalance: The initial NFT balance sent from the sender to the new pair
     * - initialTokenBalance: The initial token balance sent from the sender to the new pair
     * @return pair The new pair
     */
    function createPairERC1155ERC20(CreateERC1155ERC20PairParams calldata params)
        external
        returns (LSSVMPairERC1155ERC20 pair)
    {
        if (!bondingCurveAllowed[params.bondingCurve]) revert LSSVMPairFactory__BondingCurveNotWhitelisted();

        pair = LSSVMPairERC1155ERC20(
            payable(
                address(erc1155ERC20Template).cloneERC1155ERC20Pair(
                    this, params.bondingCurve, params.nft, uint8(params.poolType), params.nftId, params.token
                )
            )
        );

        _initializePairERC1155ERC20(
            pair,
            params.token,
            params.nft,
            params.assetRecipient,
            params.delta,
            params.fee,
            params.spotPrice,
            params.nftId,
            params.initialNFTBalance,
            params.initialTokenBalance
        );
        emit NewERC1155Pair(address(pair), params.initialNFTBalance);
    }

    function isValidPair(address pairAddress) public view returns (bool) {
        PairVariant variant = LSSVMPair(pairAddress).pairVariant();
        if (variant == PairVariant.ERC721_ETH) {
            return LSSVMPairCloner.isERC721ETHPairClone(address(this), address(erc721ETHTemplate), pairAddress);
        } else if (variant == PairVariant.ERC721_ERC20) {
            return LSSVMPairCloner.isERC721ERC20PairClone(address(this), address(erc721ERC20Template), pairAddress);
        } else if (variant == PairVariant.ERC1155_ETH) {
            return LSSVMPairCloner.isERC1155ETHPairClone(address(this), address(erc1155ETHTemplate), pairAddress);
        } else if (variant == PairVariant.ERC1155_ERC20) {
            return LSSVMPairCloner.isERC1155ERC20PairClone(address(this), address(erc1155ERC20Template), pairAddress);
        } else {
            return false;
        }
    }

    function getPairNFTType(address pairAddress) public pure returns (PairNFTType) {
        PairVariant variant = LSSVMPair(pairAddress).pairVariant();
        return PairNFTType(uint8(variant) / 2);
    }

    function getPairTokenType(address pairAddress) public pure returns (PairTokenType) {
        PairVariant variant = LSSVMPair(pairAddress).pairVariant();
        return PairTokenType(uint8(variant) % 2);
    }

    function openLock() public {
        if (_caller == msg.sender) revert LSSVMPairFactory__ReentrantCall();
        _caller = msg.sender;
    }

    function closeLock() public {
        if (_caller != msg.sender) revert LSSVMPairFactory__ReentrantCall();
        _caller = _NOT_ENTERED;
    }

    /**
     * @notice Checks if an address is an allowed auth for a token
     * @param tokenAddress The token address to check
     * @param proposedAuthAddress The auth address to check
     * @return True if the proposedAuthAddress is a valid auth for the tokenAddress, false otherwise.
     */
    function authAllowedForToken(address tokenAddress, address proposedAuthAddress) public view returns (bool) {
        // Check for admin interface
        if (
            ERC165Checker.supportsInterface(tokenAddress, type(IAdminControl).interfaceId)
                && IAdminControl(tokenAddress).isAdmin(proposedAuthAddress)
        ) {
            return true;
        }
        // Check for owner
        try OwnableUpgradeable(tokenAddress).owner() returns (address owner) {
            if (owner == proposedAuthAddress) return true;

            if (owner.isContract()) {
                try OwnableUpgradeable(owner).owner() returns (address passThroughOwner) {
                    if (passThroughOwner == proposedAuthAddress) return true;
                } catch {}
            }
        } catch {}
        // Check for default OZ auth role
        try IAccessControlUpgradeable(tokenAddress).hasRole(0x00, proposedAuthAddress) returns (bool hasRole) {
            if (hasRole) return true;
        } catch {}
        // Nifty Gateway overrides
        try INiftyBuilderInstance(tokenAddress).niftyRegistryContract() returns (address niftyRegistry) {
            try INiftyRegistry(niftyRegistry).isValidNiftySender(proposedAuthAddress) returns (bool valid) {
                if (valid) return true;
            } catch {}
        } catch {}
        // Foundation overrides
        try IFoundationTreasuryNode(tokenAddress).getFoundationTreasury() returns (address payable foundationTreasury) {
            try IFoundationTreasury(foundationTreasury).isAdmin(proposedAuthAddress) returns (bool isAdmin) {
                if (isAdmin) return true;
            } catch {}
        } catch {}
        // DIGITALAX overrides
        try IDigitalax(tokenAddress).accessControls() returns (address externalAccessControls) {
            try IDigitalaxAccessControls(externalAccessControls).hasAdminRole(proposedAuthAddress) returns (
                bool hasRole
            ) {
                if (hasRole) return true;
            } catch {}
        } catch {}
        // Art Blocks overrides
        try IArtBlocks(tokenAddress).admin() returns (address admin) {
            if (admin == proposedAuthAddress) return true;
        } catch {}
        return false;
    }

    /**
     * @notice Allows receiving ETH in order to receive protocol fees
     */
    receive() external payable {}

    /**
     * Admin functions
     */

    /**
     * @notice Withdraws the ETH balance to the protocol fee recipient.
     * Only callable by the owner.
     */
    function withdrawETHProtocolFees() external onlyOwner {
        protocolFeeRecipient.safeTransferETH(address(this).balance);
    }

    /**
     * @notice Withdraws ERC20 tokens to the protocol fee recipient. Only callable by the owner.
     * @param token The token to transfer
     * @param amount The amount of tokens to transfer
     */
    function withdrawERC20ProtocolFees(ERC20 token, uint256 amount) external onlyOwner {
        token.safeTransfer(protocolFeeRecipient, amount);
    }

    /**
     * @notice Changes the protocol fee recipient address. Only callable by the owner.
     * @param _protocolFeeRecipient The new fee recipient
     */
    function changeProtocolFeeRecipient(address payable _protocolFeeRecipient) external onlyOwner {
        if (_protocolFeeRecipient == address(0)) revert LSSVMPairFactory__ZeroAddress();
        protocolFeeRecipient = _protocolFeeRecipient;
        emit ProtocolFeeRecipientUpdate(_protocolFeeRecipient);
    }

    /**
     * @notice Changes the protocol fee multiplier. Only callable by the owner.
     * @param _protocolFeeMultiplier The new fee multiplier, 18 decimals
     */
    function changeProtocolFeeMultiplier(uint256 _protocolFeeMultiplier) external onlyOwner {
        if (_protocolFeeMultiplier > MAX_PROTOCOL_FEE) revert LSSVMPairFactory__FeeTooLarge();
        protocolFeeMultiplier = _protocolFeeMultiplier;
        emit ProtocolFeeMultiplierUpdate(_protocolFeeMultiplier);
    }

    /**
     * @notice Sets the whitelist status of a bonding curve contract. Only callable by the owner.
     * @param bondingCurve The bonding curve contract
     * @param isAllowed True to whitelist, false to remove from whitelist
     */
    function setBondingCurveAllowed(ICurve bondingCurve, bool isAllowed) external onlyOwner {
        bondingCurveAllowed[bondingCurve] = isAllowed;
        emit BondingCurveStatusUpdate(bondingCurve, isAllowed);
    }

    /**
     * @notice Sets the whitelist status of a contract to be called arbitrarily by a pair.
     * Only callable by the owner.
     * @param target The target contract
     * @param isAllowed True to whitelist, false to remove from whitelist
     */
    function setCallAllowed(address payable target, bool isAllowed) external onlyOwner {
        // Ensure target is not / was not ever a router
        if (isAllowed) {
            if (routerStatus[LSSVMRouter(target)].wasEverTouched) revert LSSVMPairFactory__CannotCallRouter();
        }

        callAllowed[target] = isAllowed;
        emit CallTargetStatusUpdate(target, isAllowed);
    }

    /**
     * @notice Updates the router whitelist. Only callable by the owner.
     * @param _router The router
     * @param isAllowed True to whitelist, false to remove from whitelist
     */
    function setRouterAllowed(LSSVMRouter _router, bool isAllowed) external onlyOwner {
        // Ensure target is not arbitrarily callable by pairs
        if (isAllowed) {
            if (callAllowed[address(_router)]) revert LSSVMPairFactory__CannotCallRouter();
        }
        routerStatus[_router] = RouterStatus({allowed: isAllowed, wasEverTouched: true});

        emit RouterStatusUpdate(_router, isAllowed);
    }

    /**
     * @notice Returns the Settings for a pair if it currently has Settings
     * @param pairAddress The address of the pair to look up
     * @return settingsEnabled Whether or not the pair has custom settings
     * @return bps The royalty basis points from the custom settings, 0 if there is no custom settings
     */
    function getSettingsForPair(address pairAddress) public view returns (bool settingsEnabled, uint96 bps) {
        address settingsAddress = settingsForPair[pairAddress];
        if (settingsAddress == address(0)) {
            return (false, 0);
        }
        return ISettings(settingsAddress).getRoyaltyInfo(pairAddress);
    }

    /**
     * @notice Enables or disables an settings for a given NFT collection
     *  @param settings The address of the Settings contract
     *  @param collectionAddress The NFT project that the settings is toggled for
     *  @param enable Bool to determine whether to disable or enable the settings
     */
    function toggleSettingsForCollection(address settings, address collectionAddress, bool enable) public {
        if (!authAllowedForToken(collectionAddress, msg.sender)) revert LSSVMPairFactory__UnauthorizedCaller();
        if (enable) {
            settingsForCollection[collectionAddress][settings] = true;
        } else {
            delete settingsForCollection[collectionAddress][settings];
        }
    }

    /**
     * @notice Enables an Settings for a given Pair
     * @notice Only the owner of the Pair can call this function
     * @notice The Settings must be enabled for the Pair's collection
     * @param settings The address of the Settings contract
     * @param pairAddress The address of the Pair contract
     */
    function enableSettingsForPair(address settings, address pairAddress) public {
        if (!isValidPair(pairAddress)) revert LSSVMPairFactory__InvalidPair();
        LSSVMPair pair = LSSVMPair(pairAddress);
        if (pair.owner() != msg.sender) revert LSSVMPairFactory__UnauthorizedCaller();
        if (!settingsForCollection[address(pair.nft())][settings]) {
            revert LSSVMPairFactory__SettingsNotEnabledForCollection();
        }
        settingsForPair[pairAddress] = settings;
    }

    /**
     * @notice Disables an Settings for a given Pair
     * @notice Only the owner of the Pair can call this function
     * @notice The Settings must already be enabled for the Pair
     * @param settings The address of the Settings contract
     * @param pairAddress The address of the Pair contract
     */
    function disableSettingsForPair(address settings, address pairAddress) public {
        if (!isValidPair(pairAddress)) revert LSSVMPairFactory__InvalidPair();
        if (settingsForPair[pairAddress] != settings) revert LSSVMPairFactory__SettingsNotEnabledForPair();
        LSSVMPair pair = LSSVMPair(pairAddress);
        if (pair.owner() != msg.sender) revert LSSVMPairFactory__UnauthorizedCaller();
        delete settingsForPair[pairAddress];
    }

    /**
     * Internal functions
     */

    function _initializePairERC721ETH(
        LSSVMPairERC721ETH _pair,
        IERC721 _nft,
        address payable _assetRecipient,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        uint256[] calldata _initialNFTIDs
    ) internal {
        // Initialize pair
        _pair.initialize(msg.sender, _assetRecipient, _delta, _fee, _spotPrice);

        // Transfer initial ETH to pair
        if (msg.value != 0) payable(address(_pair)).safeTransferETH(msg.value);

        // Transfer initial NFTs from sender to pair
        uint256 numNFTs = _initialNFTIDs.length;
        for (uint256 i; i < numNFTs;) {
            _nft.transferFrom(msg.sender, address(_pair), _initialNFTIDs[i]);

            unchecked {
                ++i;
            }
        }
    }

    function _initializePairERC721ERC20(
        LSSVMPairERC721ERC20 _pair,
        ERC20 _token,
        IERC721 _nft,
        address payable _assetRecipient,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        uint256[] calldata _initialNFTIDs,
        uint256 _initialTokenBalance
    ) internal {
        // Initialize pair
        _pair.initialize(msg.sender, _assetRecipient, _delta, _fee, _spotPrice);

        // Transfer initial tokens to pair (if != 0)
        if (_initialTokenBalance != 0) {
            _token.safeTransferFrom(msg.sender, address(_pair), _initialTokenBalance);
        }

        // Transfer initial NFTs from sender to pair
        uint256 numNFTs = _initialNFTIDs.length;
        for (uint256 i; i < numNFTs;) {
            _nft.transferFrom(msg.sender, address(_pair), _initialNFTIDs[i]);

            unchecked {
                ++i;
            }
        }
    }

    function _initializePairERC1155ETH(
        LSSVMPairERC1155ETH _pair,
        IERC1155 _nft,
        address payable _assetRecipient,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        uint256 _nftId,
        uint256 _initialNFTBalance
    ) internal {
        // Initialize pair
        _pair.initialize(msg.sender, _assetRecipient, _delta, _fee, _spotPrice);

        // Transfer initial ETH to pair
        if (msg.value != 0) payable(address(_pair)).safeTransferETH(msg.value);

        // Transfer initial NFTs from sender to pair
        if (_initialNFTBalance != 0) {
            _nft.safeTransferFrom(msg.sender, address(_pair), _nftId, _initialNFTBalance, bytes(""));
        }
    }

    function _initializePairERC1155ERC20(
        LSSVMPairERC1155ERC20 _pair,
        ERC20 _token,
        IERC1155 _nft,
        address payable _assetRecipient,
        uint128 _delta,
        uint96 _fee,
        uint128 _spotPrice,
        uint256 _nftId,
        uint256 _initialNFTBalance,
        uint256 _initialTokenBalance
    ) internal {
        // Initialize pair
        _pair.initialize(msg.sender, _assetRecipient, _delta, _fee, _spotPrice);

        // Transfer initial tokens to pair
        if (_initialTokenBalance != 0) {
            _token.safeTransferFrom(msg.sender, address(_pair), _initialTokenBalance);
        }

        // Transfer initial NFTs from sender to pair
        if (_initialNFTBalance != 0) {
            _nft.safeTransferFrom(msg.sender, address(_pair), _nftId, _initialNFTBalance, bytes(""));
        }
    }

    /**
     * @dev Used to deposit NFTs into a pair after creation and emit an event for indexing (if recipient is indeed a pair)
     */
    function depositNFTs(IERC721 _nft, uint256[] calldata ids, address recipient) external {
        uint256 numNFTs = ids.length;

        // Early return for trivial transfers
        if (numNFTs == 0) return;

        // Transfer NFTs from caller to recipient
        for (uint256 i; i < numNFTs;) {
            _nft.transferFrom(msg.sender, recipient, ids[i]);

            unchecked {
                ++i;
            }
        }
        if (isValidPair(recipient) && (address(_nft) == LSSVMPair(recipient).nft())) {
            emit NFTDeposit(recipient, ids);
        }
    }

    /**
     * @dev Used to deposit ERC20s into a pair after creation and emit an event for indexing (if recipient is indeed an ERC20 pair and the token matches)
     */
    function depositERC20(ERC20 token, address recipient, uint256 amount) external {
        // Early return for trivial transfers
        if (amount == 0) return;

        token.safeTransferFrom(msg.sender, recipient, amount);
        if (
            isValidPair(recipient) && getPairTokenType(recipient) == PairTokenType.ERC20
                && token == LSSVMPairERC20(recipient).token()
        ) {
            emit ERC20Deposit(recipient, amount);
        }
    }

    /**
     * @dev Used to deposit ERC1155 NFTs into a pair after creation and emit an event for indexing (if recipient is indeed a pair)
     */
    function depositERC1155(IERC1155 nft, uint256 id, address recipient, uint256 amount) external {
        if (amount == 0) return;

        nft.safeTransferFrom(msg.sender, recipient, id, amount, bytes(""));

        if (
            isValidPair(recipient) && getPairNFTType(recipient) == PairNFTType.ERC1155
                && address(nft) == LSSVMPair(recipient).nft() && id == LSSVMPairERC1155(recipient).nftId()
        ) {
            emit ERC1155Deposit(recipient, id, amount);
        }
    }
}

