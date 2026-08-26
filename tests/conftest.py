import pytest

from src.config import RETURN_WINDOW_DAYS
from src.data_loader import clear_data_cache, load_orders
from src.tools.order_tools import _days_since_delivery


@pytest.fixture(autouse=True)
def reset_data_cache():
    clear_data_cache()
    yield
    clear_data_cache()


@pytest.fixture
def orders():
    return {o["order_id"]: o for o in load_orders()}


def find_order(
    orders: dict,
    *,
    status: str | None = None,
    item_category: str | None = None,
    final_sale: bool | None = None,
    returnable_delivered: bool = False,
) -> dict:
    for order in orders.values():
        if status and order["status"] != status:
            continue
        if returnable_delivered:
            if order["status"] != "delivered":
                continue
            if not all(
                not i.get("final_sale")
                and i.get("category") not in {"innerwear", "jewellery"}
                for i in order["items"]
            ):
                continue
            days = _days_since_delivery(order.get("delivered_at"))
            if days is None or days > RETURN_WINDOW_DAYS:
                continue
        if item_category:
            if not any(i["category"] == item_category for i in order["items"]):
                continue
        if final_sale is not None:
            if not any(i.get("final_sale") == final_sale for i in order["items"]):
                continue
        return order
    pytest.fail(f"No order matching filters: status={status}, category={item_category}")


def find_item(order: dict, **filters) -> dict:
    for item in order["items"]:
        if all(item.get(k) == v for k, v in filters.items()):
            return item
    pytest.fail(f"No item matching {filters} in order {order['order_id']}")


def adjacent_size(item: dict) -> str:
    """Pick a different size on the generic ladder for exchange tests."""
    from src.data_loader import get_available_exchange_sizes

    sizes = get_available_exchange_sizes(
        item["sku"], item["size"], item.get("category", "apparel")
    )
    assert sizes, f"No exchange sizes for {item['sku']}"
    return sizes[0]
