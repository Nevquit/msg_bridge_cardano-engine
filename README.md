# Cardano-EVM XPort Bridge Runner

Comprehensive Python suite for cross-chain message transactions between Cardano (Preprod) and EVM (Wanchain Testnet) using the XPort protocol.

## 🚀 Features
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
This tool simplifies preparation by deriving all user accounts deterministically from a **single 24-word mnemonic** (BIP-1852 for Cardano, BIP-44 for EVM).

**Steps to Prepare:**
1. Run `python interactive_runner.py`.
2. Select **Option 1 (Create Wallets)**.
3. Enter your existing 24-word mnemonic or press Enter to generate a new one.
4. The tool automatically derives and saves credentials into `current_cardano_wallets.json` and `current_evm_wallets.json`.
5. Use **Option 2/3** in the Runner to check balances and distribute test coins (ADA/WAN/Tokens) to these accounts.

### 1. Interactive Runner (Initiating Transfers)
Use this tool to create wallets, distribute funds, and send bridge messages.
```bash
python interactive_runner.py
```
- **Option 1**: Create or load wallets from a mnemonic.
- **Option 2/3**: Diagnostic tools to check and distribute ADA/WAN/Tokens.
- **Option 4**: Execute transfers based on CSV test cases.
- **Option 5**: Sweep assets back to a central wallet.

## 📂 Project Structure
- `interactive_runner.py`: CLI entry point.
- `sendtransactions/`: Transaction building logic for Cardano & EVM.
- `utility/`: Wallet HD derivation and asset management backend.
- `config/`: RPC settings, ABIs, and verified contract addresses.
