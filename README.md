# Cardano-EVM XPort Bridge Runner (EVM -> Cardano)

Comprehensive Python suite for cross-chain message transactions from EVM (Wanchain Testnet) to Cardano (Preprod) using the XPort protocol.

## 🚀 Features
- **EVM to Cardano Cross-Chain**: Specialized runner for sending messages and tokens from EVM to Cardano.
- **Deterministic HD Wallets**: Derive both Cardano (BIP-1852) and EVM (BIP-44) wallets from a single 24-word mnemonic.
- **Interactive CLI Engine**: Manage wallets, check balances, and initiate cross-chain transfers via a menu-driven interface.
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
The XPort system utilizes multiple functional accounts. This tool simplifies preparation by deriving all roles deterministically from a **single 24-word mnemonic** (BIP-1852 for Cardano, BIP-44 for EVM):

| Role | Wallet Index | Usage |
| :--- | :--- | :--- |
| **User (EVM Source)** | Index 1+ | Initiates bridge transfers from EVM (Option 4 in Runner) |
| **Inbound Agent (Cardano)** | Index 100 | Autonomous settlement of Inbound messages on Cardano (msg_agent.py) |
| **Main Wallet** | Index 0 | Funding and management wallet |

**Steps to Prepare:**
1. Run `python interactive_runner.py`.
2. Select **Option 1 (Create Wallets)**.
3. Enter your existing 24-word mnemonic or press Enter to generate a new one.
4. The tool automatically derives and saves the User and Agent credentials into `current_cardano_wallets.json` and `current_evm_wallets.json`.
5. Use **Option 2/3** in the Runner to check balances and distribute test coins (WAN/Tokens) to EVM batch wallets.

### 1. Interactive Runner (Initiating Transfers)
Use this tool to create wallets, distribute funds, and send bridge messages from EVM.
```bash
python interactive_runner.py
```
- **Option 1**: Create or load wallets from a mnemonic.
- **Option 2/3**: Diagnostic tools to check and distribute WAN/Tokens on EVM.
- **Option 4**: Execute EVM -> Cardano transfers based on CSV test cases.

### 2. Msg Agent Service (Autonomous Settlement)
Run this service in the background to automatically process incoming bridge messages on Cardano.
```bash
python msg_agent.py preprod
```
- **Inbound**: Monitors `InboundDemo`, burns `InboundToken`, and mints `DemoToken` to the beneficiary address on Cardano.

## 📂 Project Structure
- `interactive_runner.py`: CLI entry point.
- `sendtransactions/`: Transaction building logic for EVM (Inbound initiation).
- `utility/`: Wallet HD derivation and asset management backend.
- `config/`: RPC settings, ABIs, and verified contract addresses.
