from dataclasses import dataclass


@dataclass
class MariaDBConfig:
    host: str = "localhost"
    port: int = 3306
    root_password: str = ""
    admin_user: str = "root"
    socket_path: str = ""
