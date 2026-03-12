from db import connect, run_migrations

if __name__ == "__main__":
    conn = connect()
    try:
        run_migrations(conn)
        print("CRM schema initialized")
    finally:
        conn.close()
