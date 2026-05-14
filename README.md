# Cardano-EVM XPort Bridge Runner

Interactive CLI for cross-chain transactions between Cardano (Preprod) and EVM (Wanchain Testnet).

## Setup
1. `pip install -r requirements.txt`
2. Create `.env` with `YOUR_BLOCKFROST_PROJECT_ID`.

## Manual UTXO Consumption (EVM -> Cardano)
If the monitor agent is not running, you can manually consume inbound UTXOs:
1. Select EVM -> Cardano direction.
2. Select Option 5 (Consume UTXO).
3. Provide the Cardano TX Hash and Index where the message is locked.
4. The tool uses batch wallet #1 for collateral and script witnesses.
