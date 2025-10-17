import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BlockNotFound
from eth_account import Account
import requests

# --- Configuration Loading ---
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('BridgeEventListener')

# --- MOCK CONTRACT ABI ---
# In a real-world scenario, this would be loaded from a file.
BRIDGE_CONTRACT_ABI = json.loads('''
[
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "destinationChainId",
                "type": "uint256"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "nonce",
                "type": "uint256"
            }
        ],
        "name": "TokensLocked",
        "type": "event"
    }
]
''')

# --- Configuration ---
# It's highly recommended to use environment variables for sensitive data.
CONFIG = {
    'source_chain': {
        'name': 'Ethereum-Sepolia',
        'chain_id': 11155111,
        'rpc_url': os.getenv('SOURCE_CHAIN_RPC_URL', 'https://rpc.sepolia.org'),
        'bridge_contract_address': os.getenv('SOURCE_BRIDGE_CONTRACT', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'), # Example: Uniswap V2 Router
        'confirmation_blocks': 5 # Number of blocks to wait for event confirmation
    },
    'destination_chain': {
        'name': 'Polygon-Mumbai',
        'chain_id': 80001,
        'rpc_url': os.getenv('DESTINATION_CHAIN_RPC_URL', 'https://rpc-mumbai.maticvigil.com')
    },
    'listener': {
        'poll_interval_seconds': 10,
        'start_block': 'latest' # or a specific block number to start from
    },
    'validator': {
        # This private key is used to sign attestations for the destination chain.
        # IMPORTANT: Never hardcode private keys in production code.
        'private_key': os.getenv('VALIDATOR_PRIVATE_KEY')
    }
}

class BlockchainConnector:
    """
    Manages the connection to a single blockchain via Web3.py.
    This class encapsulates the Web3 instance and provides a robust way
    to interact with a specific chain, handling connection retries.
    """
    def __init__(self, name: str, rpc_url: str):
        self.name = name
        self.rpc_url = rpc_url
        self.web3: Optional[Web3] = None
        self.connect()

    def connect(self):
        """Establishes a connection to the blockchain node."""
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.web3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.name} at {self.rpc_url}")
            logger.info(f"Successfully connected to {self.name} (Chain ID: {self.web3.eth.chain_id}).")
        except Exception as e:
            logger.error(f"Error connecting to {self.name}: {e}")
            self.web3 = None

    def get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Optional[Contract]:
        """Returns a Web3 contract instance if connected."""
        if not self.web3 or not self.web3.is_connected():
            logger.warning(f"Not connected to {self.name}, attempting to reconnect.")
            self.connect()
            if not self.web3:
                return None
        
        checksum_address = self.web3.to_checksum_address(address)
        return self.web3.eth.contract(address=checksum_address, abi=abi)


