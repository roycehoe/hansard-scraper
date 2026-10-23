# STYLE.md

Coding idioms for this codebase: only the things a contributor would get wrong without being told. Follow them when writing or reviewing code. This file is authoritative on what the rules are.

**Enforcement.** `ruff` owns import order and unused names (`I`, `F`), annotation presence (`ANN`, minus `ANN204` because `__init__` takes no return annotation), `else` after an exit (`RET505` to `RET508`), the bare variable before a `return` (`RET504`), blind `except` (`BLE001`), magic-number comparisons (`PLR2004`), `print()` (`T201`, `T203`), naive `datetime` (`DTZ003`, `DTZ005`) and module-level `global` writes (`PLW0603`). See `pyproject.toml [tool.ruff.lint]`; `ANN204` is the one ignored code. Everything else below is enforced by review. No Python formatter runs in this repo.

**Scope.** Every Python file in the app layers, `scripts/` and `tests/`. Shipped migrations in `alembic/versions/` are exempt and are never edited; `alembic/script.py.mako` is in scope, so new migrations start compliant.

**Grades.** `blocking`: a reviewer blocks the change on it. `expected`: the default; deviating needs a reason stated in the commit. `expected†`: `expected`, with one recorded carve-out in the rule text. `taste`: a suggestion; the author decides. **Preference**: the default where a technical alternative exists. A rule yields only to a demonstrated technical cost, never to a style preference. Never flatten a `taste` into a "must".

**Counter-sites.** Where a rule has live counter-sites, they are accepted until a deliberate sweep changes them everywhere. Consistency outranks correctness at the level of style: a defect that is uniform across the codebase stays uniform until one change fixes every site. New code never joins a divergence. The style sweep that introduced this file was that deliberate sweep, so the tree should hold no counter-sites today; any you find is a bug in the sweep, not a precedent.

---

## Naming

The layer decides the name's shape. `expected`

| Thing | Pattern | Example |
|---|---|---|
| CRUD class | `CRUD` + PascalCase table | `CRUDSpeech` |
| CRUD method | verb, or verb + the columns it filters on | `create_many`, `get_by_sitting_dates` |
| Service function | snake_case verb phrase; a builder is `build_` + the entity it returns | `build_report`, `build_sitting` |
| Populate stage | `populate_` + plural entity, in a module of the same name | `populate_speeches` in `populate/speeches.py` |
| Gateway function | `get_` + what the call fetches + `_response` | `get_hansard_topic_response` |
| Schema (API shape) | PascalCase noun for the payload | `HansardSearchResult` |
| Table class | PascalCase noun, one per table | `Sitting`, `Attendance` |
| Exception class, all in `exceptions.py` | `Hansard` + noun + `Error` | `HansardGatewayError` |

The affix carries type, purity, state and intended use, so the reader never opens the body to find out. Never Hungarian notation. `expected`

| Affix | Applies to | Example |
|---|---|---|
| `is_` | every boolean variable and parameter | `is_present`, `is_drop_cap` |
| `_is_` | pure boolean-returning private helper, about a state that already holds | `_is_section_header_speaker` |
| `_should_` | pure boolean-returning private helper, deciding an action not yet taken | no site yet; the shape is `_should_retry_page` |
| `_get_` | value-returning private helper | `_get_membership_label` |
| `_verb_noun` | side-effecting or transforming private helper (never `_do_`) | `_merge_wrapped_bold_lines` |
| `_at` | timestamps, where a model takes one | no column yet |
| `{key}_to_{value}` | dicts and mappings | `_OCR_FORM_TO_CORRECTED_NAME`, `holder_by_role` is the same idea read backwards and is not the pattern |
| `noun_to_verb` | an object held in order to act on it | `sitting_dates_to_fetch`, `sittings_to_process` |
| `error` | the variable bound by `except ... as` | `error`, `error_to_record`, `unexpected_failure` |

When naming the variable that holds a call's result, strip only `get_` from the function name: `get_hansard_topic_response` fills a `hansard_topic_response`.

**Do not add the `validated_` / `unvalidated_` variable prefix**, in any layer. Name the variable for what it is and validate it; reassigning the same value to a second name to record that a check happened is noise the reader has to track. The same defect recurs whenever a qualifier only restates what the context already implies.

