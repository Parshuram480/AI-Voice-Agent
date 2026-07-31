"""Executor for real estate agent tools — reads from a JSON property catalog."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from google.genai import types

logger = logging.getLogger(__name__)


class RealEstateToolExecutor:
    """Executes real estate-specific tool calls against an in-memory property catalog loaded from JSON."""

    def __init__(self, catalog_path: str = "client_configs/realestate_listings.json"):
        self.catalog_path = Path(catalog_path)
        self._catalog: Dict[str, Any] = {}
        self._properties: List[Dict[str, Any]] = []
        self._neighborhoods: List[Dict[str, Any]] = []
        self._financing: List[Dict[str, Any]] = []
        self._company: Dict[str, Any] = {}
        # Fake execution_map so the filler service doesn't crash
        self.execution_map: Dict[str, dict] = {}
        self._load_catalog()

    def _load_catalog(self):
        """Load the property catalog from the JSON file."""
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self._catalog = json.load(f)
            self._properties = self._catalog.get("properties", [])
            self._neighborhoods = self._catalog.get("neighborhoods", [])
            self._financing = self._catalog.get("financing_options", [])
            self._company = self._catalog.get("company", {})
            logger.info(
                f"Loaded real estate catalog: {len(self._properties)} properties, "
                f"{len(self._neighborhoods)} neighborhoods from {self.catalog_path}"
            )

            # Build execution map for filler audio hints
            self.execution_map = {
                "get_all_listings": {"filler_category": "lookup", "expected_latency": "fast"},
                "search_properties": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_property_details": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_properties_by_category": {"filler_category": "lookup", "expected_latency": "fast"},
                "recommend_property": {"filler_category": "thinking", "expected_latency": "medium"},
                "get_neighborhood_info": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_financing_options": {"filler_category": "lookup", "expected_latency": "fast"},
            }
        except Exception as e:
            logger.error(f"Failed to load real estate catalog from {self.catalog_path}: {e}")

    async def execute(
        self, tool_call_id: str, name: str, args: dict, state: dict
    ) -> types.FunctionResponse:
        """Execute a real estate tool and return a Gemini FunctionResponse."""
        logger.info(f"[REALESTATE] Executing tool: {name} with args: {args}")

        try:
            if name == "get_all_listings":
                return self._get_all_listings(tool_call_id, name)

            elif name == "search_properties":
                query = args.get("query", "").lower()
                return self._search_properties(tool_call_id, name, query)

            elif name == "get_property_details":
                property_id = args.get("property_id", "")
                return self._get_property_details(tool_call_id, name, property_id)

            elif name == "get_properties_by_category":
                category = args.get("category", "")
                return self._get_properties_by_category(tool_call_id, name, category)

            elif name == "recommend_property":
                bedrooms = args.get("bedrooms")
                budget = args.get("budget", "")
                neighborhood = args.get("neighborhood_preference", "")
                category = args.get("category", "")
                return self._recommend_property(tool_call_id, name, bedrooms, budget, neighborhood, category)
                
            elif name == "get_neighborhood_info":
                neighborhood = args.get("neighborhood", "")
                return self._get_neighborhood_info(tool_call_id, name, neighborhood)
                
            elif name == "get_financing_options":
                return self._get_financing_options(tool_call_id, name)

            else:
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={"error": f"Unknown real estate tool: {name}"},
                )

        except Exception as e:
            logger.error(f"[REALESTATE] Error executing {name}: {e}")
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"error": f"Tool execution error: {str(e)}"},
            )

    # -------------------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------------------

    def _get_all_listings(self, tool_call_id: str, name: str) -> types.FunctionResponse:
        """Return a summary list of all properties."""
        summary = []
        for p in self._properties:
            summary.append({
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price": p["price"],
                "status": p["status"],
                "neighborhood": p["neighborhood"],
                "bedrooms": p["bedrooms"],
                "bathrooms": p["bathrooms"],
            })
        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={
                "properties": summary,
                "total": len(summary),
                "categories": self._catalog.get("categories", []),
            },
        )

    def _search_properties(
        self, tool_call_id: str, name: str, query: str
    ) -> types.FunctionResponse:
        """Search properties by keyword."""
        if not query:
            return self._get_all_listings(tool_call_id, name)

        results = []
        for p in self._properties:
            searchable = " ".join([
                p["name"].lower(),
                p["category"].lower(),
                p["description"].lower(),
                p["neighborhood"].lower(),
                " ".join(p.get("features", [])).lower(),
            ])
            if query in searchable:
                results.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "category": p.get("category"),
                    "price": p.get("price"),
                    "status": p.get("status"),
                    "description": p.get("description", ""),
                    "neighborhood": p.get("neighborhood"),
                    "features": p.get("features", []),
                })

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"results": results, "count": len(results), "query": query},
        )

    def _get_property_details(
        self, tool_call_id: str, name: str, property_id: str
    ) -> types.FunctionResponse:
        """Get full details for a specific property."""
        property_obj = None

        # Search by ID
        for p in self._properties:
            if p.get("id", "").lower() == property_id.lower():
                property_obj = p
                break

        # Fallback: search by name substring
        if not property_obj:
            for p in self._properties:
                if property_id.lower() in p.get("name", "").lower():
                    property_obj = p
                    break

        if not property_obj:
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"error": f"Property '{property_id}' not found."},
            )

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"property": property_obj},
        )

    def _get_properties_by_category(
        self, tool_call_id: str, name: str, category: str
    ) -> types.FunctionResponse:
        """Get all properties in a specific category."""
        matches = [p for p in self._properties if p.get("category", "").lower() == category.lower()]

        if not matches:
            available = self._catalog.get("categories", [])
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={
                    "error": f"No properties found in category '{category}'.",
                    "available_categories": available,
                },
            )

        results = [{
            "id": p.get("id"),
            "name": p.get("name"),
            "price": p.get("price"),
            "status": p.get("status"),
            "neighborhood": p.get("neighborhood"),
            "bedrooms": p.get("bedrooms"),
            "bathrooms": p.get("bathrooms"),
        } for p in matches]

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"category": category, "properties": results, "count": len(results)},
        )
        
    def _get_neighborhood_info(
        self, tool_call_id: str, name: str, neighborhood: str
    ) -> types.FunctionResponse:
        """Get info about a neighborhood."""
        for n in self._neighborhoods:
            if neighborhood.lower() in n.get("name", "").lower():
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={"neighborhood": n},
                )
                
        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"error": f"Neighborhood '{neighborhood}' not found.", "available": [n["name"] for n in self._neighborhoods]},
        )
        
    def _get_financing_options(
        self, tool_call_id: str, name: str
    ) -> types.FunctionResponse:
        """Get financing options."""
        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"financing_options": self._financing},
        )

    def _recommend_property(
        self, tool_call_id: str, name: str, bedrooms: int = None, budget: str = "", neighborhood: str = "", category: str = ""
    ) -> types.FunctionResponse:
        """Recommend properties based on requirements."""
        max_budget = None
        if budget:
            try:
                max_budget = float(budget.replace("$", "").replace(",", "").strip())
            except ValueError:
                pass
                
        neighborhood_lower = neighborhood.lower() if neighborhood else ""
        category_lower = category.lower() if category else ""

        scored = []
        for p in self._properties:
            if p.get("status") != "available":
                continue
                
            if max_budget:
                import re
                match = re.search(r'\d+\.?\d*', str(p.get("price")).replace(",", ""))
                if match:
                    price_val = float(match.group())
                    if price_val > max_budget:
                        continue

            score = 0
            if bedrooms and p.get("bedrooms", 0) >= bedrooms:
                score += 2
                
            if neighborhood_lower and neighborhood_lower in p.get("neighborhood", "").lower():
                score += 3
                
            if category_lower:
                p_cat = p.get("category", "").lower()
                # Handle synonyms
                if category_lower in p_cat or p_cat in category_lower:
                    score += 4
                elif ("condo" in category_lower or "apartment" in category_lower) and ("apartment" in p_cat or "condo" in p_cat.lower() or "condo" in p.get("name", "").lower()):
                    score += 4
                
            if score > 0 or (not bedrooms and not neighborhood_lower and not category_lower):
                scored.append({"property": p, "relevance_score": score})

        # Sort by relevance then rating
        scored.sort(key=lambda x: (x["relevance_score"], x["property"].get("rating", 0)), reverse=True)

        recommendations = []
        for item in scored[:3]:
            p = item["property"]
            recommendations.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "price": p.get("price"),
                "neighborhood": p.get("neighborhood"),
                "bedrooms": p.get("bedrooms"),
                "bathrooms": p.get("bathrooms"),
                "description": p.get("description", ""),
                "open_house": p.get("open_house", ""),
            })

        response_data = {
            "recommendations": recommendations,
            "count": len(recommendations),
        }

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response=response_data,
        )