class EventScanner:
    """
    Scans a blockchain for specific events from a given contract.
    It maintains its state (last scanned block) and handles potential blockchain reorgs
    by waiting for a certain number of confirmation blocks.
    """
    def __init__(self, connector: BlockchainConnector, config: Dict[str, Any]):
        self.connector = connector
        self.config = config
        self.contract = self._initialize_contract()
        self.last_scanned_block = self._get_initial_start_block()

    def _initialize_contract(self) -> Contract:
        """Helper to get the contract instance from the connector."""
        contract_address = self.config['bridge_contract_address']
        logger.info(f"Initializing bridge contract on {self.connector.name} at {contract_address}")
        contract = self.connector.get_contract(contract_address, BRIDGE_CONTRACT_ABI)
        if not contract:
            raise RuntimeError(f"Could not initialize contract at {contract_address}")
        return contract

    def _get_initial_start_block(self) -> int:
        """Determines the starting block for scanning."""
        start_block_config = self.config['listener']['start_block']
        if start_block_config == 'latest':
            return self.connector.web3.eth.block_number
        elif isinstance(start_block_config, int):
            return start_block_config
        else:
            raise ValueError(f"Invalid start_block configuration: {start_block_config}")

    async def scan_for_events(self) -> List[Dict[str, Any]]:
        """
        Scans a range of blocks for 'TokensLocked' events.
        It respects the confirmation depth to avoid processing events from reorged blocks.
        """
        if not self.connector.web3 or not self.connector.web3.is_connected():
            logger.error(f"Cannot scan, connector for {self.connector.name} is not available.")
            return []

        try:
            latest_block = self.connector.web3.eth.block_number
            confirmation_depth = self.config['confirmation_blocks']
            
            # The `to_block` is set back by `confirmation_depth` to ensure finality
            to_block = latest_block - confirmation_depth

            if self.last_scanned_block >= to_block:
                logger.info(f"No new blocks to scan on {self.connector.name}. Current head: {latest_block}, last scanned: {self.last_scanned_block}")
                return []

            from_block = self.last_scanned_block + 1
            logger.info(f"Scanning {self.connector.name} from block {from_block} to {to_block}...")

            event_filter = self.contract.events.TokensLocked.create_filter(
                fromBlock=from_block,
                toBlock=to_block
            )
            
            new_events = event_filter.get_all_entries()

            if new_events:
                logger.warning(f"Found {len(new_events)} new 'TokensLocked' event(s) on {self.connector.name}!")
                for event in new_events:
                    logger.info(f"  - Event details: {json.dumps(event['args'], default=str)}")
            
            self.last_scanned_block = to_block
            return new_events

        except BlockNotFound:
            logger.warning(f"Block not found during scan on {self.connector.name}. Possible reorg. Will retry.")
            # In case of a reorg, we might need to rewind our last_scanned_block.
            # For simplicity, we just log and wait for the next poll.
            self.last_scanned_block = self.connector.web3.eth.block_number - (confirmation_depth * 2)
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during event scan on {self.connector.name}: {e}", exc_info=True)
            return []


