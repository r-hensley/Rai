import os
import re
import sqlite3
import asyncio
from ast import literal_eval
from datetime import datetime, timezone
from typing import Optional, Iterable

import asqlite


dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATABASE_PATH = f"{dir_path}/database.db"
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRY_DELAYS = (0.25, 0.5, 1.0, 2.0)

table_primary_keys = {
    'users': 'user_id',
    'guilds': 'guild_id',
    'channels': 'channel_id',
    'clubs': 'club_id',
    'club_members': 'id',
    'messages': 'message_id'
}


class SQLCommands(object):
    def __init__(self, database_name: str, table_name: str = None, primary_key: str = None):
        self._database_name = f"{dir_path}/{database_name}"
        self._table_name = table_name

        if table_name:
            if primary_key:
                self._primary_key = primary_key
            else:
                if table_name in table_primary_keys:
                    self._primary_key = table_primary_keys[table_name]

    async def delete(self, row_id):
        """
        deletes a certain row from the table.
        :param row_id: The id of the row.
        :type row_id: int
        :param primary_key: The name of the primary key column (usually "ID")
        :type primary_key: str
        """
        if not self._table_name or not self._primary_key:
            raise ValueError(
                "table_name and primary_key need to be specified to use this command.")
        async with asqlite.connect(self._database_name) as db:
            async with db.cursor() as cursor:
                await cursor.execute(
                    f"DELETE FROM {self._table_name} WHERE {self._primary_key} = ?", (row_id,))
            await db.commit()

    async def execute(self, query, parameters: Optional[Iterable] = None):
        """
        Execute SQL query.
        """
        if parameters and type(parameters) is not tuple:
            parameters = (parameters,)

        async with asqlite.connect(self._database_name) as db:
            async with db.cursor() as cursor:
                if parameters:
                    cur = await cursor.execute(query, parameters)
                else:
                    cur = await cursor.execute(query)
                res = await cur.fetchall()
            await db.commit()
            return res


