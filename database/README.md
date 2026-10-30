# Database

The SQLModel classes in this folder define every table the pipeline writes. Solid lines are foreign keys. Dotted lines are joins on a shared value with no foreign key behind them. Each box lists the keys and the columns most queries need. `sitting` and `hansardsittingdateresponse` hold about 60 more columns copied from the API, listed in [docs/data-dictionary.md](../docs/data-dictionary.md).

```mermaid
erDiagram
    hansardwebsiteresponse }o..o| report : "report_id"
    hansardsittingdateresponse }o..o{ sitting : "sitting_date"
    sitting }o..o{ report : "sitting_date"
    sitting |o--o{ attendance : "sitting_id"
    report |o--o{ speech : "report_id"
    report |o--o{ partyaffiliation : "source_report_id"
    speaker |o--o{ attendance : "speaker_id"
    speaker |o--o{ speech : "speaker_id"
    speaker ||--o{ partyaffiliation : "speaker_id"
    person |o--o{ speaker : "person_id"

    hansardwebsiteresponse {
        int id PK
        varchar report_id
        varchar report_type
        varchar report_version "sprs2 or sprs3"
        varchar parliament_number
        varchar sitting_date
        varchar title
        varchar html_file_name
        varchar content "raw HTML"
    }

    report {
        int id PK
        varchar report_id UK
        int parliament_number
        int volume_number
        int sitting_number
        timestamp sitting_date
        int speech_number
        varchar report_type
        varchar report_version
        varchar original_title
        varchar title
        varchar subtitle
        varchar content "raw HTML"
        varchar markdown_content
        tsvector title_tsv "generated from title"
    }

    speech {
        int id PK
        int report_id FK
        int speaker_id FK
        int ordinal
        varchar speaker "name as printed"
        varchar transcript
        speechkind kind
        timestamp sitting_date "copied from report"
        varchar report_type "copied from report"
        tsvector transcript_tsv "generated from transcript"
    }

    hansardsittingdateresponse {
        int id PK
        int parlement_no
        int session_no
        int volume_no
        int sitting_no
        varchar sitting_date "d-m-yyyy"
        varchar html_full_content "before 10 Sep 2012 only"
        varchar attendance_list "JSON string"
    }

    sitting {
        int id PK
        int parlement_no
        int session_no
        int volume_no
        int sitting_no
        varchar sitting_date "d-m-yyyy"
        varchar html_full_content
        varchar markdown_content
        varchar attendance_list "JSON string"
        varchar sections "JSON string"
        varchar annexures "JSON string"
        varchar vernaculars "JSON string"
        varchar a2b "JSON string"
    }

    attendance {
        int id PK
        int sitting_id FK "unique with speaker_id"
        int speaker_id FK
        varchar speaker_name
        bool is_present
        varchar location_name
    }

    speaker {
        int id PK
        int person_id FK
        varchar name
        varchar party "ballot party"
        int parliament_number
        bool is_legislative_assembly
        bool is_member "false for heads of state"
        varchar comments
    }

    person {
        int id PK
        varchar canonical_name
        varchar basis
        varchar notes
    }

    partyaffiliation {
        int id PK
        int speaker_id FK
        int source_report_id FK "or source_url, exactly one"
        varchar source_url
        varchar party
        date started_on
        dateprecision started_on_precision "DAY or MONTH"
        bool is_started_on_upper_bound
        varchar event
    }

    refresh_run {
        int id PK
        text status "RUNNING, SUCCEEDED, HALTED or FAILED"
        timestamptz started_at
        timestamptz finished_at
        int reports_added
        int speeches_added
        int speeches_linked
        jsonb figures
        text halt_reason
        text failure_reason
    }
```
