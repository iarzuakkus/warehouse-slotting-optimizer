# Warehouse Slotting Optimizer

Koli bazlı depo raf yerleşimi için FastAPI ve PostgreSQL tabanlı backend projesidir.
Ürünler, koli tipleri, fiziksel koliler, raflar, siparişler, ayırmalar, toplama
hareketleri ve optimizasyon kayıtları yönetilir.

Bu aşamada ABC analizi, FP-Growth, genetik algoritma, en kısa rota ve sentetik veri
üretimi uygulanmamıştır. Yalnızca bu algoritmaların ileride kullanacağı sağlam veri
ve API altyapısı hazırlanmıştır.

## Teknolojiler

- Python
- FastAPI ve Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.x ORM
- Alembic
- Psycopg 3
- Pydantic Settings
- Docker Compose
- Pytest

## Mimari

İstekler aşağıdaki katmanlardan geçer:

```text
HTTP / Swagger
    -> Route
    -> Pydantic Schema
    -> Service (iş kuralları ve transaction)
    -> Repository (SQLAlchemy sorguları)
    -> Model
    -> PostgreSQL
```

Veritabanı şeması uygulama başlangıcında otomatik oluşturulmaz.
`Base.metadata.create_all()` kullanılmaz; şemanın tek kaynağı Alembic
migration dosyalarıdır.

## Veritabanı tabloları

- `products`: Ürün ve SKU bilgileri
- `carton_types`: Koli ölçüleri ve ağırlık kapasitesi
- `product_packaging`: Ürün, koli tipi ve koli içi adet tanımı
- `warehouse_locations`: Koridor, raf, seviye ve slot bilgileri
- `cartons`: Fiziksel koliler, stok ve rezerve miktarlar
- `orders`: Sipariş üst bilgileri
- `order_lines`: Sipariş ürünleri ve miktarları
- `carton_allocations`: Sipariş satırlarına ayrılan koli miktarları
- `pick_operations`: Gerçekleşen toplama hareketleri
- `carton_location_history`: Kolilerin raf hareket geçmişi
- `optimization_runs`: Optimizasyon çalışma takip kayıtları
- `optimization_assignments`: Önerilen koli–raf yerleşimleri

## Proje yapısı

```text
warehouse-slotting-optimizer/
├── app/
│   ├── main.py
│   ├── api/routes/          # FastAPI endpoint'leri
│   ├── core/config.py       # Ortam ayarları
│   ├── db/                  # Base, engine ve session
│   ├── models/              # SQLAlchemy modelleri
│   ├── schemas/             # Pydantic istek/cevap şemaları
│   ├── repositories/        # Veritabanı sorguları
│   ├── services/            # İş kuralları ve transaction yönetimi
│   └── algorithms/          # İleride eklenecek optimizasyon algoritmaları
├── alembic/
│   └── versions/
├── tests/
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Kurulum

Bağımlılıkları yükleyin:

```bash
python -m pip install -r requirements.txt
```

Windows CMD ile örnek ortam dosyasını kopyalayın:

```cmd
copy .env.example .env
```

PowerShell kullanıyorsanız:

```powershell
Copy-Item .env.example .env
```

`.env` içindeki kullanıcı ve parola değerlerini değiştirin. Gerçek `.env` dosyası
Git'e eklenmez. Docker PostgreSQL host üzerinde `5433`, container içinde `5432`
portunu kullanır.

## Çalıştırma

Docker Desktop'ın çalıştığından emin olduktan sonra:

```bash
docker compose up -d
docker compose ps
alembic upgrade head
uvicorn app.main:app --reload
```

Komutların aktif Python yorumlayıcısıyla çalışmasını garanti etmek için şu biçimler
de kullanılabilir:

```bash
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Adresler:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Uygulama sağlığı: `http://127.0.0.1:8000/health`
- PostgreSQL sağlığı: `http://127.0.0.1:8000/health/db`

Ana endpoint grupları:

- `/products`
- `/carton-types`
- `/product-packaging`
- `/warehouse-locations`
- `/cartons`
- `/orders`
- `/orders/{order_id}/lines`
- `/orders/{order_id}/lines/{line_id}/allocations`
- `/orders/{order_id}/lines/{line_id}/allocations/{allocation_id}/picks`
- `/cartons/{carton_id}/movements`
- `/optimization-runs`
- `/optimization-runs/{run_id}/assignments`

## Testler

Testler gerçek PostgreSQL bağlantısı kullandığı için Docker PostgreSQL container'ı
çalışıyor olmalıdır:

```bash
python -m pytest -v
```

## Migration yönetimi

Mevcut migration seviyesini ve model uyumluluğunu kontrol edin:

```bash
python -m alembic current
python -m alembic check
```

Model değişikliklerinden sonra yeni migration oluşturun ve uygulayın:

```bash
alembic revision --autogenerate -m "migration açıklaması"
alembic upgrade head
```

İlk migration dosyası `create_initial_warehouse_schema` adını taşır ve tüm tabloları,
foreign key'leri, constraint'leri ve indeksleri oluşturur.
