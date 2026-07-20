"""Sentetik depo verisini kontrollü biçimde üreten terminal komutu."""

import argparse
from dataclasses import asdict
import json
from time import perf_counter

from app.data_generation.cleanup import delete_synthetic_data
from app.data_generation.config import PROFILES, get_profile
from app.data_generation.runner import generate_synthetic_data
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Warehouse Slotting Optimizer sentetik veri üreticisi"
    )
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILES),
        default="smoke",
        help="Üretilecek veri büyüklüğü (varsayılan: smoke)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Tekrarlanabilir rastgelelik değeri (varsayılan: 42)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Bu seçenek verilmezse yalnızca üretim planı gösterilir",
    )
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help="Large profilin yanlışlıkla çalıştırılmasını engelleyen ek onay",
    )
    parser.add_argument(
        "--replace-synthetic",
        action="store_true",
        help="Yalnizca SYN-* kayitlarini temizleyip yeniden uretir",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = get_profile(args.profile)
    plan = {
        "profile": profile.name,
        "seed": args.seed,
        "products": profile.product_count,
        "locations": profile.location_count,
        "cartons": profile.carton_count,
        "historical_orders": profile.historical_order_count,
        "pending_orders": profile.pending_order_count,
        "replace_synthetic": args.replace_synthetic,
    }
    print("Üretim planı:")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if not args.execute:
        print("Veri yazılmadı. Çalıştırmak için --execute ekleyin.")
        return
    if profile.name == "large" and not args.allow_large:
        raise SystemExit("Large profil için --allow-large seçeneği gereklidir.")

    started_at = perf_counter()
    cleanup_result = None
    with SessionLocal() as session:
        if args.replace_synthetic:
            cleanup_result = delete_synthetic_data(session)
        summary = generate_synthetic_data(
            session=session,
            profile_name=profile.name,
            seed=args.seed,
        )

    elapsed_seconds = perf_counter() - started_at
    if cleanup_result is not None:
        print("Temizlenen sentetik kayitlar:")
        print(json.dumps(asdict(cleanup_result), ensure_ascii=False, indent=2))
    print("Üretim tamamlandı:")
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    print(f"Süre: {elapsed_seconds:.2f} saniye")


if __name__ == "__main__":
    main()
