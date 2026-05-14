# Cardano-EVM XPort Bridge Runner

Interactive CLI for cross-chain transactions between Cardano (Preprod) and EVM (Wanchain Testnet).

## Features
- **Deterministic HD Wallets**: Derives both Cardano (BIP-1852) and EVM (BIP-44) wallets from a single 24-word mnemonic.
- **Interactive Runner**: Modular CLI for balance checking, fund distribution, and transaction initiation.
- **Protocol-Correct Encoding**: specialized CBOR indefinite-length encoding for Plutus scripts.
- **Autonomous Msg Agent**: Standalone service to monitor and settle Cardano-side message processing.

## Setup
1. `pip install -r requirements.txt`
2. Create `.env` with `YOUR_BLOCKFROST_PROJECT_ID`.

## Msg Agent Service
The Msg Agent is a background service that monitors the Cardano network for cross-chain messages.

### Starting the Agent
```bash
python msg_agent.py preprod
```

### Functions
- **Inbound Processing**: Monitors the `InboundDemo` script. When a cross-chain message is detected (minted by XPort), the agent automatically consumes the UTXO, burns the `InboundToken`, and mints the `DemoToken` to the receiver.
- **Outbound Monitoring**: (Currently Inbound focused) Detects outbound requests to be relayed to EVM.
