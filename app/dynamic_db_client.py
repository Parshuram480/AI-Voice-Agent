import sqlite3
import asyncio
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Global cache for asyncpg pools
_pg_pools: Dict[tuple, "asyncpg.Pool"] = {}

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

    async def introspect_schema(self) -> Dict[str, List[str]]:
        """Introspects user database schema, returning table names mapped to their column names."""
        if self.db_type == "sqlite":
            return await self._introspect_sqlite()
        elif self.db_type == "postgresql":
            return await self._introspect_postgresql()
        elif self.db_type in ("mysql", "mariadb"):
            return await self._introspect_mysql()
        elif self.db_type == "sql server":
            return await self._introspect_sql_server()
        else:
            return {}

    async def _introspect_sqlite(self) -> Dict[str, List[str]]:
        db_path = self.db_name
        def _run():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            schema: Dict[str, List[str]] = {}
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [r[0] for r in cursor.fetchall()]
                for t in tables:
                    cursor.execute(f'PRAGMA table_info("{t}");')
                    cols = [c[1] for c in cursor.fetchall()]
                    schema[t] = cols
                return schema
            except Exception as e:
                logger.error(f"SQLite introspection error: {e}")
                return {}
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def _introspect_postgresql(self) -> Dict[str, List[str]]:
        import asyncpg
        try:
            conn = await asyncpg.connect(
                host=self.server_name or "localhost",
                port=int(self.port) if self.port else 5432,
                database=self.db_name,
                user=self.username,
                password=self.password,
                timeout=float(self.connection_timeout),
            )
            try:
                rows = await conn.fetch("""
                    SELECT table_name, column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name, ordinal_position
                """)
                schema: Dict[str, List[str]] = {}
                for r in rows:
                    t = r["table_name"]
                    c = r["column_name"]
                    if t not in schema:
                        schema[t] = []
                    schema[t].append(c)
                return schema
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"PostgreSQL introspection error: {e}")
            return {}

    async def _introspect_mysql(self) -> Dict[str, List[str]]:
        import pymysql
        def _run():
            conn = pymysql.connect(
                host=self.server_name or "localhost",
                port=int(self.port) if self.port else 3306,
                database=self.db_name,
                user=self.username,
                password=self.password,
                connect_timeout=int(self.connection_timeout)
            )
            schema: Dict[str, List[str]] = {}
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT table_name, column_name 
                        FROM information_schema.columns 
                        WHERE table_schema = %s 
                        ORDER BY table_name, ordinal_position
                    """, (self.db_name,))
                    rows = cursor.fetchall()
                    for t, c in rows:
                        if t not in schema:
                            schema[t] = []
                        schema[t].append(c)
                return schema
            except Exception as e:
                logger.error(f"MySQL introspection error: {e}")
                return {}
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def _introspect_sql_server(self) -> Dict[str, List[str]]:
        import pyodbc
        def _run():
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
            schema: Dict[str, List[str]] = {}
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT table_name, column_name 
                    FROM information_schema.columns 
                    ORDER BY table_name, ordinal_position
                """)
                for t, c in cursor.fetchall():
                    if t not in schema:
                        schema[t] = []
                    schema[t].append(c)
                return schema
            except Exception as e:
                logger.error(f"SQL Server introspection error: {e}")
                return {}
            finally:
                conn.close()
        return await asyncio.to_thread(_run)

    async def introspect_schema_full(self) -> Dict[str, Any]:
        """Introspects schema returning columns, types, primary keys, and foreign keys."""
        if self.db_type == "sqlite":
            return await self._full_sqlite()
        elif self.db_type == "postgresql":
            return await self._full_postgresql()
        elif self.db_type in ("mysql", "mariadb"):
            return await self._full_mysql()
        elif self.db_type == "sql server":
            return await self._full_sql_server()
        else:
            return {"tables": {}, "relationships": []}

    def _normalize_keys(self, row):
        return {k.lower(): v for k, v in row.items()}

    async def _full_sqlite(self) -> Dict[str, Any]:
        metadata = {"tables": {}, "relationships": []}
        tables = await self.execute_query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        for t_row in tables:
            t = self._normalize_keys(t_row)["name"]
            metadata["tables"][t] = {"columns": {}, "primary_key": None, "foreign_keys": []}
            cols = await self.execute_query(f'PRAGMA table_info("{t}");')
            for c_raw in cols:
                c = self._normalize_keys(c_raw)
                c_name = c["name"]
                c_type = c["type"].lower()
                metadata["tables"][t]["columns"][c_name] = {"type": c_type, "nullable": c["notnull"] == 0}
                if c["pk"] > 0 and metadata["tables"][t]["primary_key"] is None:
                    metadata["tables"][t]["primary_key"] = c_name
            fks = await self.execute_query(f'PRAGMA foreign_key_list("{t}");')
            for fk_raw in fks:
                fk = self._normalize_keys(fk_raw)
                f_col, t_table, t_col = fk["from"], fk["table"], fk["to"]
                metadata["relationships"].append({"from_table": t, "from_column": f_col, "to_table": t_table, "to_column": t_col})
                metadata["tables"][t]["foreign_keys"].append({"column": f_col, "references_table": t_table, "references_column": t_col})
        return metadata

    async def _full_postgresql(self) -> Dict[str, Any]:
        metadata = {"tables": {}, "relationships": []}
        tables = await self.execute_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        for t_row in tables:
            metadata["tables"][self._normalize_keys(t_row)["table_name"]] = {"columns": {}, "primary_key": None, "foreign_keys": []}
        columns = await self.execute_query("SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public'")
        for c_raw in columns:
            c = self._normalize_keys(c_raw)
            t_name = c["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["columns"][c["column_name"]] = {"type": c["data_type"], "nullable": c["is_nullable"] == "YES"}
        pks = await self.execute_query("""
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
        """)
        for pk_raw in pks:
            pk = self._normalize_keys(pk_raw)
            t_name = pk["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["primary_key"] = pk["column_name"]
        fks = await self.execute_query("""
            SELECT tc.table_name AS from_table, kcu.column_name AS from_column, ccu.table_name AS to_table, ccu.column_name AS to_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        """)
        for fk_raw in fks:
            fk = self._normalize_keys(fk_raw)
            f_table, t_table = fk["from_table"], fk["to_table"]
            if f_table in metadata["tables"] and t_table in metadata["tables"]:
                metadata["relationships"].append({"from_table": f_table, "from_column": fk["from_column"], "to_table": t_table, "to_column": fk["to_column"]})
                metadata["tables"][f_table]["foreign_keys"].append({"column": fk["from_column"], "references_table": t_table, "references_column": fk["to_column"]})
        return metadata

    async def _full_mysql(self) -> Dict[str, Any]:
        metadata = {"tables": {}, "relationships": []}
        db = self.db_name
        tables = await self.execute_query(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db}' AND table_type = 'BASE TABLE'")
        for t_row in tables:
            metadata["tables"][self._normalize_keys(t_row)["table_name"]] = {"columns": {}, "primary_key": None, "foreign_keys": []}
        columns = await self.execute_query(f"SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = '{db}'")
        for c_raw in columns:
            c = self._normalize_keys(c_raw)
            t_name = c["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["columns"][c["column_name"]] = {"type": c["data_type"], "nullable": c["is_nullable"] == "YES"}
        pks = await self.execute_query(f"""
            SELECT table_name, column_name 
            FROM information_schema.key_column_usage 
            WHERE table_schema = '{db}' AND constraint_name = 'PRIMARY'
        """)
        for pk_raw in pks:
            pk = self._normalize_keys(pk_raw)
            t_name = pk["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["primary_key"] = pk["column_name"]
        fks = await self.execute_query(f"""
            SELECT table_name, column_name, referenced_table_name, referenced_column_name 
            FROM information_schema.key_column_usage 
            WHERE table_schema = '{db}' AND referenced_table_name IS NOT NULL
        """)
        for fk_raw in fks:
            fk = self._normalize_keys(fk_raw)
            f_table, t_table = fk["table_name"], fk["referenced_table_name"]
            if f_table in metadata["tables"] and t_table in metadata["tables"]:
                metadata["relationships"].append({"from_table": f_table, "from_column": fk["column_name"], "to_table": t_table, "to_column": fk["referenced_column_name"]})
                metadata["tables"][f_table]["foreign_keys"].append({"column": fk["column_name"], "references_table": t_table, "references_column": fk["referenced_column_name"]})
        return metadata

    async def _full_sql_server(self) -> Dict[str, Any]:
        metadata = {"tables": {}, "relationships": []}
        
        tables = await self.execute_query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        for t_row in tables:
            metadata["tables"][self._normalize_keys(t_row)["table_name"]] = {"columns": {}, "primary_key": None, "foreign_keys": []}
            
        columns = await self.execute_query("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS")
        for c_raw in columns:
            c = self._normalize_keys(c_raw)
            t_name = c["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["columns"][c["column_name"]] = {"type": c["data_type"], "nullable": c["is_nullable"] == "YES"}
                
        pks = await self.execute_query("""
            SELECT tc.TABLE_NAME, kcu.COLUMN_NAME 
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        """)
        for pk_raw in pks:
            pk = self._normalize_keys(pk_raw)
            t_name = pk["table_name"]
            if t_name in metadata["tables"]:
                metadata["tables"][t_name]["primary_key"] = pk["column_name"]
                
        fks = await self.execute_query("""
            SELECT 
                tp.name 'from_table', cp.name 'from_column', 
                tr.name 'to_table', cr.name 'to_column'
            FROM sys.foreign_keys fk
            INNER JOIN sys.tables tp ON fk.parent_object_id = tp.object_id
            INNER JOIN sys.tables tr ON fk.referenced_object_id = tr.object_id
            INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            INNER JOIN sys.columns cp ON fkc.parent_column_id = cp.column_id AND fkc.parent_object_id = cp.object_id
            INNER JOIN sys.columns cr ON fkc.referenced_column_id = cr.column_id AND fkc.referenced_object_id = cr.object_id
        """)
        for fk_raw in fks:
            fk = self._normalize_keys(fk_raw)
            f_table, t_table = fk["from_table"], fk["to_table"]
            if f_table in metadata["tables"] and t_table in metadata["tables"]:
                metadata["relationships"].append({"from_table": f_table, "from_column": fk["from_column"], "to_table": t_table, "to_column": fk["to_column"]})
                metadata["tables"][f_table]["foreign_keys"].append({"column": fk["from_column"], "references_table": t_table, "references_column": fk["to_column"]})
                
        return metadata

    def _translate_placeholders(self, query: str, dialect: str) -> str:
        """Safely translates '?' placeholders to dialect-specific ones while ignoring literals."""
        if dialect not in ("postgresql", "mysql", "oracle"):
            return query
            
        in_single_quote = False
        in_double_quote = False
        escaped = False
        new_query = []
        param_index = 1
        
        for char in query:
            if escaped:
                new_query.append(char)
                escaped = False
                continue
            if char == '\\':
                escaped = True
                new_query.append(char)
                continue
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                
            if char == '?' and not in_single_quote and not in_double_quote:
                if dialect == "postgresql":
                    new_query.append(f"${param_index}")
                elif dialect == "mysql":
                    new_query.append("%s")
                elif dialect == "oracle":
                    new_query.append(f":{param_index}")
                param_index += 1
            else:
                new_query.append(char)
        return "".join(new_query)


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
        
        # Use safe state-machine parser to convert '?' placeholders to PostgreSQL '$1', '$2'
        new_query = self._translate_placeholders(query, "postgresql")

        # Convert ISO ("YYYY-MM-DD") or compact ("YYYYMMDD") date strings to datetime.date objects for asyncpg
        pg_params = []
        for p in params:
            if isinstance(p, str):
                p_clean = p.strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}$", p_clean):
                    try:
                        pg_params.append(datetime.date.fromisoformat(p_clean))
                        continue
                    except ValueError:
                        pass
                elif re.match(r"^\d{8}$", p_clean):
                    try:
                        y, m, d = int(p_clean[:4]), int(p_clean[4:6]), int(p_clean[6:8])
                        pg_params.append(datetime.date(y, m, d))
                        continue
                    except ValueError:
                        pass
                pg_params.append(p)
            else:
                pg_params.append(p)

        pool = await self.get_pg_pool()

        # Execute
        try:
            async with pool.acquire() as conn:
                try:
                    rows = await conn.fetch(new_query, *pg_params)
                except Exception as first_err:
                    logger.warning(f"PostgreSQL fetch with converted params failed ({first_err}), retrying with string params...")
                    str_params = [p.isoformat() if hasattr(p, "isoformat") else str(p) for p in params]
                    try:
                        rows = await conn.fetch(new_query, *str_params)
                    except Exception:
                        raise first_err
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"PostgreSQL error running query: {e}")
            raise e

    async def get_pg_pool(self) -> "asyncpg.Pool":
        import asyncpg
        pool_key = (
            self.server_name or "localhost",
            int(self.port) if self.port else 5432,
            self.db_name,
            self.username
        )
        
        if pool_key not in _pg_pools:
            _pg_pools[pool_key] = await asyncpg.create_pool(
                host=pool_key[0],
                port=pool_key[1],
                database=pool_key[2],
                user=pool_key[3],
                password=self.password,
                timeout=float(self.connection_timeout),
                min_size=1,
                max_size=10,
                command_timeout=float(self.connection_timeout),
            )
        return _pg_pools[pool_key]

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
                    # MySQL uses %s for positional placeholders. Safely translate.
                    mysql_query = self._translate_placeholders(query, "mysql")
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
                # Oracle uses :1, :2, etc. placeholders. Safely translate.
                oracle_query = self._translate_placeholders(query, "oracle")
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
