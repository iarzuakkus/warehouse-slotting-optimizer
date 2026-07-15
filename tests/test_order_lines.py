"""Sipariş satırı CRUD endpoint testleri."""

from fastapi.testclient import TestClient


def create_product(db_client: TestClient, sku: str = "TEST-LINE-PRODUCT") -> int:
    response = db_client.post(
        "/products",
        json={"sku": sku, "name": "Siparis Satiri Urunu", "is_active": True},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_order(db_client: TestClient, number: str = "TEST-LINE-ORDER") -> int:
    response = db_client.post("/orders", json={"order_number": number})
    assert response.status_code == 201
    return response.json()["id"]


def test_order_line_lifecycle(db_client: TestClient) -> None:
    order_id = create_order(db_client)
    product_id = create_product(db_client)
    create_response = db_client.post(
        f"/orders/{order_id}/lines",
        json={"product_id": product_id, "ordered_qty": 12},
    )
    assert create_response.status_code == 201
    line_id = create_response.json()["id"]
    assert create_response.json()["fulfilled_qty"] == 0

    list_response = db_client.get(f"/orders/{order_id}/lines")
    update_response = db_client.patch(
        f"/orders/{order_id}/lines/{line_id}", json={"ordered_qty": 24}
    )
    delete_response = db_client.delete(f"/orders/{order_id}/lines/{line_id}")
    final_response = db_client.get(f"/orders/{order_id}/lines/{line_id}")

    assert [item["id"] for item in list_response.json()] == [line_id]
    assert update_response.status_code == 200
    assert update_response.json()["ordered_qty"] == 24
    assert delete_response.status_code == 204
    assert final_response.status_code == 404


def test_order_line_rejects_missing_references(db_client: TestClient) -> None:
    missing_order = db_client.post(
        "/orders/999999999/lines", json={"product_id": 999999999, "ordered_qty": 1}
    )
    order_id = create_order(db_client, "TEST-LINE-MISSING-PRODUCT")
    missing_product = db_client.post(
        f"/orders/{order_id}/lines",
        json={"product_id": 999999999, "ordered_qty": 1},
    )
    assert missing_order.status_code == 404
    assert missing_product.status_code == 404


def test_order_line_rejects_duplicate_product(db_client: TestClient) -> None:
    order_id = create_order(db_client, "TEST-LINE-DUPLICATE")
    product_id = create_product(db_client, "TEST-LINE-PRODUCT-DUPLICATE")
    payload = {"product_id": product_id, "ordered_qty": 5}
    first = db_client.post(f"/orders/{order_id}/lines", json=payload)
    duplicate = db_client.post(f"/orders/{order_id}/lines", json=payload)
    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_order_lines_are_locked_after_order_leaves_pending(
    db_client: TestClient,
) -> None:
    order_id = create_order(db_client, "TEST-LINE-LOCKED")
    product_id = create_product(db_client, "TEST-LINE-PRODUCT-LOCKED")
    status_response = db_client.patch(
        f"/orders/{order_id}", json={"status": "allocated"}
    )
    create_response = db_client.post(
        f"/orders/{order_id}/lines",
        json={"product_id": product_id, "ordered_qty": 5},
    )
    assert status_response.status_code == 200
    assert create_response.status_code == 409


def test_order_line_validates_quantity(db_client: TestClient) -> None:
    order_id = create_order(db_client, "TEST-LINE-QUANTITY")
    product_id = create_product(db_client, "TEST-LINE-PRODUCT-QUANTITY")
    response = db_client.post(
        f"/orders/{order_id}/lines",
        json={"product_id": product_id, "ordered_qty": 0},
    )
    assert response.status_code == 422
