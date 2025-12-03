import json
from aiosqlite import connect


DB_PATH = "tasks.db"


async def save_user_state(user_id: int, state: dict):
    async with connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS user_states (user_id INTEGER PRIMARY KEY, state TEXT)"
        )
        state_json = json.dumps(state)
        await db.execute(
            "INSERT INTO user_states (user_id, state) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state",
            (user_id, state_json)
        )
        await db.commit()


async def load_user_state(user_id: int):
    async with connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS user_states (user_id INTEGER PRIMARY KEY, state TEXT)"
        )
        cursor = await db.execute(
            "SELECT state FROM user_states WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

        if row and row[0]:
            try:
                return json.loads(row[0])
            except:
                return {}
        return {}
