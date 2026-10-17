import json
from pathlib import Path

from ml.g0_extractor import features_for_unit, find_units
from ml.jm1_facts import METRIC_COLUMNS

REPOSITORY_ROOT = Path(__file__).parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT / "backend" / "app" / "ml" / "artifacts" / "feature_schema.json"
)
FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "g0"
    / "python_if_and"
    / "source.py"
)
EXPECTED_FEATURES = [
    "loc",
    "v(g)",
    "uniq_Op",
    "uniq_Opnd",
    "total_Op",
    "total_Opnd",
    "n",
    "v",
    "l",
    "d",
    "i",
    "b",
]


def test_feature_schema_matches_extractor_and_jm1_columns() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    features = schema["features"]
    names = [feature["name"] for feature in features]

    assert schema["schema_status"] == "draft"
    assert schema["dataset"] == "JM1"
    assert names == EXPECTED_FEATURES
    assert len(names) == 12
    assert len(set(names)) == 12
    assert [feature["order"] for feature in features] == list(range(1, 13))

    source = FIXTURE_PATH.read_text(encoding="utf-8")
    unit = next(
        unit for unit in find_units(source, FIXTURE_PATH) if unit.name == "decide"
    )
    feature_vector = features_for_unit(source, unit)
    assert all(name in feature_vector for name in names)

    jm1_columns = set(METRIC_COLUMNS)
    for feature in features:
        source_column = feature["source_dataset_column"]
        if source_column not in jm1_columns:
            assert source_column.startswith("derived from ")
            assert "=" in feature["definition"]