- `expected`: **Name the function for what it returns or mutates, and propagate a rename everywhere.** When the returned type's name changes, the rename travels through the service, the populate stage, the scripts and every import list in the same commit. A populate module's name matches its function's name: `populate/speeches.py` holds `populate_speeches`. Never join branches with `or` in the name; the branching is irrelevant to the caller, so name the function for the end goal, not the paths it takes.
- `expected`: **`is_` is not optional on a boolean.** Every boolean variable and parameter takes `is_`; a boolean constant takes `IS_`. Column names on the tables already follow this (`is_present`, `is_member`, `is_legislative_assembly`).
- `expected`: **Spell the domain object out in full.** No abbreviations ever, and no bare `response`, `row` or `result` where the type is more specific. Loop variables too: `for speaker in speakers`, never `for s in speakers`. An `enumerate` counter may be `i` only when the index has no domain meaning; a regex match is `match`, a caught exception is `error`. One exemption: a column or alias that mirrors the source API keeps the API's spelling (`parl_no`, `sno`, `ptba_from`), because the raw tables store the response exactly as received. The variable that reads it does not: `parliament_number = sitting.parlement_no`.
- `expected`: **A name is guessable from the import path alone.** A reader holding only the path and the name must be able to guess what the thing is and how it is grouped. Spelling a word out in full does not save it: a name for a container or a metaphor rather than the domain is still wrong. A vendor's product name is an implementation detail and never reaches a module or function name: the module that calls `html2text` is `utils/markdown_parser.py`, not `utils/html2text_parser.py`.
- `expected`: **One word per concept, and the domain prefix on every exception class.** The repo's word is `Hansard`; the same noun appears in the class name and in the message it carries.
- `expected`: **The caught exception is `error`.** Where the handler holds it in order to hand it to something else, it takes the `noun_to_verb` affix above: `error_to_record`, `error_to_raise`. A parameter that only reads the exception it was handed is plain `error`. Where a `BaseException` catch-all sits beside a typed handler in the same `try`, the catch-all is `unexpected_failure`, so the two blocks do not read alike. `e` and `exc` are out under *Spell the domain object out in full*.

  ```python
  # gateway/hansard_topic.py:14-31
  def get_hansard_topic_response(report_id: str) -> HansardTopicResponse:
      try:
          response = send_with_retry(
              partial(
                  requests.post,
                  url=settings.hansard_topic_url,
                  json={"id": report_id},
                  headers=CRAWL_HEADERS,
                  timeout=REQUEST_TIMEOUT_SECONDS,
              )
          )
          return HansardTopicResponse(**response.json())
      except requests.exceptions.RequestException as error:
          raise HansardGatewayError(f"Topic request failed for {report_id}") from error
      except ValueError as error:
          raise HansardGatewayError(f"Topic request failed for {report_id}") from error
      except TypeError as error:
          raise HansardGatewayError(f"Topic request failed for {report_id}") from error
  ```

- `expected`: **No hedge words in a name** (`_if_needed`, `_maybe_`). A hedge describes optional behaviour, which belongs in the logic, not the name.
- `expected`: **Validators come in exactly two shapes.** `get_validated_*` returns the validated object or raises; use it when the caller needs the object. `validate_can_*` returns `None` and raises; use it for a gate the caller only needs to know passed. Never return `True`/`False` from either: a boolean forces the caller to branch, raising makes the failure path unambiguous. The repo has no site yet; this governs the first one.

---

## Layers

The layer table in `CLAUDE.md` says where code goes. These rules say what each layer may do once it is there.

