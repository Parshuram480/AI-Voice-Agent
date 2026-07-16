import sqlite3
import asyncio
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class DynamicDbClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_type = config.get("db_type", "").lower()
        self.db_name = config.get("db_name", "")
        self.server_name = config.get("server_name", "")
        self.port = config.get("port")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.connection_timeout = config.get("connection_timeout", 5)

    async def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Executes query on client database asynchronously."""
        if self.db_type == "sqlite":
            return await self._run_sqlite(query, params)
        elif self.db_type == "postgresql":
            return await self._run_postgresql(query, params)
        elif self.db_type in ("mysql", "mariadb"):
            return await self._run_mysql(query, params)
        elif self.db_type == "sql server":
            return await self._run_sql_server(query, params)
        elif self.db_type == "oracle":
            return await self._run_oracle(query, params)
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    async def _run_sqlite(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        # SQLite files are read from the project root directory
        db_path = self.db_name
        
        # SQLite compares date fields as strings, so convert any date/datetime parameter to string
        sqlite_params = tuple(p.isoformat() if hasattr(p, "isoformat") else p for p in params)
        
        def _run():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                cursor.execute(query, sqlite_params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"SQLite error running query: {e}")
                raise e
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def _run_postgresql(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        import asyncpg
        import datetime
        import re
        
        # Convert standard '?' placeholders to PostgreSQL '$1', '$2', ... placeholders
        count = 1
        new_query = ""
        for char in query:
            if char == "?":
                new_query += f"${count}"
                count += 1
            else:
                new_query += char

        # Convert ISO date strings ("YYYY-MM-DD") to datetime.date objects for asyncpg
        pg_params = []
        for p in params:
            if isinstance(p, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", p):
                try:
                    pg_params.append(datetime.date.fromisoformat(p))
                except ValueError:
                    pg_params.append(p)
            else:
                pg_params.append(p)

        # Connect and execute
        conn = await asyncpg.connect(
            host=self.server_name or "localhost",
            port=int(self.port) if self.port else 5432,
            database=self.db_name,
            user=self.username,
            password=self.password,
            timeout=float(self.connection_timeout),
        )
        try:
            rows = await conn.fetch(new_query, *pg_params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"PostgreSQL error running query: {e}")
            raise e
        finally:
            await conn.close()

    async def _run_mysql(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        try:
            import pymysql
        except ImportError:
            raise ImportError("MySQL driver 'pymysql' is required. Run 'pip install pymysql' to use MySQL.")
        
        def _run():
            conn = pymysql.connect(
                host=self.server_name or "localhost",
                port=int(self.port) if self.port else 3306,
                database=self.db_name,
                user=self.username,
                password=self.password,
                connect_timeout=int(self.connection_timeout),
                cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with conn.cursor() as cursor:
                    # MySQL uses %s for positional placeholders. Convert '?' to '%s'.
                    mysql_query = query.replace("?", "%s")
                    cursor.execute(mysql_query, params)
                    return list(cursor.fetchall())
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def _run_sql_server(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        try:
            import pyodbc
        except ImportError:
            raise ImportError("SQL Server driver 'pyodbc' is required. Run 'pip install pyodbc' to use SQL Server.")
        
        def _run():
            # Build connection string
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.server_name};"
                f"DATABASE={self.db_name};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"Connection Timeout={self.connection_timeout};"
            )
            if self.config.get("trust_server_certificate"):
                conn_str += "TrustServerCertificate=yes;"
            conn = pyodbc.connect(conn_str)
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def _run_oracle(self, query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        try:
            import cx_Oracle
        except ImportError:
            raise ImportError("Oracle driver 'cx_Oracle' is required. Run 'pip install cx_Oracle' to use Oracle.")
        
        def _run():
            dsn = cx_Oracle.makedsn(self.server_name, int(self.port or 1521), service_name=self.db_name)
            conn = cx_Oracle.connect(user=self.username, password=self.password, dsn=dsn)
            try:
                cursor = conn.cursor()
                # Oracle uses :1, :2, etc. placeholders. Convert '?' to :1, :2, ...
                count = 1
                oracle_query = ""
                for char in query:
                    if char == "?":
                        oracle_query += f":{count}"
                        count += 1
                    else:
                        oracle_query += char
                cursor.execute(oracle_query, params)
                columns = [col[0].lower() for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def test_connection(self) -> Tuple[bool, str]:
        """Tests the database connection. Returns (Success, Message)."""
        try:
            if self.db_type == "sqlite":
                # For SQLite, check if file can be opened
                def _test():
                    conn = sqlite3.connect(self.db_name)
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    conn.close()
                await asyncio.to_thread(_test)
                return True, "Successfully connected to SQLite database."
            elif self.db_type == "postgresql":
                import asyncpg
                # PostgreSQL standard test
                conn = await asyncpg.connect(
                    host=self.server_name or "localhost",
                    port=int(self.port) if self.port else 5432,
                    database=self.db_name,
                    user=self.username,
                    password=self.password,
                    timeout=float(self.connection_timeout),
                )
                await conn.close()
                return True, "Successfully connected to PostgreSQL database."
            elif self.db_type in ("mysql", "mariadb"):
                import pymysql
                def _test():
                    conn = pymysql.connect(
                        host=self.server_name or "localhost",
                        port=int(self.port) if self.port else 3306,
                        database=self.db_name,
                        user=self.username,
                        password=self.password,
                        connect_timeout=int(self.connection_timeout)
                    )
                    conn.close()
                await asyncio.to_thread(_test)
                return True, "Successfully connected to MySQL database."
            elif self.db_type == "sql server":
                import pyodbc
                def _test():
                    conn_str = (
                        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                        f"SERVER={self.server_name};"
                        f"DATABASE={self.db_name};"
                        f"UID={self.username};"
                        f"PWD={self.password};"
                        f"Connection Timeout={self.connection_timeout};"
                    )
                    if self.config.get("trust_server_certificate"):
                        conn_str += "TrustServerCertificate=yes;"
                    conn = pyodbc.connect(conn_str)
                    conn.close()
                await asyncio.to_thread(_test)
                return True, "Successfully connected to SQL Server database."
            elif self.db_type == "oracle":
                import cx_Oracle
                def _test():
                    dsn = cx_Oracle.makedsn(self.server_name, int(self.port or 1521), service_name=self.db_name)
                    conn = cx_Oracle.connect(user=self.username, password=self.password, dsn=dsn)
                    conn.close()
                await asyncio.to_thread(_test)
                return True, "Successfully connected to Oracle database."
            else:
                return False, f"Unsupported database type: {self.db_type}"
        except Exception as e:
            logger.error("Error connecting to database: %s", str(e))
            return False, str(e)
