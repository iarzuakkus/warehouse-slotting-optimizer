"""PostgreSQL siparişleri üzerinde ABC analizini çalıştıran komut."""

import argparse
from collections import Counter

from app.db.session import SessionLocal
from app.services.abc_analysis import ABCAnalysisService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ürün talebi ABC analizi")
    parser.add_argument("--a-threshold", type=float, default=0.80)
    parser.add_argument("--b-threshold", type=float, default=0.95)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--all-data",
        action="store_true",
        help="Sentetik siparişlerle sınırlamak yerine tüm tamamlanmış siparişleri kullan",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top <= 0:
        raise SystemExit("--top sıfırdan büyük olmalıdır")

    with SessionLocal() as session:
        results = ABCAnalysisService(session).run_analysis(
            synthetic_only=not args.all_data,
            a_threshold=args.a_threshold,
            b_threshold=args.b_threshold,
        )

    if not results:
        print("ABC analizi için tamamlanmış sipariş verisi bulunamadı.")
        return

    class_counts = Counter(item.abc_class for item in results)
    demand_by_class = Counter()
    for item in results:
        demand_by_class[item.abc_class] += item.total_quantity
    total_demand = sum(item.total_quantity for item in results)

    print("ABC sınıf özeti:")
    for abc_class in ("A", "B", "C"):
        quantity = demand_by_class[abc_class]
        demand_share = quantity / total_demand * 100
        print(
            f"  {abc_class}: {class_counts[abc_class]:>3} ürün, "
            f"{quantity:>6} adet, talep payı %{demand_share:>6.2f}"
        )

    shown_count = min(args.top, len(results))
    print(f"\nEn yoğun {shown_count} ürün:")
    print(
        f"  {'SKU':<32} {'Adet':>8} {'Sipariş':>8} "
        f"{'Pay':>8} {'Kümülatif':>11} {'Sınıf':>6}"
    )
    for item in results[:shown_count]:
        print(
            f"  {item.sku:<32} {item.total_quantity:>8} "
            f"{item.order_frequency:>8} %{item.demand_share * 100:>7.2f} "
            f"%{item.cumulative_share * 100:>10.2f} {item.abc_class:>6}"
        )


if __name__ == "__main__":
    main()
