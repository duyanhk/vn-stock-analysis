import os


def _env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).lower() in ("true", "1", "yes")


class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DEBUG = True
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    SELENIUM_HEADLESS = True
    SELENIUM_WINDOW_SIZE = "1920,1080"
    SELENIUM_TIMEOUT = 20

    # When True, /run_financials will serve data from a saved JSON sample
    # instead of running live APIs. For deployment demo: USE_SAMPLE_DATA=True
    USE_SAMPLE_DATA = _env_bool("USE_SAMPLE_DATA", "false")

    # When True, Vietstock Selenium scraper is used as fallback when VNStock fails.
    # Set False for cloud deployment (Render, Railway, etc.) where Chrome is unavailable.
    # ENABLE_SELENIUM=True python run.py  # local/VPS with Chrome
    ENABLE_SELENIUM = _env_bool("ENABLE_SELENIUM", "false")

    # Financial data settings (VNStock)
    USE_VNSTOCK_PRIMARY = _env_bool("USE_VNSTOCK_PRIMARY", "true")  # Use VNStock as primary data source
    # VCI default (more years, IBD, Financial Income); KBS fallback (TCBS deprecated, SSI not supported for financials)
    VNSTOCK_FINANCIAL_PROVIDERS = ["vci", "kbs"]
    VNSTOCK_INCLUDE_QUARTERLY = _env_bool("VNSTOCK_INCLUDE_QUARTERLY", "true")  # Fetch quarterly data for T4Q/valuation (uses 2x API calls)
    
    # Market data settings (VNStock)
    VNSTOCK_DEFAULT_SOURCE = "VCI"  # VCI or KBS (TCBS deprecated as of March 2026)
    VNSTOCK_FALLBACK_SOURCES = ["KBS"]  # Removed TCBS - no longer accessible
    MARKET_SAMPLE_LIMIT = 3  # Max market data samples to keep (consistent with financial data)
    # Price history: when no start/end given, use this many years starting Jan 1 of that year
    MARKET_PRICE_YEARS = 5


class ProductionConfig(Config):
    DEBUG = False
    VNSTOCK_FINANCIAL_PROVIDERS = ["vci", "kbs"]
    VNSTOCK_INCLUDE_QUARTERLY = _env_bool("VNSTOCK_INCLUDE_QUARTERLY", "true")


class DevelopmentConfig(Config):
    DEBUG = True