- `expected†`: **CRUD does one C/R/U/D on what it is handed.** A method that queries *and* mutates is two methods, and the decision between them belongs to the populate stage. The method takes the row it is given rather than looking it up itself.
- `blocking`: **CRUD holds no business rule, on either side.** **Reading:** every filter value is a parameter and the name lists the columns filtered on, never the concept the caller has in mind. `get_report_ids_by_speaker_id_null_and_speaker_regex(pattern)`, never `get_report_ids_with_unlinked_speaker(pattern)`. A sampling loop over parliaments and report types is a script's job, not a CRUD method's. **Writing:** the test is how many attributes the method writes and whether its name identifies them. A domain verb is right for a **single** attribute the name names: `set_speaker_ids_bulk` writes `speaker_id` and nothing else. Once a method writes several attributes a reader cannot infer, it is a general `update_` taking those fields. **Returning:** SQLModel objects, primitives, or a list of the projection dataclass declared beside the method; never a dict or tuple built inside CRUD, and nothing no caller consumes.
- `expected`: **A lookup names every filter it applies**, with `_and_` between them: `get_by_sitting_date_and_markdown_content_not_null`.
- `expected`: **Instantiate CRUD and call it in one expression:** `speakers = CRUDSpeaker(session).get_all()`. Never bind the instance to a variable first: it holds no reusable state, so the intermediate name buys nothing and reads as though it did. A loop that writes in batches calls `CRUDSpeech(session).create_many(batch)` each time.
- `expected†`: **`services/` and `utils/` take data and return data or raise.** No session, no HTTP, no hidden mutation; that is what makes them safe to import from any layer. A function takes the values it reads, not the object holding them: pass primitives, and pass the row only once that would mean three or more arguments. A pure function belongs in `utils/`, and a function is never defined inside another function. One licensed impurity: `database/init.py` builds the engine at import, because every session comes from it. It does not generalise.
- `blocking`: **Never share sideways between peers at the same layer.** Two peers are never collapsed into each other; where sharing genuinely is right it comes from a *lower* layer, because sideways sharing couples peers and invites circular imports. **For two `services/` or two `gateway/` modules, that lower layer is `utils/`**: the name helpers that `services/attendance.py` and `services/person.py` both need live in `utils/names.py`, and importing them is required rather than merely tolerated. The constraint that keeps it safe is directional: `utils/` imports nothing from `services/`, `gateway/`, `crud/` or `database/`. Not a licence to reach into `utils/` for anything impure; if the shared thing needs a `Session`, it is not a `utils/` candidate. `populate/` is the one layer that may import from every other, and `scripts/` may import from any layer below `populate/` plus `populate/`'s constants.
- `expected` (judgement call): **Collapse duplication only when it is mechanically identical *and* its meaning is fixed.** Duplicate when the copies encode rules that could plausibly diverge, even if they are byte-identical today. The sync and async pairs in `gateway/` are the licensed duplicate: they differ in transport and nothing else.
- `taste`: **A shared base class for two tables is a judgement call**, in four criteria: a short file does not need one; a file becoming excessively long may use one to shorten it; a **1-1 mapping** may be considered; **non-1-1 is generally a bad idea**, because a base plus extensions forces the reader to assemble one class's definition from two places. `Sitting` repeats every column of `HansardSittingDateResponse` on purpose. Never route this to a linter.
- `expected`: **`crud/` is a Table Data Gateway, and a method's name is a claim about the row after the call.** If any legal combination of arguments falsifies that claim, or the method writes anything the name does not state and no parameter supplies, the name asserts a rule the method does not enforce. A wide write gets a typed record only where the same field group already appears in two or more independent signatures on the same model; the record is declared beside the model it describes. Otherwise the method takes exactly the fields it sets, with no optional parameters.
- `expected`: **A gateway is named for the concrete action, returns a parsed model, and does nothing past that.** It maps transport failures (`requests.exceptions.RequestException`, `httpx.RequestError`, a body that is not JSON) to `HansardGatewayError` in one wrapper beside the call, wraps the body in the Pydantic schema for that endpoint, and interprets nothing else. A gateway never decides what a missing field means; that belongs to the populate stage that called it.
- `expected`: **A concern consumed by more than one populate stage is not a stage.** Pure logic goes to `services/`, DB access to `crud/`, a reference table to a constants module beside its readers. Where code goes is `CLAUDE.md`'s table, not this guide's.
- `expected†`: **No helper for logic that is *both* single-use *and* uncomplicated.** The test is a conjunction; both halves must hold before the helper is questionable. A helper called from several places, or carrying real branching, earns its name however short its call list is. Duplicate until the shape is proven. One carve-out even when both halves hold: a one-liner helper is legitimate when its name carries meaning the code cannot express, as `_replace_nbsp_with_space` does in the markdown pipeline; the name stands in for the comment the no-comments rule forbids.
- `expected`: **No indirection that only re-supplies what the call site already has**, including a helper for a value that is already a field on the row.
- `expected`: **A private helper is defined before the function that calls it, and sibling modules stay symmetric.** The helper's `def` goes above its caller, never below; the reader meets it before the code that depends on it. Two modules doing near-identical jobs keep the same shape and the same order (`gateway/hansard_topic.py` and `gateway/hansard_report.py`).
- `expected`: **Early terminate; never declare a variable in order to populate it later.** A function does not assign a value and then reassign it under a condition; each branch states its whole case and returns. The named anti-shape is a local initialised to `None` against the chance a later branch fills it in. Distinct from the no-`else` rule below: that one is about indentation, this one is about mutable locals, and it bites where there is no `else` at all.
- `expected`: **No bare variable that exists only to be returned on the next line.** `x = f(...)` then `return x` names nothing the reader did not have from the call. Two deliberate exceptions: naming a SQLModel `statement` before executing it, and a value named to be passed as a constructor argument. The ban is scoped to a name whose only consumer is the `return` on the very next line; a name consumed by a loop, a dict insertion, or more than one expression is a different shape, and review requires assigning it first rather than building it inline.
- `expected`: **Build only what this iteration needs.** No method for a caller that does not exist yet, no field, no flag, no script option without a user.
- `expected`: **Remove the unused thing *and its whole tail*:** the orphaned exception class, the dataclass field no caller reads, the import and the call it existed for, the CRUD method with no caller.

---

## Control flow and failure

