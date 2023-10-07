import os
from ast import literal_eval
from typing import Optional, Iterable

import discord
from discord.ext import commands
import asqlite

from .utils import helper_functions as hf

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

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
            raise ValueError("table_name and primary_key need to be specified to use this command.")
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


def test():
    print('hello')
    return 5


class Connect(SQLCommands):
    """
    Instantiate a conversion to and from sqlite3 database and python dictionary.
    primary_key needs to be specified manually if table_name is not one of the recognized tables.

    Most of the credit for this module goes to: https://github.com/sabrysm/asqlitedict
    """

    def __init__(self, database_name: str, table_name: str = None, primary_key: str = None):
        super().__init__(database_name, table_name, primary_key)

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
            raise ValueError("table_name and primary_key need to be specified to use this command.")
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
            raise ValueError("table_name and primary_key need to be specified to use this command.")
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
            raise ValueError("table_name and primary_key need to be specified to use this command.")
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
                    query += f" DESC"
                else:
                    query += f""
                if limit is not None:
                    query += f" LIMIT ?"
                    parameters.append(limit)
                if offset is not None and limit is not None:
                    query += f" OFFSET ?"
                    parameters.append(offset)
                elif offset is not None and limit is None:
                    raise Exception("You can't use kwarg 'offset' without kwarg 'limit'")
                parameters = str(tuple(parameters))
                parameters = eval(parameters)
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
                        i = eval(i)
                        my_list.append(eval(i))
                    elif i.isascii():
                        i = i[1:-1]
                        my_list.append(i)
                    else:
                        my_list.append(i)

                return my_list


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


async def setup(bot):
    pass
