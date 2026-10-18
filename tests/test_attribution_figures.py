from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.attribution_text_share as attribution_text_share
from tests.attribution_seed import seed_attribution_rows

_EXPECTED_FIGURES_FILE = Path(__file__).parent / "fixtures" / "attribution" / "figures.txt"


def test_script_output_is_unchanged(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed_attribution_rows(scratch_session)
    monkeypatch.setattr(attribution_text_share, "engine", scratch_engine)
    output_path = tmp_path / "figures.txt"
    attribution_text_share.main(output_path)
    assert output_path.read_text(encoding="utf-8") == _EXPECTED_FIGURES_FILE.read_text(encoding="utf-8")
