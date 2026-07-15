"""PostgreSQL siparişleri üzerinde FP-Growth analizi çalıştırır."""

import argparse

from app.db.session import SessionLocal
from app.services.fp_growth_analysis import FPGrowthAnalysisService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ürün birlikteliği FP-Growth analizi")
    parser.add_argument("--min-support", type=float, default=0.05)
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--min-lift", type=float, default=1.0)
    parser.add_argument("--max-length", type=int, default=3)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--all-data",
        action="store_true",
        help="Yalnızca sentetik siparişler yerine tüm tamamlanmış siparişleri kullan",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top <= 0:
        raise SystemExit("--top sıfırdan büyük olmalıdır")

    with SessionLocal() as session:
        analysis = FPGrowthAnalysisService(session).run_analysis(
            synthetic_only=not args.all_data,
            minimum_support=args.min_support,
            minimum_confidence=args.min_confidence,
            minimum_lift=args.min_lift,
            maximum_length=args.max_length,
        )

    grouped_itemsets = [itemset for itemset in analysis.itemsets if len(itemset.items) > 1]
    print("FP-Growth özeti:")
    print(f"  Analiz edilen sipariş: {analysis.transaction_count}")
    print(f"  Sık ürün kümesi:       {len(analysis.itemsets)}")
    print(f"  Çoklu ürün kümesi:     {len(grouped_itemsets)}")
    print(f"  İlişki kuralı:         {len(analysis.rules)}")

    shown_itemsets = grouped_itemsets[: args.top]
    print(f"\nEn sık {len(shown_itemsets)} ürün grubu:")
    print(f"  {'Ürünler':<70} {'Sayı':>7} {'Support':>9}")
    for itemset in shown_itemsets:
        items = " + ".join(itemset.items)
        print(
            f"  {items:<70} {itemset.support_count:>7} "
            f"%{itemset.support * 100:>8.2f}"
        )

    shown_rules = analysis.rules[: args.top]
    print(f"\nEn güçlü {len(shown_rules)} ilişki kuralı:")
    print(
        f"  {'Kural':<76} {'Support':>9} {'Confidence':>12} {'Lift':>8}"
    )
    for rule in shown_rules:
        antecedent = " + ".join(rule.antecedent)
        consequent = " + ".join(rule.consequent)
        label = f"{antecedent} -> {consequent}"
        print(
            f"  {label:<76} %{rule.support * 100:>8.2f} "
            f"%{rule.confidence * 100:>11.2f} {rule.lift:>8.2f}"
        )


if __name__ == "__main__":
    main()
