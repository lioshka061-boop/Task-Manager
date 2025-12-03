import aiosqlite

class TaskRepository:
    def __init__(self, db_path="tasks.db"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
            """)
            await db.commit()

    async def add(self, user_id: int, name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tasks (user_id, name) VALUES (?, ?)",
                (user_id, name)
            )
            await db.commit()

    async def list(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, name, status FROM tasks WHERE user_id=? ORDER BY id",
                (user_id,)
            )
            rows = await cursor.fetchall()

        if not rows:
            return "Список порожній."

        out = []
        for i, (tid, name, status) in enumerate(rows, 1):
            mark = "✅" if status == "done" else "❌"
            out.append(f"{i}. {name} {mark}")
        return "\n".join(out)

    async def mark_done(self, user_id: int, index: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM tasks WHERE user_id=? ORDER BY id",
                (user_id,)
            )
            rows = await cursor.fetchall()

            if 0 <= index < len(rows):
                task_id = rows[index][0]
                await db.execute(
                    "UPDATE tasks SET status='done' WHERE id=?",
                    (task_id,)
                )
                await db.commit()
                return True
            return False
