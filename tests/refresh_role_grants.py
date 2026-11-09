import re
from dataclasses import dataclass
from pathlib import Path

_REFRESH_DOCUMENT = Path(__file__).parent.parent / "docs" / "refresh.md"
_WRITE_ROLE_HEADING = "## Write role SQL"
_SQL_FENCE_PATTERN = re.compile(r"```sql\n(.*?)```", re.DOTALL)
_ROLE = "hansard_refresh"
_GRANT_PATTERN = re.compile(
    r"^GRANT\s+(?P<privileges>.+?)\s+ON\s+(?P<sequence>SEQUENCE\s+)?(?P<objects>.+?)\s+TO\s+(?P<role>\S+)$",
    re.IGNORECASE | re.DOTALL,
)
_PRIVILEGE_PATTERN = re.compile(
    r"(SELECT|INSERT|UPDATE|MAINTAIN|USAGE)(?:\s*\(([^)]*)\))?", re.IGNORECASE
)
_FROM_OR_JOIN_PATTERN = re.compile(r"\b(?:from|join)\s+(\w+)")
_INSERT_PATTERN = re.compile(r"^insert into (\w+)")
_UPDATE_PATTERN = re.compile(r"^update (\w+) set (.*?)(?: where | returning |$)")
_SET_COLUMN_PATTERN = re.compile(r"(?:^|,\s*)(\w+)\s*=")


@dataclass(frozen=True)
class RoleGrants:
    table_privileges: frozenset[str]
    column_privileges: frozenset[str]
    sequence_usages: frozenset[str]


def get_write_role_blocks() -> list[str]:
    section = _REFRESH_DOCUMENT.read_text(encoding="utf-8").split(_WRITE_ROLE_HEADING)[
        1
    ]
    return _SQL_FENCE_PATTERN.findall(section)


def get_role_grants(sql_block: str) -> RoleGrants:
    table_privileges: set[str] = set()
    column_privileges: set[str] = set()
    sequence_usages: set[str] = set()
    for statement in sql_block.split(";"):
        grant_match = _GRANT_PATTERN.match(statement.strip())
        if grant_match is None or grant_match["role"] != _ROLE:
            continue
        objects = [name.strip() for name in grant_match["objects"].split(",")]
        if grant_match["sequence"] is not None:
            sequence_usages.update(objects)
            continue
        for privilege, columns in _PRIVILEGE_PATTERN.findall(grant_match["privileges"]):
            for table in objects:
                if columns == "":
                    table_privileges.add(f"{privilege.upper()} {table}")
                    continue
                for column in columns.split(","):
                    column_privileges.add(
                        f"{privilege.upper()} {table}.{column.strip()}"
                    )
    return RoleGrants(
        frozenset(table_privileges),
        frozenset(column_privileges),
        frozenset(sequence_usages),
    )


def _has_update_privilege(table: str, role_grants: RoleGrants) -> bool:
    return f"UPDATE {table}" in role_grants.table_privileges or any(
        column_privilege.startswith(f"UPDATE {table}.")
        for column_privilege in role_grants.column_privileges
    )


def _get_statement_violations(
    statement: str, table_names: frozenset[str], role_grants: RoleGrants
) -> list[str]:
    if statement.startswith("delete") or statement.startswith("truncate"):
        return [f"the role has no DELETE or TRUNCATE: {statement}"]
    violations: list[str] = []
    insert_match = _INSERT_PATTERN.match(statement)
    if insert_match is not None:
        table = insert_match[1]
        if f"INSERT {table}" not in role_grants.table_privileges:
            violations.append(f"INSERT on {table}")
        if f"{table}_id_seq" not in role_grants.sequence_usages:
            violations.append(f"USAGE on {table}_id_seq")
        if (
            "returning" in statement
            and f"SELECT {table}" not in role_grants.table_privileges
        ):
            violations.append(f"SELECT on {table} for RETURNING")
    update_match = _UPDATE_PATTERN.match(statement)
    if update_match is not None:
        table = update_match[1]
        for column in _SET_COLUMN_PATTERN.findall(update_match[2]):
            if (
                f"UPDATE {table}.{column}" not in role_grants.column_privileges
                and f"UPDATE {table}" not in role_grants.table_privileges
            ):
                violations.append(f"UPDATE on {table}.{column}")
        if (
            " where " in statement
            and f"SELECT {table}" not in role_grants.table_privileges
        ):
            violations.append(f"SELECT on {table} for WHERE")
    for table in _FROM_OR_JOIN_PATTERN.findall(statement):
        if table not in table_names:
            continue
        if f"SELECT {table}" not in role_grants.table_privileges:
            violations.append(f"SELECT on {table}")
        if "for update" in statement and not _has_update_privilege(table, role_grants):
            violations.append(f"UPDATE on {table} for FOR UPDATE")
    return violations


def get_grant_violations(
    statements: list[str], table_names: frozenset[str], role_grants: RoleGrants
) -> list[str]:
    violations: list[str] = []
    for statement in statements:
        violations.extend(
            _get_statement_violations(
                " ".join(statement.lower().split()), table_names, role_grants
            )
        )
    return violations