class Connect(SQLCommands):
    """
    Instantiate a conversion to and from sqlite3 database and python dictionary.
    primary_key needs to be specified manually if table_name is not one of the recognized tables.

    Most of the credit for this module goes to: https://github.com/sabrysm/asqlitedict
    """

    async def to_dict(self, my_id, *column_names: str) -> dict:
        """
        Convert a sqlite3 table into a python dictionary.
        :param my_id: The id of the row.
        :type my_id: int
        :param column_names: The column name.
        :type column_names: str
        :return: The dictionary.
        :rtype: dict
        """
        if not self._table_name or not self._primary_key:
            raise ValueError(
                "table_name and primary_key need to be specified to use this command.")
        async with asqlite.connect(self._database_name) as db:
            async with db.cursor() as cursor:
                data = {}
                columns = ", ".join(column for column in column_names)

                def check_type(value, value_type):
                    # to check if value is of certain type
                    try:
                        val = str(value)
                        return isinstance(literal_eval(val), value_type)
                    except SyntaxError:
                        return False
                    except ValueError:
                        return False

                if columns == "*":
                    getID = await cursor.execute(
                        f"SELECT {columns} FROM {self._table_name} WHERE {self._primary_key} = ?", (my_id,))
                    fieldnames = [f[0] for f in getID.description]
                    values = await getID.fetchone()
                    values = list(values)
                    for v in range(len(values)):
                        if not (isinstance(values[v], int) or isinstance(values[v], float)):
                            isList = check_type(values[v], list)
                            isTuple = check_type(values[v], tuple)
                            isDict = check_type(values[v], dict)
                            if isList or isTuple or isDict:
                                values[v] = literal_eval(values[v])
                    for i in range(len(fieldnames)):
                        data[fieldnames[i]] = values[i]
                    return data
                else:
                    getID = await cursor.execute(
                        f"SELECT {columns} FROM {self._table_name} WHERE {self._primary_key} = ?", (my_id,))
                    values = await getID.fetchone()
                    values = list(values)
                    for v in range(len(values)):
                        if not (isinstance(values[v], int) or isinstance(values[v], float)):
                            isList = check_type(values[v], list)
                            isTuple = check_type(values[v], tuple)
                            isDict = check_type(values[v], dict)
                            if isList or isTuple or isDict:
                                values[v] = literal_eval(values[v])
                    for i in range(len(column_names)):
                        data[column_names[i]] = values[i]
                    return data

    #  To push data to db

    async def to_sql(self, my_id, dictionary: dict):
        """
        Convert a python dictionary into a sqlite3 table.
        :param my_id: The id of the row.
        :type my_id: int
        :param dictionary: The dictionary object.
        :type dictionary: dict
        :return: The SQLite3 Table.
        :rtype: sqlite
        """
        if not self._table_name or not self._primary_key:
            raise ValueError(
                "table_name and primary_key need to be specified to use this command.")
        async with asqlite.connect(self._database_name) as db:
            async with db.cursor() as cursor:
                getUser = await cursor. \
                    execute(f"SELECT {self._primary_key} FROM {self._table_name} WHERE {self._primary_key} = ?",
                            (my_id,))
                isUserExists = await getUser.fetchone()
                if isUserExists:
                    for key, val in dictionary.items():
                        if isinstance(val, list) or isinstance(val, dict) or isinstance(val, tuple):
                            dictionary[key] = str(val)
                    await cursor.execute(f"UPDATE {self._table_name} SET " + ', '.join(
                        "{}=?".format(k) for k in dictionary.keys()) + f" WHERE {self._primary_key}=?",
                        list(dictionary.values()) + [my_id])
                else:
                    await cursor.execute(f"INSERT INTO {self._table_name} ({self._primary_key}) VALUES ( ? )", (my_id,))
                    for key, val in dictionary.items():
                        if isinstance(val, list) or isinstance(val, dict) or isinstance(val, tuple):
                            dictionary[key] = str(val)
                    await cursor.execute(f"UPDATE {self._table_name} SET " + ', '.join(
                        "{}=?".format(k) for k in dictionary.keys()) + f" WHERE {self._primary_key}=?",
                        list(dictionary.values()) + [my_id])

            await db.commit()

    async def select(self, column_name: str, limit: int = None, order_by: str = None,
                     ascending: bool = True, equal=None, like: str = None, between: tuple = None,
                     distinct: bool = False, offset: int = None) -> list:
        """
        Select a column from the table.

        :param column_name: The column name.
        :type column_name: str
        :param limit:
        :rtype: int
        :param order_by:
        :rtype: str
        :param ascending:
        :rtype: bool
        :param equal:
        :param like:
        :rtype: str
        :param distinct:
        :rtype: bool
        :param between:
        :rtype: tuple
        :param offset:
        :rtype: int
        :return: The list.
        :rtype: list
        """
        if not self._table_name or not self._primary_key:
            raise ValueError(
                "table_name and primary_key need to be specified to use this command.")
        async with asqlite.connect(self._database_name) as db:
            async with db.cursor() as cursor:

                query = f"SELECT {column_name} FROM {self._table_name}"
                parameters = []
                condition = False
                if distinct is True:
                    query = f"SELECT DISTINCT {column_name} FROM {self._table_name}"
                if equal is not None and condition is False:
                    condition = True
                    query += f" WHERE {column_name} = ?"
                    parameters.append(equal)
                elif equal is not None and condition is True:
                    query += f" AND {column_name} = ?"
                    parameters.append(equal)
                if like is not None and condition is False:
                    condition = True
                    query += f" WHERE {column_name} LIKE ?"
                    parameters.append("%" + like + "%")
                elif like is not None and condition is True:
                    query += f" AND {column_name} LIKE ?"
                    parameters.append("%" + like + "%")
                if between is not None and condition is False:
                    condition = True
                    query += f" WHERE {column_name} BETWEEN ? AND ?"
                    parameters.append(range(between[0], between[1]).start)
                    parameters.append(range(between[0], between[1]).stop)

                elif between is not None and condition is True:
                    query += f" AND {column_name} BETWEEN ? AND ?"
                    parameters.append(range(between[0], between[1]).start)
                    parameters.append(range(between[0], between[1]).stop)
                if order_by is not None:
                    query += f" ORDER BY {order_by}"
                if ascending is False:
                    query += " DESC"
                else:
                    query += ""
                if limit is not None:
                    query += " LIMIT ?"
                    parameters.append(limit)
                if offset is not None and limit is not None:
                    query += " OFFSET ?"
                    parameters.append(offset)
                elif offset is not None and limit is None:
                    raise Exception(
                        "You can't use kwarg 'offset' without kwarg 'limit'")
                parameters = str(tuple(parameters))
                parameters = literal_eval(parameters)
                # print(f"query ==> await cursor.execute(\"{query}\", {parameters})")
                # print(parameters)
                getValues = await cursor.execute(query, parameters)
                values = await getValues.fetchall()
                my_list = []

                def check_type(value, value_type):
                    # to check if value is of certain type
                    try:
                        val = str(value)
                        return isinstance(literal_eval(val), value_type)
                    except SyntaxError:
                        return False
                    except ValueError:
                        return False

                for i in values:
                    i = str(i)
                    i = i[1:-2]  # Remove round brackets in i
                    # Check the type of i
                    if i.isnumeric():
                        my_list.append(int(i))
                    elif isinstance(i, float):
                        my_list.append(float(i))
                    elif i == 'None' or i is None:
                        my_list.append(i)
                    elif check_type(i, list) or check_type(i, dict) or check_type(i, tuple):
                        i = literal_eval(i)
                        my_list.append(literal_eval(i))
                    elif i.isascii():
                        i = i[1:-1]
                        my_list.append(i)
                    else:
                        my_list.append(i)

                return my_list


