# Database

The SQLModel classes in this folder define every table the pipeline writes. Solid lines are foreign keys. Dotted lines are joins on a shared value with no foreign key behind them. Each box lists the keys and a few columns that show what the table holds. The SQLModel classes have every column, and [docs/data-dictionary.md](../docs/data-dictionary.md) describes the main tables.

```mermaid
erDiagram
    hansardwebsiteresponse }o..o| report : "report_id"
    hansardsittingdateresponse }o..o{ sitting : "sitting_date"
    sitting }o..o{ report : "sitting_date"
    sitting |o--o{ attendance : "sitting_id"
    report |o--o{ speech : "report_id"
    report |o--o{ partyaffiliation : "source_report_id"
    report ||--o{ report_asker : "report_id"
    report ||--o{ report_participant : "report_id"
    report ||--o{ report_question_state : "report_id"
    speaker |o--o{ attendance : "speaker_id"
    speaker |o--o{ speech : "speaker_id"
    speaker ||--o{ partyaffiliation : "speaker_id"
    speaker |o--o{ report_asker : "speaker_id"
    speaker |o--o{ report_participant : "speaker_id"
    person |o--o{ speaker : "person_id"
    person ||--o{ personnamespelling : "person_id"

    hansardwebsiteresponse {
        int id PK
        varchar report_id
        varchar content "raw HTML"
    }

    report {
        int id PK
        varchar report_id UK
        timestamp sitting_date
        varchar title
    }

    speech {
        int id PK
        int report_id FK
        int speaker_id FK
        varchar transcript
    }

    hansardsittingdateresponse {
        int id PK
        varchar sitting_date "d-m-yyyy"
        varchar attendance_list "JSON string"
    }

    sitting {
        int id PK
        varchar sitting_date "d-m-yyyy"
    }

    attendance {
        int id PK
        int sitting_id FK "unique with speaker_id"
        int speaker_id FK
        bool is_present
    }

    speaker {
        int id PK
        int person_id FK
        varchar name
        int parliament_number
    }

    person {
        int id PK
        varchar canonical_name
    }

    personnamespelling {
        int id PK
        int person_id FK
        text spelling
    }

    partyaffiliation {
        int id PK
        int speaker_id FK
        int source_report_id FK "or source_url, exactly one"
        varchar party
    }

    report_asker {
        int id PK
        int report_id FK "unique with ordinal"
        int speaker_id FK "null when the name resolves to no single Membership"
        varchar printed_name "name as printed"
    }

    report_participant {
        int id PK
        int report_id FK "unique with ordinal"
        int speaker_id FK "null when the name resolves to no single Membership"
        participantrole role
    }

    report_question_state {
        int id PK
        int report_id FK "unique with state"
        questionstate state
    }

    refresh_run {
        int id PK
        text status "RUNNING, SUCCEEDED, HALTED or FAILED"
    }
```
