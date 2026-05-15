# Cardano-EVM XPort Bridge Runner

Comprehensive Python suite for cross-chain message transactions between Cardano (Preprod) and EVM (Wanchain Testnet) using the XPort protocol.

## 🚀 Features
- **Deterministic HD Wallets**: Derive both Cardano (BIP-1852) and EVM (BIP-44) wallets from a single 24-word mnemonic.
- **Interactive CLI Engine**: Manage wallets, check balances, and initiate cross-chain transfers via a menu-driven interface.
- **Autonomous Msg Agent**: Standalone service to monitor script addresses and automatically settle Cardano-side bridge settlements.
- **Protocol Excellence**: Custom CBOR recursive encoder for indefinite-length nesting required by Plutus scripts.

## 🛠️ Setup
1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure Environment**: Create a `.env` file and add your Blockfrost API key:
   ```env
   YOUR_BLOCKFROST_PROJECT_ID=your_id_here
   ```

## 📖 Usage Guide

### 1. Interactive Runner (Initiating Transfers)
Use this tool to create wallets, distribute funds, and send bridge messages.
```bash
python interactive_runner.py
```
- **Option 1**: Create or load wallets from a mnemonic.
- **Option 2/3**: Diagnostic tools to check and distribute ADA/WAN/Tokens.
- **Option 4**: Execute transfers based on CSV test cases.

### 2. Msg Agent Service (Autonomous Settlement)
Run this service in the background to automatically process incoming/outgoing bridge messages on Cardano.
```bash
python msg_agent.py preprod
```
- **Inbound**: Monitors `InboundDemo`, burns `InboundToken`, and mints `DemoToken` to the receiver.
- **Outbound**: Monitors `OutboundDemo`, burns `DemoToken`, and relays to `XPort`.

## 📂 Project Structure
- `interactive_runner.py`: CLI entry point.
- `msg_agent.py`: Autonomous background service.
- `sendtransactions/`: Transaction building logic for Cardano & EVM.
- `utility/`: Wallet HD derivation and asset management backend.
- `config/`: RPC settings, ABIs, and verified contract addresses.
