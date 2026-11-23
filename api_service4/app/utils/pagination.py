def parse_pagination(args, *, default_size=24, max_size=100):
    try:
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", default_size))
    except (TypeError, ValueError):
        raise ValueError("页码和每页条数必须为整数") from None
    if not 1 <= page <= 1_000_000 or not 1 <= page_size <= max_size:
        raise ValueError(f"页码须为 1 至 1000000，每页条数须为 1 至 {max_size}")
    return page, page_size


def pagination_data(page, page_size, total):
    return {"page": page, "page_size": page_size, "total": total}
