"""Analiz algoritmaları için toplulaştırılmış salt okunur sorgular."""

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.algorithms.abc_analysis import ProductDemand
from app.models.catalog import Product
from app.models.orders import Order, OrderLine


class AnalysisDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_product_demand(
        self,
        order_number_prefix: str | None = None,
    ) -> list[ProductDemand]:
        """Tamamlanan siparişleri ürün miktarı ve sipariş sıklığına göre toplar."""
        statement = (
            select(
                Product.id,
                Product.sku,
                func.sum(OrderLine.fulfilled_qty).label("total_quantity"),
                func.count(distinct(OrderLine.order_id)).label("order_frequency"),
            )
            .join(OrderLine, OrderLine.product_id == Product.id)
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.status == "completed",
                OrderLine.fulfilled_qty > 0,
            )
            .group_by(Product.id, Product.sku)
            .order_by(func.sum(OrderLine.fulfilled_qty).desc(), Product.sku)
        )
        if order_number_prefix is not None:
            statement = statement.where(
                Order.order_number.like(f"{order_number_prefix}%")
            )

        return [
            ProductDemand(
                product_id=product_id,
                sku=sku,
                total_quantity=int(total_quantity),
                order_frequency=int(order_frequency),
            )
            for product_id, sku, total_quantity, order_frequency in self.session.execute(
                statement
            )
        ]