- `expected†`: **Where a function checks and raises, one `if` per failure mode.** Check `None`, missing config, malformed input, and raise a typed exception. A compound `or` guard is split into one `if` per failure mode, even when both raise the same exception, so each mode stays readable and separately raiseable.
- `expected`: **No `else` after an `if` that exits.** When the `if` raises, returns, continues or breaks, the `else` indents the rest of the block for no information. `elif` after an exit is the same defect. Governs every layer.
- `blocking`: **Attempt the operation and catch the failure.** In `services/`, `gateway/`, `crud/` and `populate/`, wrap the work in `try` and catch at the end. **No LBYL pre-check in front of the attempt, including a cheap deterministic one.**

  ```python
  # utils/text.py:14-20: no `if` in front of the attempt
  def _fix_mojibake_run(match: re.Match) -> str:
      try:
          return match.group(0).encode("cp1252").decode("utf-8")
      except UnicodeDecodeError:
          return match.group(0)
      except UnicodeEncodeError:
          return match.group(0)
  ```

- `expected`: **A `None` result is a result, not a pre-check, and `is None`, never a falsy check.** Read this immediately after the EAFP rule; the two are constantly confused. Checking a value you *already hold* and acting on it is legal everywhere: the operation already ran and you are handling its result. LBYL is testing a precondition *in order to avoid attempting* the operation. Use `is None` explicitly, because a SQLModel object, a regex match or a `bs4` tag can evaluate falsy in states you did not mean to test for. An emptiness check on a `str` or a `list` (`if not stripped`) is a different question and stays a falsy check.

  ```python
  # Good: services/speech.py:1354-1355: a completed lookup's result, checked
      if report.markdown_content is None:
          return ReportSpeeches([], ReportSkipReason.NO_MARKDOWN_CONTENT)

  # Bad: falsy, not `is None`
          if not match:
              return None
  ```

