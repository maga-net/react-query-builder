# React Query Builder - Cross-Chain Bridge Event Listener

> **Note on Naming:** Despite the repository name, this project is a backend service, not a UI component. It simulates the architectural logic of a decentralized bridge oracle.

This repository contains a Python-based simulation of a critical backend component for a cross-chain bridge: the **Event Listener and Validator Node**. This script monitors a source blockchain for specific events (e.g., `TokensLocked`), validates them, and then prepares and signs a corresponding transaction payload for a destination chain.

## Concept

Cross-chain bridges allow users to transfer assets or data from one blockchain to another. A common architectural pattern is the "lock-and-mint" or "burn-and-release" mechanism. This script simulates the off-chain oracle or validator's role in this system.

1.  **Listen**: The service continuously monitors a `Bridge` smart contract on the source chain (e.g., Ethereum).
2.  **Detect**: It looks for a specific event, such as `TokensLocked`, which is emitted when a user deposits assets into the bridge contract, specifying a destination chain and recipient address.
3.  **Confirm**: To mitigate the risk of block reorganizations (re-orgs)—where a block is temporarily orphaned and replaced—the service waits for a predefined number of `confirmation_blocks` to pass before considering an event as final.
4.  **Validate & Attest**: Once confirmed, the service (acting as a validator) processes the event data. It creates a standardized payload containing the details of the transfer (amount, recipient, etc.) and signs it with its private key. This signature is an attestation, a verifiable proof that the event occurred on the source chain.
5.  **Dispatch**: The signed payload is then dispatched to the destination chain. In a real system, this could be sent to a relayer network or directly submitted to a smart contract on the destination chain, which would then mint the equivalent tokens for the user.

## Code Architecture

The script is designed with a modular, object-oriented approach to separate concerns and enhance maintainability.

```
+-----------------------+
|  BridgeOrchestrator   | (Main loop, coordinates all components)
+-----------+-----------+
            |
            | 1. Starts and manages
            v
+-----------------------+
|     EventScanner      | (Scans source chain for events)
+-----------+-----------+
            |           |
            |           | 2. Uses connector to get block data
            |           v
            |   +-----------------------+
            |   |  BlockchainConnector  | (Manages Web3 connection)
            |   +-----------------------+
            |
            | 3. Passes confirmed events to
            v
+-----------------------+
|  TransactionProcessor | (Validates event data, creates payload)
+-----------+-----------+
            |
            | 4. Passes payload to
            v
+-----------------------+
| CrossChainDispatcher  | (Signs payload with validator key, sends to dest)
+-----------------------+
```

### Core Components

