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

### 0. Wallet Preparation
The XPort system requires three distinct functional accounts. This tool simplifies preparation by deriving all roles deterministically from a **single 24-word mnemonic** (BIP-1852 for Cardano, BIP-44 for EVM):

| Role | Wallet Index | Usage |
| :--- | :--- | :--- |
| **User** | Index 0 (Main) | Initiates transfers (Options 4 in Runner) |
| **Inbound Agent** | Index 1 (Batch 1) | Automates Inbound settlements (EVM -> Cardano) |
| **Outbound Agent** | Index 2 (Batch 2) | Automates Outbound relays (Cardano -> EVM) |

**Steps to Prepare:**
1. Run `python interactive_runner.py`.
2. Select **Option 1 (Create Wallets)**.
3. Enter your existing 24-word mnemonic or press Enter to generate a new one.
4. The tool automatically derives and saves the User and Agent credentials into `current_cardano_wallets.json` and `current_evm_wallets.json`.
5. Use **Option 2/3** in the Runner to check balances and distribute test coins (ADA/WAN/Tokens) to these accounts.

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
