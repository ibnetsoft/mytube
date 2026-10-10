from eth_account import Account
import secrets

def generate_bep20_wallet():
    """Generates a BEP20 (Ethereum-compatible) wallet address and private key."""
    # eth_account requires this for some environments to avoid warnings
    Account.enable_unaudited_hdwallet_features()
    
    # Generate random private key
    priv = secrets.token_hex(32)
    private_key = "0x" + priv
    
    # Get address from private key
    acct = Account.from_key(private_key)
    address = acct.address
    
    return {
        "address": address,
        "private_key": private_key
    }
