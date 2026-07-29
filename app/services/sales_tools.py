"""Gemini tool declarations for the Sales Agent."""


def get_sales_tool_declarations() -> list:
    """
    Returns the Gemini function declarations for sales-specific tools.
    These are injected into the GeminiLiveClient's tool list alongside
    the global call-flow tools (end_call, out_of_scope).
    """
    return [
        {
            "name": "get_all_products",
            "description": (
                "Fetch a summary of ALL products in the catalog. "
                "Use this at the start of the conversation to know what's available, "
                "or when the user asks to see everything."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "search_products",
            "description": (
                "Search the product catalog by keyword. Matches product names, "
                "descriptions, features, and categories. "
                "Use when the user mentions a specific product type or feature."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "Search keyword (e.g., 'earbuds', 'waterproof', 'fitness', 'charger').",
                    }
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_product_details",
            "description": (
                "Get full details (features, price, discount, rating) for a specific product. "
                "Use when the user asks about a particular product by name or shows interest in one."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "product_id": {
                        "type": "STRING",
                        "description": "Product ID (e.g., 'TNS-001') or product name (e.g., 'Nova Smart Hub Pro').",
                    }
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "get_products_by_category",
            "description": (
                "List all products in a specific category. "
                "Available categories: Smart Home, Audio, Wearables, Accessories."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "category": {
                        "type": "STRING",
                        "description": "Category name: 'Smart Home', 'Audio', 'Wearables', or 'Accessories'.",
                    }
                },
                "required": ["category"],
            },
        },
        {
            "name": "get_bundles",
            "description": (
                "Get all available product bundle deals. "
                "Use when the user is interested in deals, combos, or wants to save money."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "check_stock",
            "description": (
                "Check if a specific product is currently in stock. "
                "Use when the user asks about availability before committing."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "product_id": {
                        "type": "STRING",
                        "description": "Product ID or name to check stock for.",
                    }
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "recommend_product",
            "description": (
                "Get personalized product recommendations based on the user's needs and budget. "
                "Use this after understanding the user's interests, use case, or constraints."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "use_case": {
                        "type": "STRING",
                        "description": "What the user needs the product for (e.g., 'working out', 'home automation', 'travel').",
                    },
                    "budget": {
                        "type": "STRING",
                        "description": "Optional max budget in USD (e.g., '100', '200'). Leave empty if no budget constraint.",
                    },
                },
                "required": ["use_case"],
            },
        },
    ]
