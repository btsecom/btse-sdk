"""
Configuration file for BTSE SDK examples.

Update your API credentials here. All examples will reference this file.
"""

# =============================================================================
# API CREDENTIALS
# =============================================================================

# Testnet credentials (safe for testing)
TESTNET_API_KEY = "API KEY"
TESTNET_API_SECRET = "API SECRET"

# Production credentials (CAUTION: Real trading!)
PROD_API_KEY = "API KEY"
PROD_API_SECRET = "API SECRET"

# =============================================================================
# ENVIRONMENT SETTINGS
# =============================================================================

# Set to True for testnet, False for production
USE_TESTNET = False


# =============================================================================
# WEBSOCKET SETTINGS
# =============================================================================

# Orderbook grouping level (0 = no grouping, highest precision)
ORDERBOOK_GROUPING = 0

# Update interval in seconds for live displays
UPDATE_INTERVAL = 0.2

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_spot_credentials():
    """Get spot API credentials based on environment."""
    if USE_TESTNET:
        return TESTNET_API_KEY, TESTNET_API_SECRET
    return PROD_API_KEY, PROD_API_SECRET

def get_futures_credentials():
    """Get futures API credentials based on environment."""
    if USE_TESTNET:
        return TESTNET_API_KEY, TESTNET_API_SECRET
    return PROD_API_KEY, PROD_API_SECRET

def get_environment_name():
    """Get current environment name."""
    return "TESTNET" if USE_TESTNET else "PRODUCTION"

# =============================================================================
# VALIDATION
# =============================================================================

if not USE_TESTNET:
    print("⚠️  WARNING: Using PRODUCTION environment with REAL funds!")
    print("   Set USE_TESTNET=True in config.py to use testnet instead.")
    print()