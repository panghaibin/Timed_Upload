from app import get_connection, app


def get_history(id_=None, username=None, status=None):
    with app.app_context():
        db = get_connection()
        if id_:
            query = "SELECT * FROM history WHERE id = ?"
            cur = db.cursor().execute(query, (id_,))
        elif username:
            query = "SELECT * FROM history WHERE username = ?"
            cur = db.cursor().execute(query, (username,))
        elif status:
            query = "SELECT * FROM history WHERE status = ?"
            cur = db.cursor().execute(query, (status,))
        else:
            return []
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
        return rv
