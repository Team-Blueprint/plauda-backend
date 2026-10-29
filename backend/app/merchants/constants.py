"""PayPal-supported currencies (Orders v2). Verify against PayPal docs in Phase 4."""

PAYPAL_SUPPORTED_CURRENCIES: frozenset[str] = frozenset(
    {
        "AUD",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "ILS",
        "JPY",
        "MXN",
        "MYR",
        "NOK",
        "NZD",
        "PHP",
        "PLN",
        "SEK",
        "SGD",
        "THB",
        "TWD",
        "USD",
    }
)

MAX_PRODUCT_IMAGES = 5

BUSINESS_INFO_SOURCES: tuple[str, ...] = ("about", "policies", "faq")
