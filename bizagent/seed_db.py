from datetime import date
from app.db_postgres import PostgresDB
from app.mock_data import seed as seed_mock, MockDB

def main():
    print("Генерация данных в PostgreSQL...")
    pg_db = PostgresDB()
    
    # Чтобы использовать наш детерминированный генератор данных из mock_data.py
    # Мы сначала генерируем их в памяти, а потом переносим в PostgreSQL
    temp_mem_db = MockDB()
    seed_mock(temp_mem_db, date(2026, 10, 11))

    # Наполняем PostgreSQL из сгенерированных объектов
    # 1. Компании
    with pg_db._get_conn() as conn:
        with conn.cursor() as cur:
            for c in temp_mem_db._companies.values():
                cur.execute(
                    "INSERT INTO companies (id, name, unp, tax_regime) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                    (c.id, c.name, c.unp, c.tax_regime)
                )
            # Пользователи демо
            users = [
                (1, 1, 'owner@uyut.by', 'owner', 'Владелец (Уютный дом)'),
                (2, 1, 'manager@uyut.by', 'manager', 'Менеджер (Уютный дом)'),
                (3, 1, 'accountant@uyut.by', 'accountant', 'Бухгалтер (Уютный дом)'),
                (4, 2, 'owner@flora.by', 'owner', 'Владелец (Флора)'),
            ]
            for u in users:
                cur.execute(
                    "INSERT INTO users (id, company_id, email, role, name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                    u
                )
            # Товары
            for p in temp_mem_db._products:
                cur.execute(
                    """INSERT INTO products (id, company_id, sku, name, category, price, cost, stock)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;""",
                    (p.id, p.company_id, p.sku, p.name, p.category, float(p.price), float(p.cost), p.stock)
                )
            # Клиенты
            for cl in temp_mem_db._clients:
                cur.execute(
                    """INSERT INTO clients (id, company_id, name, phone, email, unp, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;""",
                    (cl.id, cl.company_id, cl.name, cl.phone, cl.email, cl.unp, cl.notes)
                )
            # Заказы
            for o in temp_mem_db._orders:
                cur.execute(
                    "INSERT INTO orders (id, company_id, client_id, status, created_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                    (o.id, o.company_id, o.client_id, o.status, o.created)
                )
                for item in o.items:
                    cur.execute(
                        "INSERT INTO order_items (order_id, product_id, qty, price, unit_cost) VALUES (%s, %s, %s, %s, %s);",
                        (o.id, item.product_id, item.qty, float(item.price), float(item.unit_cost))
                    )
            # Расходы
            for ex in temp_mem_db._expenses:
                cur.execute(
                    "INSERT INTO expenses (id, company_id, category, amount, day, comment) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                    (ex.id, ex.company_id, ex.category, float(ex.amount), ex.day, ex.comment)
                )
            # Строки вставлялись с явными id, а счётчики SERIAL при этом не двигаются. Без этого первая же вставка
            # из приложения (создать клиента, заказ, расход) получит id=1 и упадёт на дубликате ключа.
            for table in ("companies", "users", "products", "clients", "orders", "expenses"):
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
        conn.commit()
    print("Данные успешно перенесены в PostgreSQL!")

if __name__ == "__main__":
    main()