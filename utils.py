def paginate(items, page: int = 1, limit: int = 10):
    start = (page - 1) * limit
    end = start + limit
    return items[start:end]

def sort_items(items, sort_by: str):
    if sort_by == "price_asc":
        return sorted(items, key=lambda x: x.get("price", 0))
    if sort_by == "price_desc":
        return sorted(items, key=lambda x: x.get("price", 0), reverse=True)
    if sort_by == "rating_asc":
        return sorted(items, key=lambda x: x.get("rating", 0))
    if sort_by == "rating_desc":
        return sorted(items, key=lambda x: x.get("rating", 0), reverse=True)
    return items
