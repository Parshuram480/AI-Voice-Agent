"""Executor for sales agent tools — reads from a JSON product catalog (no database)."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from google.genai import types

logger = logging.getLogger(__name__)


class SalesToolExecutor:
    """Executes sales-specific tool calls against an in-memory product catalog loaded from JSON."""

    def __init__(self, catalog_path: str = "data/sales_products.json"):
        self.catalog_path = Path(catalog_path)
        self._catalog: Dict[str, Any] = {}
        self._products: List[Dict[str, Any]] = []
        self._bundles: List[Dict[str, Any]] = []
        self._company: Dict[str, Any] = {}
        # Fake execution_map so the filler service doesn't crash
        self.execution_map: Dict[str, dict] = {}
        self._load_catalog()

    def _load_catalog(self):
        """Load the product catalog from the JSON file."""
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self._catalog = json.load(f)
            self._products = self._catalog.get("products", [])
            self._bundles = self._catalog.get("bundles", [])
            self._company = self._catalog.get("company", {})
            logger.info(
                f"Loaded sales catalog: {len(self._products)} products, "
                f"{len(self._bundles)} bundles from {self.catalog_path}"
            )

            # Build execution map for filler audio hints
            self.execution_map = {
                "get_all_products": {"filler_category": "lookup", "expected_latency": "fast"},
                "search_products": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_product_details": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_products_by_category": {"filler_category": "lookup", "expected_latency": "fast"},
                "get_bundles": {"filler_category": "lookup", "expected_latency": "fast"},
                "check_stock": {"filler_category": "lookup", "expected_latency": "fast"},
                "recommend_product": {"filler_category": "thinking", "expected_latency": "medium"},
            }
        except Exception as e:
            logger.error(f"Failed to load sales catalog from {self.catalog_path}: {e}")

    async def execute(
        self, tool_call_id: str, name: str, args: dict, state: dict
    ) -> types.FunctionResponse:
        """Execute a sales tool and return a Gemini FunctionResponse."""
        logger.info(f"[SALES] Executing tool: {name} with args: {args}")

        try:
            if name == "get_all_products":
                return self._get_all_products(tool_call_id, name)

            elif name == "search_products":
                query = args.get("query", "").lower()
                return self._search_products(tool_call_id, name, query)

            elif name == "get_product_details":
                product_id = args.get("product_id", "")
                return self._get_product_details(tool_call_id, name, product_id)

            elif name == "get_products_by_category":
                category = args.get("category", "")
                return self._get_products_by_category(tool_call_id, name, category)

            elif name == "get_bundles":
                return self._get_bundles(tool_call_id, name)

            elif name == "check_stock":
                product_id = args.get("product_id", "")
                return self._check_stock(tool_call_id, name, product_id)

            elif name == "recommend_product":
                use_case = args.get("use_case", "")
                budget = args.get("budget", "")
                return self._recommend_product(tool_call_id, name, use_case, budget)

            else:
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={"error": f"Unknown sales tool: {name}"},
                )

        except Exception as e:
            logger.error(f"[SALES] Error executing {name}: {e}")
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"error": f"Tool execution error: {str(e)}"},
            )

    # -------------------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------------------

    def _get_all_products(self, tool_call_id: str, name: str) -> types.FunctionResponse:
        """Return a summary list of all products."""
        summary = []
        for p in self._products:
            summary.append({
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price": p["price"],
                "in_stock": p["in_stock"],
                "rating": p["rating"],
                "discount": p.get("discount"),
            })
        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={
                "products": summary,
                "total": len(summary),
                "categories": self._catalog.get("categories", []),
            },
        )

    def _search_products(
        self, tool_call_id: str, name: str, query: str
    ) -> types.FunctionResponse:
        """Search products by name, category, description, or features."""
        if not query:
            return self._get_all_products(tool_call_id, name)

        results = []
        for p in self._products:
            searchable = " ".join([
                p["name"].lower(),
                p["category"].lower(),
                p["short_description"].lower(),
                p.get("best_for", "").lower(),
                " ".join(p.get("features", [])).lower(),
            ])
            if query in searchable:
                results.append({
                    "id": p["id"],
                    "name": p["name"],
                    "category": p["category"],
                    "price": p["price"],
                    "short_description": p["short_description"],
                    "in_stock": p["in_stock"],
                    "discount": p.get("discount"),
                })

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"results": results, "count": len(results), "query": query},
        )

    def _get_product_details(
        self, tool_call_id: str, name: str, product_id: str
    ) -> types.FunctionResponse:
        """Get full details for a specific product by ID or name."""
        product = None

        # Search by ID
        for p in self._products:
            if p["id"].lower() == product_id.lower():
                product = p
                break

        # Fallback: search by name substring
        if not product:
            for p in self._products:
                if product_id.lower() in p["name"].lower():
                    product = p
                    break

        if not product:
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={"error": f"Product '{product_id}' not found."},
            )

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"product": product},
        )

    def _get_products_by_category(
        self, tool_call_id: str, name: str, category: str
    ) -> types.FunctionResponse:
        """Get all products in a specific category."""
        matches = [p for p in self._products if p["category"].lower() == category.lower()]

        if not matches:
            available = self._catalog.get("categories", [])
            return types.FunctionResponse(
                name=name,
                id=tool_call_id,
                response={
                    "error": f"No products found in category '{category}'.",
                    "available_categories": available,
                },
            )

        results = [{
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "short_description": p["short_description"],
            "in_stock": p["in_stock"],
            "rating": p["rating"],
            "discount": p.get("discount"),
        } for p in matches]

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"category": category, "products": results, "count": len(results)},
        )

    def _get_bundles(self, tool_call_id: str, name: str) -> types.FunctionResponse:
        """Return all available product bundles."""
        bundles_info = []
        for b in self._bundles:
            # Resolve product names
            product_names = []
            for pid in b.get("products", []):
                for p in self._products:
                    if p["id"] == pid:
                        product_names.append(p["name"])
                        break

            bundles_info.append({
                "name": b["name"],
                "products": product_names,
                "bundle_price": b["bundle_price"],
                "savings": b["savings"],
                "description": b["description"],
            })

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"bundles": bundles_info, "count": len(bundles_info)},
        )

    def _check_stock(
        self, tool_call_id: str, name: str, product_id: str
    ) -> types.FunctionResponse:
        """Check if a specific product is in stock."""
        for p in self._products:
            if p["id"].lower() == product_id.lower() or product_id.lower() in p["name"].lower():
                return types.FunctionResponse(
                    name=name,
                    id=tool_call_id,
                    response={
                        "product": p["name"],
                        "in_stock": p["in_stock"],
                        "message": f"{p['name']} is {'available' if p['in_stock'] else 'currently out of stock'}.",
                    },
                )

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response={"error": f"Product '{product_id}' not found."},
        )

    def _recommend_product(
        self, tool_call_id: str, name: str, use_case: str, budget: str
    ) -> types.FunctionResponse:
        """Recommend products based on use case and optional budget."""
        use_case_lower = use_case.lower() if use_case else ""
        max_budget = None
        if budget:
            try:
                max_budget = float(budget.replace("$", "").replace(",", "").strip())
            except ValueError:
                pass

        scored = []
        for p in self._products:
            if not p["in_stock"]:
                continue
            if max_budget and p["price"] > max_budget:
                continue

            score = 0
            searchable = " ".join([
                p.get("best_for", "").lower(),
                p["category"].lower(),
                p["short_description"].lower(),
                " ".join(p.get("features", [])).lower(),
            ])

            # Score by keyword match
            for word in use_case_lower.split():
                if word in searchable:
                    score += 1

            if score > 0:
                scored.append({"product": p, "relevance_score": score})

        # Sort by relevance then rating
        scored.sort(key=lambda x: (x["relevance_score"], x["product"]["rating"]), reverse=True)

        recommendations = []
        for item in scored[:3]:
            p = item["product"]
            recommendations.append({
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "why": p["best_for"],
                "short_description": p["short_description"],
                "discount": p.get("discount"),
                "rating": p["rating"],
            })

        # If no keyword matches, return top-rated in-stock products
        if not recommendations:
            fallback = sorted(
                [p for p in self._products if p["in_stock"] and (not max_budget or p["price"] <= max_budget)],
                key=lambda p: p["rating"],
                reverse=True,
            )[:3]
            recommendations = [{
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "why": p["best_for"],
                "short_description": p["short_description"],
                "discount": p.get("discount"),
                "rating": p["rating"],
            } for p in fallback]

        # Also suggest a relevant bundle if any
        suggested_bundle = None
        rec_ids = {r["id"] for r in recommendations}
        for b in self._bundles:
            if any(pid in rec_ids for pid in b.get("products", [])):
                product_names = []
                for pid in b["products"]:
                    for p in self._products:
                        if p["id"] == pid:
                            product_names.append(p["name"])
                suggested_bundle = {
                    "name": b["name"],
                    "products": product_names,
                    "bundle_price": b["bundle_price"],
                    "savings": b["savings"],
                }
                break

        response_data = {
            "recommendations": recommendations,
            "count": len(recommendations),
        }
        if suggested_bundle:
            response_data["suggested_bundle"] = suggested_bundle

        return types.FunctionResponse(
            name=name,
            id=tool_call_id,
            response=response_data,
        )