-   `BlockchainConnector`: A wrapper around `web3.py` that manages the connection to a blockchain's RPC endpoint.
-   `EventScanner`: The heart of the listening process. It polls the source chain for new blocks, queries for specific contract events within a block range, and waits for confirmations before flagging an event as final.
-   `TransactionProcessor`: A stateless logic class that takes a raw event log, validates its data (e.g., checks if it's intended for the correct destination chain), and transforms it into a structured, standardized payload. For example:
    ```json
    {
      "source_tx_hash": "0xabc...",
      "source_chain_id": 11155111,
      "destination_chain_id": 80001,
      "recipient": "0x123...",
      "token": "0x456...",
      "amount": "1000000000000000000"
    }
    ```
-   `CrossChainDispatcher`: Simulates the validator's role. It takes the processed payload, signs it using a private key, and dispatches the signed message. In this simulation, it sends the data to a mock API endpoint.
-   `BridgeOrchestrator`: The top-level class that initializes and wires together all other components. It runs the main asynchronous loop, controlling the flow from scanning to dispatching.

## How It Works

1.  **Configuration**: The script loads its configuration from environment variables (via a `.env` file for secrets like RPC URLs and private keys) and supplements it with static settings from the `CONFIG` dictionary in `script.py`.

2.  **Initialization**: The `BridgeOrchestrator` is instantiated. It creates instances of the `BlockchainConnector`, `EventScanner`, `TransactionProcessor`, and `CrossChainDispatcher` using the loaded configuration.

3.  **Scanning Loop**: The orchestrator starts its `run()` method.
    -   The `EventScanner` determines the range of blocks to scan, from the last scanned block up to the latest block minus the required number of confirmations.
    -   It uses `web3.py` to filter for `TokensLocked` events within that block range.

4.  **Processing**: If any confirmed events are found:
    -   Each event is passed to the `TransactionProcessor`.
    -   The processor checks if the event's `destinationChainId` matches the configured destination. If so, it creates a structured payload.

5.  **Dispatching**:
    -   The valid payload is passed to the `CrossChainDispatcher`.
    -   The dispatcher serializes the payload into a standard format, hashes it (using Keccak-256), and signs the resulting hash with the validator's private key.
    -   The signed message is then sent to a mock API endpoint to simulate the completion of the cross-chain communication leg.

6.  **Repeat**: The orchestrator pauses for a configured interval (`poll_interval_seconds`) and then repeats the loop.

## The Target Event

The listener is configured to watch for a specific event signature on the source bridge contract. For this simulation, it targets a `TokensLocked` event, which might be defined in a Solidity smart contract like this:

```solidity
// Example Solidity event in the source Bridge.sol contract
event TokensLocked(
    address indexed user,
    address indexed token,
    uint256 amount,
    uint256 destinationChainId,
    bytes recipientAddress
);
```

When a user locks tokens, this event is emitted, and its data becomes the input for the cross-chain validation and dispatch process.

## Getting Started

### 1. Prerequisites

-   Python 3.8+
-   An RPC URL for a source EVM-compatible chain (e.g., from Infura or Alchemy for Sepolia testnet).
-   A private key for the account that will act as the validator. **Do not use a key with real funds for this simulation.**

### 2. Installation

Clone the repository and install the required dependencies.

```bash
# 1. Clone this repository
git clone https://github.com/your-username/react-query-builder.git
cd react-query-builder

# 2. Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file in the root of the project directory and add your configuration details. This file is ignored by Git to protect your secrets.

```dotenv
# .env file

# RPC URL for the blockchain you want to listen to (e.g., Ethereum Sepolia)
SOURCE_CHAIN_RPC_URL="https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"

# (Optional) Address of the bridge contract to monitor on the source chain.
# Defaults to a well-known contract on Sepolia for demonstration purposes.
SOURCE_BRIDGE_CONTRACT="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

# Private key of the account that will sign the attestations. 
# MUST start with 0x. USE A BURNER ACCOUNT.
VALIDATOR_PRIVATE_KEY="0x_your_burner_private_key_here"
```

### 4. Running the Script

Execute the script from your terminal.

```bash
python script.py
```

The script will start, connect to the source chain, and begin scanning for events. The console will show detailed log output of its operations.

```text
# Example Output
2023-10-27 15:30:00 - BridgeOrchestrator - [INFO] - Initializing Bridge Orchestrator...
2023-10-27 15:30:01 - BlockchainConnector - [INFO] - Successfully connected to Ethereum-Sepolia (Chain ID: 11155111).
2023-10-27 15:30:01 - EventScanner - [INFO] - Initializing bridge contract on Ethereum-Sepolia at 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D
2023-10-27 15:30:01 - TransactionProcessor - [INFO] - TransactionProcessor initialized for source 11155111 -> dest Polygon-Mumbai
2023-10-27 15:30:01 - CrossChainDispatcher - [INFO] - Dispatcher initialized with validator address: 0x...
2023-10-27 15:30:01 - BridgeOrchestrator - [INFO] - Bridge Event Listener service starting.
2023-10-27 15:30:02 - EventScanner - [INFO] - Scanning Ethereum-Sepolia from block 4851200 to 4851210...
2023-10-27 15:30:04 - BridgeOrchestrator - [INFO] - No new confirmed events found. Waiting for 10 seconds.
... 
```