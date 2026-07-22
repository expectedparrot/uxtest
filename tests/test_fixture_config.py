from __future__ import annotations

import json

import pytest

from uxtest.cli import main
from uxtest.store import Store, read_yaml


def test_fixture_can_be_built_incrementally_and_shown(tmp_path, capsys):
    store = Store.init(tmp_path)

    main(
        [
            "--store",
            str(store.root),
            "fixture",
            "new",
            "homepage",
            "--url-template",
            "https://example.test/?variant={variant}",
            "--task",
            "Find product documentation.",
            "--success-criteria",
            "Documentation is opened.",
            "--persona",
            "seniors",
            "--variant",
            "clear",
            "--driver",
            "heuristic",
        ]
    )
    assert "fixtures/homepage/fixture.yaml" in capsys.readouterr().out

    main(["--store", str(store.root), "fixture", "persona", "homepage", "mobile-first"])
    capsys.readouterr()
    main(["--store", str(store.root), "fixture", "variant", "homepage", "flawed", "--device", "iphone"])
    capsys.readouterr()
    main(["--store", str(store.root), "fixture", "set", "homepage", "max_steps", "6"])
    capsys.readouterr()
    main(["--store", str(store.root), "fixture", "set", "homepage", "overrides", '{"model":"gpt-4o"}', "--json-value"])
    capsys.readouterr()

    plan = read_yaml(store.fixtures_path / "homepage" / "fixture.yaml")
    assert plan["personas"] == ["seniors", "mobile-first"]
    assert plan["variants"] == [{"name": "clear"}, {"name": "flawed", "device": "iphone"}]
    assert plan["max_steps"] == 6
    assert plan["overrides"] == {"model": "gpt-4o"}

    main(["--store", str(store.root), "fixture", "validate", "homepage"])
    validation = json.loads(capsys.readouterr().out)
    assert validation["data"]["valid"] is True
    main(["--store", str(store.root), "fixture", "show", "homepage", "--json"])
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["command"] == "fixture show"
    shown = envelope["data"]
    assert shown["task"] == "Find product documentation."


def test_fixture_new_imports_json_and_normalizes_id(tmp_path, capsys):
    store = Store.init(tmp_path)
    source = tmp_path / "plan.json"
    source.write_text(
        json.dumps(
            {
                "id": "ignored-source-id",
                "name": "Imported Plan",
                "url_template": "https://example.test/{variant}",
                "task": "Choose a useful next step.",
                "personas": ["seniors"],
                "variants": [{"name": "a"}, {"name": "b"}],
            }
        ),
        encoding="utf-8",
    )

    main(["--store", str(store.root), "fixture", "new", "imported", "--from-json", str(source)])
    capsys.readouterr()
    plan = read_yaml(store.fixtures_path / "imported" / "fixture.yaml")
    assert plan["id"] == "imported"
    assert plan["name"] == "Imported Plan"
    assert plan["driver"] == "edsl"
    assert plan["variants"] == [{"name": "a"}, {"name": "b"}]


def test_fixture_register_copies_directory_companions(tmp_path, capsys):
    store = Store.init(tmp_path)
    source = tmp_path / "source-fixture"
    source.mkdir()
    (source / "fixture.yaml").write_text(
        "id: source\nurl_template: https://example.test/\ntask: Explore.\nvariants:\n  - name: default\n",
        encoding="utf-8",
    )
    (source / "server.py").write_text("print('server')\n", encoding="utf-8")
    (source / "alternate.yaml").write_text(
        "id: alternate\nurl_template: https://alternate.test/\ntask: Compare.\nvariants:\n  - name: other\n",
        encoding="utf-8",
    )

    main(["--store", str(store.root), "fixture", "register", str(source), "--name", "registered"])
    capsys.readouterr()
    assert (store.fixtures_path / "registered" / "server.py").is_file()
    assert read_yaml(store.fixtures_path / "registered" / "fixture.yaml")["id"] == "registered"

    main(["--store", str(store.root), "fixture", "list", "--json"])
    listed = json.loads(capsys.readouterr().out)["data"]
    assert listed[0]["id"] == "registered"

    main(
        [
            "--store",
            str(store.root),
            "fixture",
            "register",
            str(source),
            "--name",
            "alternate",
            "--plan",
            "alternate.yaml",
        ]
    )
    capsys.readouterr()
    alternate = read_yaml(store.fixtures_path / "alternate" / "fixture.yaml")
    assert alternate["url_template"] == "https://alternate.test/"


def test_fixture_validate_reports_all_basic_errors(tmp_path, capsys):
    store = Store.init(tmp_path)
    main(["--store", str(store.root), "fixture", "new", "invalid"])
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        main(["--store", str(store.root), "fixture", "validate", "invalid"])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "task must be a non-empty string" in output.out
    assert "url_template is required" in output.out
