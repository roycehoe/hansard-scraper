# STYLE.md

Personal coding idioms for this codebase. Follow these when writing or reviewing code.
This document only contains things Claude would get wrong without being told — not standard Python conventions.

**Automated enforcement:** `ruff` runs `I` (import sorting) and `F` (unused names/imports) via pre-commit — see `pyproject.toml [tool.ruff.lint]`. `black` handles formatting — run manually with `black .`. Everything else in this file is enforced by code review only.

**Rule strength:** All rules are hard requirements unless marked **Preference** — team default where a technical alternative exists; deviate only with explicit justification.

## Variable Naming

**Encode state and role in the name.**

- Must use `validated_` / `unvalidated_` prefix on variables that have or have not been through a validation step — makes the validation boundary visible; prevents passing unvalidated data to code that assumes it is safe
- Must use `{key}_to_{value}` pattern for dict/mapping variables — makes lookup intent visible without tracing what the dict contains — e.g. `project_id_to_project_creator`, `user_id_to_user`
- Must use `noun_to_verb` pattern for objects held in order to act on them — encodes the planned action alongside the object — e.g. `user_to_update_suspension_status`, `user_project_to_favourite`
- Must use `is_` prefix on all boolean variables and boolean constants — unambiguous in conditional expressions — e.g. `is_using_lower_confidence`, `IS_USING_AZURE_AI_VECTOR_SEARCH`
- Must strip only `get_` from the function name when naming the variable that holds the result — avoids name stuttering: `get_trigger_databricks_job_response` → variable is `trigger_databricks_job_response`

**No abbreviations for domain objects, ever** — abbreviated names require the reader to maintain a mental mapping; full names are self-documenting at the read site. Spell out full names for loop variables. `enumerate` index counters may use `i` when the index has no domain meaning; use a descriptive name when it does.

```python
# Good
for user_project in user_projects: ...
for i, source in enumerate(sources): ...             # i: no domain meaning
for citation_number, source in enumerate(sources):   # descriptive when index matters
    ...

# Bad
for up in user_projects: ...                         # up abbreviates the domain object
```

```python
# Good
unvalidated_user = crud_user.get_by_email(email)
if unvalidated_user is None:
    raise UserNotFoundException
validated_user = unvalidated_user

# Bad
user = crud_user.get_by_email(email)
```

## Function Naming

- Private helpers that **return** an object must use `_get_` prefix — signals the helper produces a value, not a side effect — e.g. `_get_processed_documents()`
- Private helpers that **return a bool** must use `_is_` prefix — readable in conditional context — e.g. `_is_token_revoked()`
- Private helpers that **do** something side-effectful must use `_verb_noun` — makes clear the helper does work, not returns a value — e.g. `_execute_soft_delete()`. Never `_do_` — it describes no specific action.
- Router function name must exactly match its corresponding service function name. This is the explicit coupling between layers.
- Never use hedge words in names — hedge words describe optional behavior that belongs in the logic, not the name: `update_conversation_summary` not `update_conversation_summary_if_needed`.

## Guard Clauses, No Else

Early-exit with `raise` or `return` — keeps the happy path at the lowest indentation level. Never write an `else` branch when the `if` branch exits.

Compound `or` guards where each condition represents a different failure mode must be split into separate `if` blocks — each failure mode remains readable and raiseable in isolation:

```python
# Good
if authorization is None:
    raise AuthEntraTokenMissingException
if not authorization.startswith(BEARER_PREFIX):
    raise AuthEntraTokenMissingException

# Bad
if authorization is None or not authorization.startswith(BEARER_PREFIX):
    raise AuthEntraTokenMissingException
```

## None Checks

Do not use falsy checks as None guards — SQLModel objects can evaluate as falsy in unexpected states. Use `if user is None:` explicitly.

```python
# Good
if user is None:
    raise UserNotFoundException

# Bad — ambiguous for ORM objects
if not user:
    raise UserNotFoundException
```

## Comparisons

Always repeat the full comparison rather than using `in` / `not in` — each condition is independently readable, and future conditions won't silently fold into the group.

```python
# Good
if role != UserProjectRole.OWNER and role != UserProjectRole.ADMIN:
    ...

# Bad
if role not in [UserProjectRole.OWNER, UserProjectRole.ADMIN]:
    ...
```

## Exception Handling

Each exception type gets its own `except` block — handlers often diverge over time; grouping prevents adding different handling without first splitting the block. Never group exception types in a tuple, even when the handler is identical:

```python
# Good
except AuthEntraTokenMissingException:
    raise
except AuthEntraTokenInvalidException:
    raise
except SomeOtherException:
    raise AuthEntraTokenInvalidException

# Bad
except (AuthEntraTokenMissingException, AuthEntraTokenInvalidException):
    raise
```

## List Comprehensions

Always inline single-use transformations directly in `return` statements — avoids naming a throwaway variable that only exists to be returned on the next line:

```python
return [
    ProjectMember(
        user_id=user_project.user_id,
        role=user_project.role,
    )
    for user_project in user_projects
]
```

## Function Signatures

Three or more parameters must be one per line, closing paren on its own line — makes signature changes diff-friendly; adding one parameter touches exactly one line.