- `expected`: **Exception handling for a fallible call lives in one wrapper beside it.** A high-level function bundles lower-level calls; it does not also handle their exceptions mid-flight or reach into their details. Handling goes in **one** dedicated wrapper next to the call. The ban is on *chains*, a helper calling a helper calling a helper, not on the single wrapper.
- `expected`: **Inside the wrapper, handling is flat: one `except` per type**, narrowest first, ordered specific-to-general. Never group types in a tuple, even when the handler is identical; handlers diverge, and grouping lets the next person change one without splitting the block first. Never delegate the classification to a separate helper. See `gateway/hansard_topic.py:14-31` above.
- `expected`: **`except Exception` is not a handler, where the catch decides something.** A blind catch routes the bug it was not written for (a typo's `AttributeError`, a `KeyError` from a renamed field) into the branch built for a parse failure, so the real fault surfaces as the wrong outcome. That harm is the test: the ban reaches a catch that degrades into a silent default, and **not** one that logs and re-raises, or that contains failure in work whose collapse must not reach the caller. Where a blind catch is right, `# noqa: BLE001` carries a **reason** a reviewer can argue with (`# noqa: BLE001 a corpus survey must record every failing document, not stop at the first`). A `noqa` reason is a suppression's argument, not a comment, so the no-comments rule does not reach it.
- `expected`: **An unexpected condition raises where it is discovered.** It never degrades into an empty list, a `None`, a silent default, or a partially-completed write.
- `blocking`: **One failure mode, one exception, carried out of the layer that found it.** A gateway failure is a `HansardGatewayError` with a message naming the request that failed; a parse failure, when one is raised, is its own `Hansard` + noun + `Error` subclass of `HansardError` in `exceptions.py` (none exists today; the sweep removed an unreferenced one). An exception must never imply a scenario that did not happen.

---

## Types and data

- `blocking`: **Parse at the boundary before reading a field.** Anything from outside the process (the Hansard API, parliament.gov.sg, a JSON file under `data/`) becomes a Pydantic model before any field is read, because dict access fails where the value is used while validation fails where the schema changed. `gateway/` constructs directly with `Schema(**response.json())`; a `data/` file is read through `Schema.model_validate(...)`.
- `expected`: **The declared type admits only reachable states.** `Optional[T]` only where the value is genuinely absent or unknown; `""` and `[]` instead of nullability; **no field defaults on a schema that models a response**, because a default hides a field the caller forgot. One licensed exception, stated in a NOTE on the schema: an endpoint that returns several body shapes (`getHansardTopic` and `getHansardReport/` also answer with `{errorCode, description}`) gets a schema whose fields are all `Optional` with a `None` default, because the caller reads a missing field as absent, not as an error. **Standing design, not divergence:** the two raw response tables (`HansardWebsiteResponse`, `HansardSittingDateResponse`) and their entity twins declare every field `Optional`, because they store two API formats in one row shape and that is what the DB schema holds. Changing it is a migration, not a style fix.

  ```python
  # Good: database/report.py:38-39
      title: str
      subtitle: Optional[str] = None
  ```

- `expected`: **An id that points at a row is a foreign key, a closed set is an enum, and no string literal stands in for either.** Integer ids across layer boundaries. `report_type` compared to `"motion"` inline is the same mistake as a bare id: the `ReportType` enum exists for it.
- `expected`: **Enum value casing follows the enum's origin, until a column persists it.** An internal lifecycle enum's values are UPPER_SNAKE (`ParsedSpeechType.PARSED = "PARSED"`); an enum mirroring the API's wire vocabulary keeps the API's casing verbatim (`ReportType.ORAL_ANSWER = "oral-answer"`), so raw payload values round-trip without a case transform. The carve-out holds only while the enum stays on the wire: the moment a SQLModel column persists it, its values go UPPER_SNAKE, because SQLAlchemy persists the member *name* and a lowercase value writes a label the Postgres type does not have.
- `expected`: **Several values come back as one typed `@dataclass`, never a tuple, and a `@dataclass` is the fallback, not the first move.** Returning one object is first choice; where a method produces a fixed set of scalars, split it into one method per value rather than wrapping the set in a new type. A tuple makes the caller unpack positionally, so adding a field breaks every call site silently, and `row[4]` assumes the value sits where the writer left it. A CRUD method that selects columns returns a list of a dataclass declared in the same `crud/` module, never a list of tuples (`SpeechRow` in `crud/speech.py:15-22`). A service that consumes such rows imports the dataclass from `crud/`; that import reaches no engine code, so the layer rule holds.

  ```python
  # services/report.py:18-21: two values, one record
  @dataclass(frozen=True)
  class ReportHeader:
      title: str
      subtitle: Optional[str] = None
  ```

- `blocking`: **A mapping that encodes a decision is never a module-level constant.** An exception-to-handler or type-to-branch table hides the classification a screen away from the one `try` that uses it: inline it, and past three branches write an `if`/`return` function instead. A **reference table of domain data** is a different thing and is a module-level constant: `VOLUME_TO_PARLIAMENT`, the OCR corrections, the office holders by date. It sits beside its one reader, or in a constants module when several readers share it, and it is never mutated.
- `expected†`: **Every fixed literal becomes a named module-level constant.** The name is the documentation and one place changes when the value does. Module-private constants take a leading underscore; constants other modules import do not. A sequence constant is a **tuple** and a set constant a **frozenset**, immutable by construction. Integer literals of 1000 or more carry `_` thousands separators: `_WRITE_BATCH = 50_000`.

  ```python
  # utils/markdown_parser.py:10
  _MAX_ADJOURNMENT_CONTINUATIONS = 6

  # services/attendance.py:46-47
  _MIN_SURNAME_LOOKUP_LENGTH = 2
  _MIN_PREFIX_WORD_COUNT = 2
  ```

- `expected`: **A comparison against a fixed number names the number.** Inline, `> 80` is a bound with no subject and no place to change it. HTTP status-code comparisons are the noisy class and still want named constants.
- `expected†`: **Anything that varies by deployment is read from `AppSettings` at the point of use**, not hoisted into a module constant or copied into a local, so it stays overridable. The search page size is `settings.search_page_size`, not a `20` in the gateway. Never a secret in code or in a committed file.
- `expected`: **A model declares its own timestamp default, and its fields come in a fixed order:** primary key, business fields, timestamps, state and boolean fields, foreign key ids, relationships. Reordering an existing table's fields is a schema change and is tracked as its own task, not done in passing.
- `expected`: **A constructed timestamp carries its timezone:** `datetime.now(timezone.utc)`, never the naive `datetime.now()` or the deprecated, and also naive, `datetime.utcnow()`. A naive value written to an aware column is wrong by the host's offset and silent about it. A sitting date parsed from the API's `d-m-yyyy` string is a calendar date, not a timestamp, and stays as the column declares it.
- `expected`: **A CRUD mutation method runs prepare, set, persist, return**, each phase separated by a blank line. Prepare only where there is something to prepare; the blank lines are what make the phases visible. Where a model declares `updated_at`, the method sets the clock itself and never takes a timestamp from its caller. A batch method computes one timestamp before its loop and writes it to every row.
- `expected`: **Filtering, sorting, limiting and batching happen in SQL.** Name the `statement` before executing it, wrap a multi-line chain in one pair of parentheses (never a `\` continuation), and chain separate `.where()` calls rather than passing several filters to one so each reads independently. Bend this only when moving the work would change the result; the populate stages that diff two id sets in Python are the licensed bend, because the sets are small and the diff is the stage's whole logic.

  ```python
  # crud/speech.py:175-181
      def get_rows_by_report_ids(self, report_ids: list[int]) -> list[SpeechRow]:
          statement = (
              select(Speech.id, Speech.ordinal, Speech.speaker, Speech.transcript, Speech.report_id, Speech.speaker_id)
              .where(col(Speech.report_id).in_(report_ids))
              .order_by(Speech.report_id, Speech.ordinal)
          )
          return [SpeechRow(*row) for row in self.session.exec(statement).all()]
  ```

- `expected`: **`*` goes before a dangerous default, nothing else.** Default to no `*`; add it only where a caller accidentally overriding that default would be dangerous, whatever the parameter's type. Not an arity rule and not a boolean-parameter rule.
- `expected`: **Every signature is annotated, parameters and return alike**, on public functions and private helpers equally, **except a class `__init__`, which takes no return annotation.** That carve-out is not a case-by-case argument: `__init__` never gets `-> None`. A value whose shape is genuinely unknown (a JSON tree of either API format) is annotated `object`, not `Any`; `ANN401` stays on and takes no `noqa`.

  ```python
  # crud/speech.py:89-91
  class CRUDSpeech:
      def __init__(self, session: Session):
          self.session = session
  ```

- `expected`: **Pick the construct that compels the caller.** Python's typing is unenforced, so the signature does the work: an enum parameter the editor flags, a frozen structure that cannot be mutated, a declared schema instead of `dict`, a `Field` that rejects the bad value.

---

## Comments, diffs and migrations

- `blocking`: **A comment or a docstring is an admission the code failed to say it.** Delete both by default. Exactly three survivors: a `TODO` naming a known-temporary state; a `NOTE` on correct code that looks wrong, explaining *why* rather than *what*; and an inline annotation on an enum member, or an entry in a reference table, whose triggering condition or source is **impossible** to infer from the code: big picture, no implementation detail, eight words. The third is not a softer `NOTE`: a `NOTE` defends code a reader would misread, this one supplies a fact the code cannot contain, such as the volume range an OCR correction was seen in. "Impossible to infer", not "helpful", is the test. A regex's example input is inferable from the pattern and goes.
- `expected`: **Where the repo has no convention for a mechanism, add nothing.** An ad-hoc `logger` call goes on sight, and a log line whose only justification is debugging convenience is declined. The convention that exists: a populate stage logs one line per processed item and one summary line.
- `expected`: **When you do log, it is Loguru's `logger`, never `print()`.** `print()` bypasses the sink configured in `logs.py`, so the line carries no level and never reaches the log file. One carve-out: a script whose stdout *is* its output, such as a JSON template another program reads, writes that output with `print` under `# noqa: T201` carrying that reason; its progress lines still go to `logger`.
- `expected`: **Match the way it is already done here, even when the local choice is worse.** Settle a dispute by the majority of existing untouched code, name the canonical module to copy from, and raise standardisation as its own change rather than fixing it in passing. The one documented exception is the aware-timestamp rule above, which stops a naive `datetime` from spreading even where the local majority is already naive.
- `blocking`: **A cross-cutting mechanism is implemented everywhere or nowhere.** A mechanism is cross-cutting when its value depends on being applied uniformly, as opposed to a local feature that merely happens to be reusable. A mechanism that spans the codebase (outbound-call timeouts, retry, batching) ships in one deliberate full sweep that decides it for every site, or it does not ship at all; adding it piecemeal in whichever change first happens to need it is refused at review.
- `expected`: **Every changed line traces to the task.** Revert out-of-scope edits, and say any deliberate gap out loud: a `TODO`, a written note, or an explicit "not in scope", rather than leaving it silent.
- `blocking`: **A migration keeps the chain single-headed.** One head, a `down_revision` pointing at the real predecessor, and `python -m alembic check` clean before the commit. Two changes adding a migration on the same predecessor fork the chain and break `alembic upgrade head` outright; check `python -m alembic heads` returns exactly one head, and join a real fork with a merge revision.

---

## Two carried preferences

- **Preference**: **Repeat the comparison in full rather than using `in` / `not in` against a literal.** Each condition stays independently readable, and a future condition cannot silently fold into the group. Membership in a named reference table (`speaker in NON_SPEAKERS`) is a lookup, not a comparison, and is not what this governs.

  ```python
  # Good
      if report_type != ReportType.PRESIDENT_ADDRESS and report_type != ReportType.ATBP:
          return parsed

  # Bad
      if report_type in ("president-address", "atbp"):
  ```

- **Preference**: **`Optional[T]`, never `T | None`.** Chosen for consistency with the existing uses across `schemas/` and `database/`; ruff's `UP007` is deliberately not enabled. Do not write new `T | None`, and do not migrate existing `Optional[T]`.

---

## Sweep rulings

Decisions made while the guide was applied to the whole tree, kept here so the next sweep does not relitigate them.

1. An inline regex predicate keeps its truthiness test (`if _RE.search(text):`). Only a match bound to a name is tested with `is None`.
2. A `str` constant that serves `in` on single characters stays a `str`. An empty string is `in` any `str` and in no frozenset, so the change would alter a result.
3. `_build_`, `_parse_`, `_extract_` and `_classify_` are transforming helper verbs under `_verb_noun`. `_get_` is for a value lookup only.
4. A per-module timeout constant may repeat across modules while `AppSettings` has no timeout field.
5. A `NOTE` starts lowercase after `NOTE:` and says why the code looks wrong, never what it does.
6. The eight-word cap on a reference-table annotation is counted, not estimated.
7. A `StrEnum` member is compared through the member (`report_type == ReportType.MOTION`), never through the wire literal, and `in` against a tuple of literals is written out as a chain of `!=`.
8. A CRUD projection's dataclass is declared in the `crud/` module that returns it and is built positionally in the select's column order, so the SQL does not change.
9. A streamed CRUD read (`yield_per`) wraps each row lazily in a generator expression, so the query still runs at call time and memory use does not change.
10. When removing a dead field leaves a dataclass with one field, the dataclass goes too and the builder returns the inner object.
11. Renaming a variable never changes a log line's text. Log wording changes only under the print-to-logger rule.
12. Where the pure helpers of two `services/` peers moved to `utils/names.py`, the moved names dropped their leading underscore and no re-export stayed behind; every importer names the new home.
13. A gateway picks the response schema by the only discriminator the API offers. For `getHansardReport/` that is the shape of the body (a `metadata` key means the nested format), and the populate stage dispatches on the model type to pick the builder. The sitting date was the discriminator until 14 October 2026, when the nested format turned out to start on 10 September 2012, not on `settings.sitting_date_format_change`.
14. NUL bytes are stripped from a sitting-date body in the gateway, before the schema is built, so the stored row is what the schema saw.
15. A comparison against 0 or 1 names no constant, and 0 or 1 as an offset, step, origin or unit (`+ 1`, `days=1`, `range(0, ...)`, `enumerate(x, 1)`) stays inline, as does a literal its keyword already names (`indent=1`). A constant that only names singularity or emptiness is inlined; a 1 that is a threshold or a domain number keeps its name.
16. A pipeline that threads one value through steps written `value = step(value)` is not the declare-then-populate shape, conditional steps included. The banned shape is a local that waits for a later branch to give it its value.
17. An `AppSettings` field declared `Optional` whose `None` means not configured is a designed state. A function that does nothing when it is `None` handles a value it holds; it does not swallow an unexpected condition.
18. A dataclass is declared in the module that builds it, above its first user. A populate stage's carrier type stays in the stage while only the stage reads it, and moves down with its builder when the builder moves.
19. A hand-kept file under `data/` is read through its schema by one function in `utils/data_files.py` once two modules read it; one reader reads it in place. The function returns the parsed schema and derives nothing, so it stays a boundary parser. A repository file read is not the session, HTTP or mutation the `utils/` clause bans.
20. Known fields are copied by name, one assignment each. A string list of field names driving `getattr` and `setattr` hides which fields a write touches and fails at run time where an attribute fails in the editor.
21. A plan file a script writes and reads back is input on the read, because a reviewer may have changed it. It is parsed through a schema in `schemas/`. The write keeps `json.dumps` so the file's bytes do not change.
22. The helper rules reach `scripts/`. A pure helper with one caller stays beside that caller in every layer; the `utils/` placement rule fires when a second module needs the helper, and two scripts needing one send it to `utils/`.
23. A name imported by another module is public and drops its underscore at the definition and every use. A NOTE licensing a private import is not a licence; the import is.
24. A NOTE stays when deleting it would make a careful reader change the code, and goes when the reader would only learn a fact and leave the code alone; a kept fact moves to the data-loss register row or ADR that covers the rule. A reference table takes one source line of eight words at table level, counted as an entry's annotation is.
25. The never-a-tuple rule governs values that cross a function boundary. A tuple that is a dict or set key, or that one function builds and consumes, is not a return; a positional read on it still becomes unpacking.
26. A parameter that receives a column keeps the column's type. `report_type: str` and `report_version: str` change to the enum in the commit that changes the columns, and compare through the enum member meanwhile.
27. A value is deployment-varying, and an `AppSettings` field, only when two deployments need different values today. A rule of the refresh or a vendor's limit with one value is a module constant.
28. `_has_` joins `_is_` as a pure boolean helper about a present state, read as containment. `_try_` is a hedge; a lookup that may find nothing is `_get_` and returns `Optional`.
29. A dataclass with one field is a wrapper and goes; its builder returns the field. Sweep ruling 10 applies however the dataclass came to hold one field.
30. A private class that one service function builds, mutates and consumes, and that never reaches a caller, is a local data structure and not hidden mutation. Its attributes are annotated.
31. A dataclass whose fields are never reassigned after construction is `frozen=True`. Mutating a container a field holds is not reassignment.
32. The sideways ban governs `services/`, `gateway/`, `populate/` and `scripts/`. `database/` modules import each other to register the class a foreign key or relationship names, and `utils/` modules import each other because no lower layer exists; `gateway/http.py` is the one transport module the gateways share.
33. `row` is the name of the SQLAlchemy `Row` inside the ruling 8 comprehension, where it has no domain type yet. Outside that comprehension a bare `row` is a spelling violation.
34. The no-`else`-after-exit rule names `if` and `elif`. A loop's `else` is the no-`break` branch and stays.
35. A request body sent verbatim keeps its values inline in the API's spelling, like a column that mirrors the source. A value that two requests send takes a name.
36. A CRUD projection field and a CRUD method name keep a column's API spelling, because both name the column. The variable that reads the field spells the domain word.
37. Paginating a list endpoint to a complete result, including re-requests and dedupe by id, is the gateway's fetch and stays in `gateway/`. Reading meaning out of the parsed body (a flag, a name split, an id mapping) is interpretation and lives in `services/`.
38. `Optional[object]` stays on a field the API sends as null; the rule bans needless nullability, not its spelling. A response schema's `= None` default is removed only once a probe shows every hit carries the key, because removing it changes what parses.
39. `tests/` follows the rules about how code reads (names, affixes, annotations, `Optional`, comments, no `else` after an exit) and is exempt from the rules about structure a test exists to cross: the layer table, the sideways ban, named constants for fixture data, the single-use helper test and the comparison-in-full preference inside an `assert`.
40. Code identifiers spell normalize with a z, the spelling of `utils/names.py`; prose keeps British spelling.
41. A name drops a qualifier that only restates its type or its enclosing function (`db_report_header` in `build_report` is `report_header`), and keeps one that tells it apart from another value of the same kind in the same scope (`raw_title` beside `title`).
42. A record that `scripts/` builds and `crud/` consumes lives in `utils/`, the lowest module both import; `crud/` modules never import each other. A bulk write takes a list of such records, never a dict of tuples or parallel lists.
43. A gateway function is named for the parsed model it returns: `_response` where the body parses into one `...Response` schema, and the item schema's plural where the body is a list parsed one item at a time (`get_hansard_search_results`).
44. A populate helper that logs and moves below `populate/` drops its log lines and returns the fact each line needs, as a frozen dataclass field or an enum member; every populate caller writes the line with identical text and never re-derives the fact from the inputs.
45. A dict read guarded by `in` or `not in` becomes `.get()` with an `is None` test where the dict's values cannot be `None`; `try`/`except KeyError` is for the raise form, and memoisation keeps `not in`.
46. The `{key}_to_{value}` affix is required of a variable or parameter; a field of a lookups record may instead carry the lookup's own name, because the record's name says lookup and the annotation states the mapping.
47. Ruling 7's `!=` chain is for enum members. Two or more string literals compared against one value are a closed set and become a named frozenset tested with `in`.
48. A result that pairs values by position across parallel lists returns one list of records; parallel lists are a tuple spread over fields.
49. A script's entry function is named for the script (`apply_report_titles` in `scripts/apply_report_titles.py`), never `main` or `run`; the `__main__` guard parses arguments and calls it.
50. A write script's check before the write is `_validate_can_<write verb>_<noun>`; a check after the write, or one that runs both before and after it, gates the commit and is `_validate_can_commit_<noun>`.
51. A script's entry function takes the script's name even when that name begins with `validate_`; the validator shapes govern a function whose caller branches on its result, and a `__main__` guard branches on nothing.
52. Ruling 23 reaches tests/ and a name read through an imported module (`module._name`); a function a test must call with its own session is public for that reason alone.
53. A name a test replaces with `monkeypatch.setattr` by string, and never imports or reads, stays private; rulings 23 and 52 reach only a name the test binds.
54. A line-walking parser's state locals (the current speaker, an in-section flag) are the algorithm, not the declare-then-populate shape.
55. `if key not in cache:` memoisation stays. `if key not in mapping: raise` becomes `try: mapping[key]` with `except KeyError`, raising the same exception with the same message.
56. The `if not updates: return 0` guard at the top of a `set_*_bulk` CRUD method stays: it is the method's empty case, not a pre-check before an attempt.
57. A tuple inside a reference table is data and stays; a positional read of it (`term[2]`) becomes unpacking.
58. A single-use one-liner helper whose name says what the code cannot stays under the name carve-out.
59. A lambda is an expression, not a function defined inside a function.
60. `i` is the name of an `i/total` progress counter.
61. A truthiness check on an `Optional[str]` becomes `is None` only where `""` cannot reach the value; otherwise it stays.
62. A module that runs other stages (`script.py`, `populate/refresh_runs.py`) may call another stage's public session-taking entry point, such as `link_speakers_by_report_ids_and_sitting_ids` or `get_attribution_figures`. Pure logic and private helpers still move down, and no other `populate/` module imports a peer.
63. A 0 or 1 that ruling 15 keeps inline is passed by keyword where it is a function argument, so the parameter name does the work a constant would.
64. Ruling 15's domain-number clause reaches 0. A 0 that names a thing (Parliament 0, the Assembly-only row) keeps its name and is compared through it; only a 0 that means none or empty stays inline.
