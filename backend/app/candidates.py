"""Catalog search (PLAN.md section 4.7). No electrical filtering: traps must reach the comparison."""

from app.catalog import all_parts
from app.schemas import Category, PartSpec


def search_candidates(
    category: str | Category,
    preferred_manufacturer: str,
    original_mpn: str,
    include_synthetic: bool = False,
    limit: int = 8,
) -> list[PartSpec]:
    category = Category(category)
    original = original_mpn.strip().lower()
    preferred = (preferred_manufacturer or "").strip().lower()
    found = [
        p for p in all_parts()
        if p.category == category and p.verified and p.mpn.lower() != original and (include_synthetic or not p.synthetic)
    ]
    found.sort(key=lambda p: (p.manufacturer.strip().lower() != preferred, p.mpn))
    return found[:limit]
