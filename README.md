# Warehouse Slotting Optimizer

Koli bazlı depo raf yerleşimi için FastAPI ve PostgreSQL tabanlı backend projesi.
Bu aşamada veritabanı şeması, migration sistemi ve sağlık kontrolleri hazırlanmıştır.
Optimizasyon algoritmaları ve CRUD endpoint'leri henüz eklenmemiştir.

## Kullanılan teknolojiler

- Python
- FastAPI ve Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.x ve Psycopg 3
- Alembic
- Docker Compose
- Pytest

## Veritabanı tabloları

- `products`: Ürün ve SKU bilgileri.
- `carton_types`: Koli ölçüleri ve ağırlık kapasitesi.
- `product_packaging`: Bir ürünün koli tipi ve koli içi adet tanımı.
- `warehouse_locations`: Koridor, raf, seviye ve slot bilgileri.
- `cartons`: Depodaki fiziksel koliler ve güncel miktarları.
- `orders`: Sipariş üst bilgileri.
- `order_lines`: Sipariş edilen ürün ve miktarlar.
- `carton_allocations`: Sipariş için fiziksel kolilerden ayrılan miktarlar.
- `pick_operations`: Gerçekleşen toplama hareketleri.
- `carton_location_history`: Kolilerin konum değişiklikleri.
- `optimization_runs`: Optimizasyon çalıştırma kayıtları.
- `optimization_assignments`: Optimizasyonun önerdiği koli-konum atamaları.

## Proje yapısı

```text
app/
├── main.py
├── api/routes/health.py
├── core/config.py
├── db/
│   ├── base.py
│   └── session.py
└── models/
    ├── catalog.py
    ├── inventory.py
    ├── orders.py
    └── optimization.py
alembic/
tests/
docker-compose.yml
requirements.txt
```

## Kurulum

Bağımlılıkları yükleyin:

```bash
python -m pip install -r requirements.txt
```

Örnek ortam dosyasını kopyalayın:

```cmd
copy .env.example .env
```

`.env` içindeki kullanıcı ve parola değerlerini düzenleyin. Gerçek `.env` dosyası
Git'e eklenmez. Docker PostgreSQL bilgisayara `5433` portundan açılır; container
içinde standart `5432` portunu kullanır.

## Çalıştırma

PostgreSQL container'ını başlatın:

```bash
docker compose up -d postgres
docker compose ps
```

Veritabanı tablolarını oluşturun:

```bash
python -m alembic upgrade head
```

FastAPI uygulamasını başlatın:

```bash
python -m uvicorn app.main:app --reload
```

Kullanılabilir adresler:

- Swagger UI: `http://127.0.0.1:8000/docs`
- Uygulama sağlığı: `http://127.0.0.1:8000/health`
- Veritabanı sağlığı: `http://127.0.0.1:8000/health/db`

## Testler

```bash
python -m pytest -v
```

Veritabanı bağlantı testi gerçek PostgreSQL'e bağlandığı için test sırasında Docker
PostgreSQL container'ının çalışıyor olması gerekir.

## Yeni migration oluşturma

Model değişikliklerinden sonra:

```bash
python -m alembic revision --autogenerate -m "migration açıklaması"
python -m alembic upgrade head
```

Veritabanı şeması uygulama başlangıcında otomatik oluşturulmaz.
Şema değişikliklerinin tek kaynağı Alembic migration dosyalarıdır.
