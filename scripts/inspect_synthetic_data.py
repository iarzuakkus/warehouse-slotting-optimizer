"""Sentetik veri miktarını ve talep dağılımını inceleyen komut."""

import argparse

from sqlalchemy import distinct, func, select

from app.db.session import SessionLocal
from app.models.catalog import Product
from app.models.inventory import Carton, WarehouseLocation
from app.models.orders import Order, OrderLine, PickOperation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sentetik veri kalite özeti")
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Gösterilecek popüler SKU sayısı (varsayılan: 10)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top <= 0:
        raise SystemExit("--top sıfırdan büyük olmalıdır")

    with SessionLocal() as session:
        counts = {
            "Ürün": session.scalar(
                select(func.count(Product.id)).where(Product.sku.like("SYN-%"))
            ),
            "Raf": session.scalar(
                select(func.count(WarehouseLocation.id)).where(
                    WarehouseLocation.aisle.like("SYN-A%")
                )
            ),
            "Koli": session.scalar(
                select(func.count(Carton.id)).where(
                    Carton.carton_number.like("SYN-CARTON-%")
                )
            ),
            "Tamamlanmış sipariş": session.scalar(
                select(func.count(Order.id)).where(
                    Order.order_number.like("SYN-ORD-H-%")
                )
            ),
            "Bekleyen sipariş": session.scalar(
                select(func.count(Order.id)).where(
                    Order.order_number.like("SYN-ORD-P-%")
                )
            ),
            "Toplama hareketi": session.scalar(
                select(func.count(PickOperation.id)).where(
                    PickOperation.operator_reference.like("SYN-OP-%")
                )
            ),
        }

        demand_statement = (
            select(
                Product.sku,
                func.sum(OrderLine.ordered_qty).label("total_quantity"),
                func.count(distinct(OrderLine.order_id)).label("order_frequency"),
            )
            .join(OrderLine, OrderLine.product_id == Product.id)
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Product.sku.like("SYN-%"),
                Order.order_number.like("SYN-ORD-H-%"),
            )
            .group_by(Product.id, Product.sku)
            .order_by(func.sum(OrderLine.ordered_qty).desc())
        )
        demand_rows = list(session.execute(demand_statement))

    print("Sentetik kayıt özeti:")
    for label, value in counts.items():
        print(f"  {label:<22} {value}")

    print(f"\nEn yoğun {min(args.top, len(demand_rows))} SKU:")
    print(f"  {'SKU':<32} {'Adet':>10} {'Sipariş':>10}")
    for sku, total_quantity, order_frequency in demand_rows[: args.top]:
        print(f"  {sku:<32} {total_quantity:>10} {order_frequency:>10}")

    if demand_rows:
        total_demand = sum(int(row.total_quantity) for row in demand_rows)
        top_product_count = max(1, round(len(demand_rows) * 0.20))
        top_demand = sum(
            int(row.total_quantity) for row in demand_rows[:top_product_count]
        )
        concentration = top_demand / total_demand * 100
        print(
            f"\nİlk %20 ürünün toplam talep payı: %{concentration:.2f}"
        )


if __name__ == "__main__":
    main()