```python
# Good
def create_project(
    session: Session,
    user: User,
    request: CreateProjectRequest,
) -> Project:
    ...
```

Must use `*` to force keyword-only arguments when a function has optional boolean flags — prevents unreadable positional boolean calls like `update(user, True, False)`:

```python
def update_permissions(
    self,
    user: User,
    role: UserRole,
    *,
    update_updated_at: bool = True,
    revoke_previously_issued_tokens: bool = True,
) -> User:
    ...
```

## Type Annotations

- **Preference** — Use `Optional[T]`, never `T | None` — ruff's `UP007` would flag this as deprecated; we intentionally disable it to keep the 54+ existing uses in `schemas/` consistent. Do not write new code using `T | None`. Do not migrate existing `Optional[T]` to `T | None`.
- Use `list[T]` (lowercase), never `List[T]` from typing — `List[T]` is deprecated since Python 3.9 (PEP 585).
- **Preference** — No walrus operator (`:=`) — `:=` is visually similar to `==`; misreading one for the other is a silent correctness bug.
- Never use `from __future__ import annotations` — defers annotation evaluation in ways that can break Pydantic v2, which evaluates annotations at class creation time.

## Multi-Value Returns

Functions that return multiple values use a typed `@dataclass`, never a tuple — tuple returns require callers to unpack positionally; adding a field breaks all callers silently:

```python
# Good
@dataclass
class SourceImageDimensions:
    width: int
    height: int

def _get_source_image_dimensions(...) -> SourceImageDimensions:
    return SourceImageDimensions(width=w, height=h)

# Bad
def _get_source_image_dimensions(...) -> tuple:
    return w, h
```

## Constants

Inline string and numeric literals that represent fixed named values must be defined as module-level constants, never inlined at the usage site — a name makes the value self-documenting and ensures updates happen in one place:

```python
# Good
BEARER_PREFIX = "Bearer "
TOKEN_OFFSET = len(BEARER_PREFIX)

if not authorization.startswith(BEARER_PREFIX):
    ...
token = authorization[TOKEN_OFFSET:]

# Bad
if not authorization.startswith("Bearer "):
    ...
token = authorization[7:]
```

Always use `_` as a thousands separator for integer literals ≥ 1000 — makes large literals scannable: `32_000`, `3_840`, `10_000`.

Always use **tuples** (not lists) for constant sequences — immutable by construction; a list invites accidental mutation:

```python
REQUIRED_CLAIMS: tuple[str, ...] = ("aud", "exp", "iat", "iss", "oid", "tid")
```

## Pydantic Models

**Response schemas** (names ending in `Response` or `Data`) must not have field defaults. Every field must be explicitly populated at construction. If a field can be absent, type it `Optional[T]` but do not add `= None` — require the caller to pass `None` explicitly. Defaults on response models hide missing fields silently.

**Mutable field defaults** must use `Field(default_factory=...)` — mutable defaults are shared across all instances in Python; a plain `[]` default means every instance shares the same list:

```python
# Good
prior_user_instructions: list[str] = Field(default_factory=list)
options: OptionsIn = Field(default_factory=OptionsIn)

# Bad
prior_user_instructions: list[str] = []
options: OptionsIn = OptionsIn()
```

**External API responses** must be parsed through a Pydantic model before any field access — dict key access fails at access time; Pydantic validation fails at the boundary, which is where you want to discover schema changes:

```python
# Good
class EntraDiscoveryResponse(BaseModel):
    jwks_uri: str
    issuer: str

state = EntraDiscoveryResponse.model_validate(response.json())

# Bad
config = response.json()
jwks_uri = config["jwks_uri"]
```

Do not add `model_config = ConfigDict(extra="forbid")` unless there is a specific reason — the project default is permissive; `extra="forbid"` breaks when external APIs add new fields.

## Error Messages

Second person, sentence fragment, capital first word, ends with period — reads as feedback to the user, not a developer note:

```
"You do not have permission to access this project."
"Password must contain at least one uppercase letter."
```

Not: `"permission denied"`, `"invalid password"`, `"You don't have permission to access this project"`

## Validator Functions

Two distinct patterns:

**`get_validated_*`** — returns the validated object or raises. Use when the caller needs the object. Naming makes the return type predictable and the validation step visible in the call chain.

```python
def get_validated_reset_password_token(token: str) -> PasswordResetToken:
    result = crud_token.get_by_token(token)
    if result is None:
        raise PasswordResetTokenNotFoundException
    return result
```

Never return `True`/`False` — boolean returns force callers to add a branch; raising makes the failure path unambiguous.

## String Field Defaults

Always use `""` (empty string) as the default for optional string fields in domain models, never `None`. Reserve `None` for fields that are genuinely absent/unknown — this keeps `Optional[T]` meaningful rather than routine.

```python
# Good
description: str = ""

# Bad — None implies "unknown", not "not yet provided"
description: Optional[str] = None
```

## Datetime

Always `datetime.now(timezone.utc)`. Never `datetime.now()` (returns a naive datetime with no timezone) or `datetime.utcnow()` (deprecated, also naive).

```python
# Good
time_now = datetime.now(timezone.utc)

# Bad
time_now = datetime.now()     # naive — no timezone info
time_now = datetime.utcnow()  # deprecated, also naive
```

