from dataclasses import dataclass
import getpass

import mysql.connector


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    user: str = "root"
    database: str = "gerenciador"


def connect_with_prompt(config: DatabaseConfig):
    password = getpass.getpass("Senha do banco de dados: ")
    return mysql.connector.connect(
        host=config.host,
        user=config.user,
        password=password,
        database=config.database,
    )


def fetch_credentials(table: str, *, row_id: int = 1, config: DatabaseConfig | None = None) -> tuple[str, str]:
    database = connect_with_prompt(config or DatabaseConfig())
    try:
        cursor = database.cursor()
        cursor.execute(f"SELECT usuario, senha FROM {table} WHERE id = %s", (row_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Credenciais nao encontradas em {table} para id={row_id}")
        return row[0], row[1]
    finally:
        database.close()