def _normalize_role_ids(role_payload, role_map: dict) -> list[int]:
    if isinstance(role_payload, str):
        tokens = [token for token in role_payload.split(',') if token]
    elif isinstance(role_payload, (list, tuple)):
        tokens = [str(token) for token in role_payload if token is not None]
    else:
        return []

    role_ids = []
    for token in tokens:
        role_id = role_map.get(token, token)
        try:
            role_ids.append(int(role_id))
        except (TypeError, ValueError):
            continue

    # Preserve order while dropping duplicates.
    return list(dict.fromkeys(role_ids))


def _normalize_left_at(left_at) -> str:
    if isinstance(left_at, str) and re.fullmatch(r"\d{8}", left_at):
        return left_at
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _is_locked_database_error(error: Exception) -> bool:
    return isinstance(error, sqlite3.OperationalError) and "database is locked" in str(error).lower()


async def connect_to_database():
    db = await asqlite.connect(DATABASE_PATH)
    await db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return db


async def _run_readd_roles_write(query: str, parameters: Iterable, *, return_rowcount: bool = False) -> Optional[int]:
    for delay in (*SQLITE_WRITE_RETRY_DELAYS, None):
        try:
            async with await connect_to_database() as db:
                async with db.cursor() as cursor:
                    await cursor.execute(query, parameters)
                    rowcount = cursor.get_cursor().rowcount
                await db.commit()
            return rowcount if return_rowcount else None
        except sqlite3.OperationalError as error:
            if delay is None or not _is_locked_database_error(error):
                raise
            await asyncio.sleep(delay)

    return 0 if return_rowcount else None


