import os
import pymysql

def dump_db():
    host = os.environ.get('MYSQL_HOST', '127.0.0.1')
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    port = int(os.environ.get('MYSQL_PORT', '3306'))
    db = os.environ.get('MYSQL_DB', 'badminton_tournament')

    conn = pymysql.connect(
        host=host,
        user=user,
        password=password,
        port=port,
        database=db,
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username, email FROM users")
            users = cursor.fetchall()
            print("=== Users ===")
            for u in users:
                print(u)
                
            cursor.execute("SELECT id, name, creator, fixture_type, num_sets FROM tournaments")
            tourneys = cursor.fetchall()
            print("=== Tournaments ===")
            for t in tourneys:
                print(t)
    finally:
        conn.close()

if __name__ == '__main__':
    dump_db()
