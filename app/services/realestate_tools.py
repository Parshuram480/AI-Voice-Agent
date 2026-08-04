"""Gemini tool declarations for the Real Estate Agent."""

def get_realestate_tool_declarations() -> list:
    """
    Returns the Gemini function declarations for real estate-specific tools.
    These are injected into the GeminiLiveClient's tool list.
    """
    return [
        {
            "name": "get_all_listings",
            "description": (
                "Fetch a summary of ALL available properties in the catalog. "
                "Use this at the start of the conversation to know what's available, "
                "or when the user asks to see everything."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "search_properties",
            "description": (
                "Search the property catalog by keyword. Matches property names, "
                "descriptions, features, and neighborhoods. "
                "Use when the user mentions a specific feature like 'pool', 'garage', or a location."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "Search keyword (e.g., 'pool', 'garage', 'downtown', 'luxury').",
                    }
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_property_details",
            "description": (
                "Get full details (price, beds/baths, features, open house, rating) for a specific property. "
                "Use when the user asks about a particular property by name or shows interest in one."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "property_id": {
                        "type": "STRING",
                        "description": "Property ID (e.g., 'PROP-APT-01') or property name (e.g., 'The Metro Lofts').",
                    }
                },
                "required": ["property_id"],
            },
        },
        {
            "name": "get_properties_by_category",
            "description": (
                "List all properties in a specific category. "
                "Available categories: Apartments, Townhomes, Single-Family Homes, Luxury Estates, New Developments."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "category": {
                        "type": "STRING",
                        "description": "Category name (e.g., 'Apartments', 'Single-Family Homes').",
                    }
                },
                "required": ["category"],
            },
        },
        {
            "name": "recommend_property",
            "description": (
                "Get personalized property recommendations based on the user's needs, budget, and family size. "
                "Use this after understanding the user's budget and requirements."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "bedrooms": {
                        "type": "INTEGER",
                        "description": "Minimum number of bedrooms required.",
                    },
                    "budget": {
                        "type": "STRING",
                        "description": "Maximum budget in USD (e.g., '500000'). Leave empty if no budget constraint.",
                    },
                    "category": {
                        "type": "STRING",
                        "description": "Preferred property category (e.g., 'Apartments', 'Single-Family Homes', 'condo').",
                    },
                    "neighborhood_preference": {
                        "type": "STRING",
                        "description": "Preferred neighborhood or area vibe.",
                    }
                },
            },
        },
        {
            "name": "get_neighborhood_info",
            "description": (
                "Get details about a specific neighborhood, including school ratings, walkability, and average prices. "
                "Use when the user asks about the area a property is in."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "neighborhood": {
                        "type": "STRING",
                        "description": "Name of the neighborhood (e.g., 'Greenwood Heights').",
                    }
                },
                "required": ["neighborhood"],
            },
        },
        {
            "name": "get_financing_options",
            "description": (
                "Get available mortgage types, interest rates, and down payment requirements. "
                "Use when the user asks about financing, loans, or affordability."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
    ]