async def fetch_readd_role_entry(guild_id: int, user_id: int) -> Optional[tuple[str, list[int]]]:
    async with await connect_to_database() as db:
        async with db.cursor() as cursor:
            row = await cursor.execute(
                "SELECT left_at, role_ids FROM readd_roles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            result = await row.fetchone()

    if not result:
        return None

    left_at, role_ids = result
    normalized_role_ids = _normalize_role_ids(role_ids, {})
    return left_at, normalized_role_ids


async def store_readd_role_entry(guild_id: int, user_id: int, left_at: str, role_ids: list[int]) -> None:
    role_ids_text = ",".join(str(role_id) for role_id in role_ids)
    await _run_readd_roles_write(
        """
        INSERT OR REPLACE INTO readd_roles (guild_id, user_id, left_at, role_ids)
        VALUES (?, ?, ?, ?)
        """,
        (guild_id, user_id, _normalize_left_at(left_at), role_ids_text),
    )


async def delete_readd_role_entry(guild_id: int, user_id: int) -> None:
    await _run_readd_roles_write(
        "DELETE FROM readd_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )


async def purge_old_readd_role_entries(cutoff: str) -> int:
    deleted = await _run_readd_roles_write(
        "DELETE FROM readd_roles WHERE left_at < ?",
        (cutoff,),
        return_rowcount=True,
    )
    return deleted or 0


async def create_database_tables() -> None:
    """
    Setup the database when the bot starts
    :return: None
    """
    users = Connect("database.db", "users", "user_id")
    await users.execute("CREATE TABLE IF NOT EXISTS users "
                        "(rai_id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE)")

    guilds = Connect("database.db", "guilds", "guild_id")
    await guilds.execute("CREATE TABLE IF NOT EXISTS guilds "
                         "(rai_id INTEGER PRIMARY KEY, guild_id INTEGER UNIQUE)")

    channels = Connect("database.db", "channels", "channel_id")
    await channels.execute("CREATE TABLE IF NOT EXISTS channels "
                           "(rai_id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE)")

    clubs = Connect("database.db", "clubs", "club_id")
    await clubs.execute("CREATE TABLE IF NOT EXISTS clubs "
                        "(club_id INTEGER PRIMARY KEY, "
                        "name TEXT, "
                        "guild_id INTEGER,"
                        "created_at TIMESTAMP,"
                        "owner_id INTEGER,"
                        "UNIQUE (name, guild_id),"
                        "FOREIGN KEY (guild_id) REFERENCES guilds (guild_id),"
                        "FOREIGN KEY (owner_id) REFERENCES users (user_id))")

    club_members = Connect("database.db", "club_members", "id")
    await club_members.execute("CREATE TABLE IF NOT EXISTS club_members "
                               "(id INTEGER PRIMARY KEY, "
                               "club_id INTEGER,"
                               "member_id INTEGER,"
                               "FOREIGN KEY (club_id) REFERENCES clubs (club_id),"
                               "FOREIGN KEY (member_id) REFERENCES users (user_id),"
                               "UNIQUE (club_id, member_id))")

    messages = Connect("database.db", "messages", "message_id")
    await messages.execute("CREATE TABLE IF NOT EXISTS messages "
                           "(message_id INTEGER PRIMARY KEY, "
                           "user_id INTEGER,"
                           "guild_id INTEGER,"
                           "channel_id INTEGER,"
                           "language TEXT,"
                           "FOREIGN KEY (guild_id) REFERENCES guilds (rai_id),"
                           "FOREIGN KEY (user_id) REFERENCES users (rai_id),"
                           "FOREIGN KEY (channel_id) REFERENCES channels (rai_id))")

    # for slash command "/linkusers"
    messages = Connect("database.db", "", "")
    await messages.execute("CREATE TABLE IF NOT EXISTS linkedusers "
                           "(id INTEGER PRIMARY KEY, "
                           "id_1 INTEGER, "
                           "id_2 INTEGER, "
                           "guild_id INTEGER, "
                           "FOREIGN KEY (id_1) REFERENCES users (user_id) ON DELETE RESTRICT,"
                           "FOREIGN KEY (id_2) REFERENCES users (user_id) ON DELETE RESTRICT,"
                           "FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE RESTRICT)")

    readd_roles = Connect("database.db", "", "")
    await readd_roles.execute("CREATE TABLE IF NOT EXISTS readd_roles "
                              "(guild_id INTEGER, "
                              "user_id INTEGER, "
                              "left_at TEXT, "
                              "role_ids TEXT, "
                              "PRIMARY KEY (guild_id, user_id))")
    await readd_roles.execute("CREATE INDEX IF NOT EXISTS idx_readd_roles_left_at "
                              "ON readd_roles (left_at)")

    async with await connect_to_database() as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.commit()


async def setup(bot):
    # this file is not formatted like a typical cog but this is necessary to allow reloading of this file
    pass