class TransactionProcessor:
    """
    Processes confirmed events and prepares them for cross-chain dispatch.
    This involves validating data and constructing a payload that the destination
    chain's contract can understand.
    """
    def __init__(self, source_chain_id: int, dest_chain_config: Dict[str, Any]):
        self.source_chain_id = source_chain_id
        self.dest_chain_config = dest_chain_config
        logger.info(f"TransactionProcessor initialized for source {source_chain_id} -> dest {dest_chain_config['name']}")

    def process_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Validates the event and transforms it into a standard cross-chain payload.
        """
        try:
            args = event['args']
            # Basic validation
            if args['destinationChainId'] != self.dest_chain_config['chain_id']:
                logger.debug(f"Skipping event with nonce {args['nonce']} meant for another chain ({args['destinationChainId']}).")
                return None

            payload = {
                'sourceTransactionHash': event['transactionHash'].hex(),
                'sourceBlockNumber': event['blockNumber'],
                'sender': args['sender'],
                'receiver': args['receiver'],
                'amount': args['amount'],
                'nonce': args['nonce'],
                'sourceChainId': self.source_chain_id,
                'destinationChainId': args['destinationChainId']
            }
            logger.info(f"Successfully processed event with nonce {payload['nonce']}. Payload prepared.")
            return payload
        except (KeyError, TypeError) as e:
            logger.error(f"Failed to process event due to malformed data: {event}. Error: {e}")
            return None


class CrossChainDispatcher:
    """
    Simulates dispatching the transaction to the destination chain.
    In a real bridge, this component would be a validator/oracle that signs the payload
    and either submits it directly to the destination chain's contract or broadcasts
    the signature for others to collect and submit.
    """
    def __init__(self, validator_private_key: str):
        if not validator_private_key:
            raise ValueError("Validator private key is required for the dispatcher.")
        self.validator_account = Account.from_key(validator_private_key)
        logger.info(f"Dispatcher initialized with validator address: {self.validator_account.address}")

    async def dispatch(self, payload: Dict[str, Any]):
        """
        Signs the payload and simulates sending it to the destination chain.
        """
        try:
            # Create a structured message to sign (EIP-712 is better for production)
            message = json.dumps(payload, sort_keys=True)
            message_hash = Web3.keccak(text=message)

            # Sign the hash
            signed_message = self.validator_account.signHash(message_hash)
            
            logger.info(f"Payload with nonce {payload['nonce']} signed by validator.")
            logger.info(f"  - Signature: {signed_message.signature.hex()}")

            # --- SIMULATION --- 
            # In a real system, this would call a contract on the destination chain
            # or send the signature to a relayer network.
            # Here, we simulate by posting to a mock API endpoint.
            await self._simulate_api_call(payload, signed_message.signature.hex())

        except Exception as e:
            logger.error(f"Failed to dispatch payload for nonce {payload.get('nonce', 'N/A')}: {e}", exc_info=True)

    async def _simulate_api_call(self, payload: Dict[str, Any], signature: str):
        """
        A mock function to simulate interacting with a relayer or destination chain API.
        """
        mock_api_endpoint = "https://httpbin.org/post" # Use a test endpoint
        dispatch_data = {
            'attestation': {
                'payload': payload,
                'signature': signature
            }
        }
        logger.info(f"Dispatching signed payload to mock relayer API: {mock_api_endpoint}")
        try:
            # Using `requests` in a non-blocking way with asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(mock_api_endpoint, json=dispatch_data, timeout=10))
            response.raise_for_status() # Raise an exception for bad status codes
            logger.info(f"Successfully dispatched payload for nonce {payload['nonce']}. Relayer API response: {response.status_code}")
            # logger.debug(f"API Response Body: {response.json()}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to communicate with relayer API: {e}")


class BridgeOrchestrator:
    """
    The main class that coordinates all components of the bridge listener service.
    It sets up the scanner, processor, and dispatcher and runs the main event loop.
    """
    def __init__(self, config: Dict[str, Any]):
        logger.info("Initializing Bridge Orchestrator...")
        self.config = config
        self.poll_interval = config['listener']['poll_interval_seconds']
        
        if not config['validator'].get('private_key'):
            raise ValueError("VALIDATOR_PRIVATE_KEY is not set in the environment or config.")

        # 1. Setup blockchain connectors
        self.source_connector = BlockchainConnector(
            name=config['source_chain']['name'],
            rpc_url=config['source_chain']['rpc_url']
        )

        # 2. Setup event scanner
        self.event_scanner = EventScanner(
            connector=self.source_connector,
            config=config['source_chain']
        )
        self.event_scanner.config['listener'] = config['listener'] # Pass listener config

        # 3. Setup transaction processor
        self.tx_processor = TransactionProcessor(
            source_chain_id=config['source_chain']['chain_id'],
            dest_chain_config=config['destination_chain']
        )

        # 4. Setup dispatcher
        self.dispatcher = CrossChainDispatcher(
            validator_private_key=config['validator']['private_key']
        )

        self.is_running = False

    async def run(self):
        """Starts the main orchestration loop."""
        logger.info("Bridge Event Listener service starting.")
        self.is_running = True
        while self.is_running:
            try:
                # Scan for new, confirmed events
                confirmed_events = await self.event_scanner.scan_for_events()
                
                if not confirmed_events:
                    logger.info(f"No new confirmed events found. Waiting for {self.poll_interval} seconds.")
                else:
                    # Process and dispatch each event
                    for event in confirmed_events:
                        payload = self.tx_processor.process_event(event)
                        if payload:
                            await self.dispatcher.dispatch(payload)
                
                await asyncio.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Stopping orchestrator.")
                self.is_running = False
            except Exception as e:
                logger.critical(f"A critical error occurred in the main loop: {e}", exc_info=True)
                logger.info("Service will attempt to recover in 30 seconds.")
                await asyncio.sleep(30)
        
        logger.info("Bridge Event Listener service has stopped.")


async def main():
    """Main entry point for the script."""
    try:
        orchestrator = BridgeOrchestrator(CONFIG)
        await orchestrator.run()
    except (ValueError, RuntimeError) as e:
        logger.critical(f"Failed to initialize orchestrator: {e}")

if __name__ == '__main__':
    asyncio.run(main())
 

 

 

 

 















