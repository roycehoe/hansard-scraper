import json
from typing import Optional


def get_json_column(value: object) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value)
