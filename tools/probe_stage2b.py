"""Prepare fictional A/B data through the installed common API, never SQL edits."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

from zaratustra.commands import Command, Context, execute
from zaratustra.commands.connect import connect_agent
from zaratustra.home import init_home


def prepare(root: Path) -> dict[str, Any]:
    root = root.resolve()
    root.mkdir()
    init_home(root)
    context = Context(home=root.as_posix())

    def run(action: str, **fields: Any) -> dict[str, Any]:
        return execute(
            context,
            Command.model_validate({"action": action, **fields}),
            source_ref="fictional-stage2b-fixture",
        )

    processes = [
        run("process.create", title=name, purpose="Неперсональная проверка skills")["process"]
        for name in ("A", "B")
    ]
    for name in ("A", "B"):
        for title, outcome, next_action in (
            ("Проверка суммы", "Сумма 20 и 30 равна 50. Проверка завершена.", None),
            ("Доступ к макету", "Макет недоступен, печать остановлена.", "Получить учебный макет"),
            (
                "Поля страницы",
                "Поля страницы не проверены.",
                "Проверить поля после получения макета",
            ),
        ):
            run(
                "record.create",
                process=name,
                type_name="episode",
                title=title,
                payload={"situation": title, "outcome": outcome, "next_action": next_action},
                reason="Учебная исходная работа",
            )
    episode = run(
        "record.create",
        process="A",
        type_name="episode",
        title="Обзор скрыл препятствие",
        payload={
            "situation": "В обзоре завершённая проверка суммы заслонила остановку печати.",
            "outcome": "Предложено начинать обзор с незавершённого и препятствий, "
            "открывать основания.",
            "next_action": "По решению владельца улучшить общий навык обзора",
        },
        reason="Учебное основание для изменения методики",
    )
    skill = run(
        "record.create",
        scope="home",
        type_name="skill",
        title="Обзор текущего состояния",
        payload={
            "name": "state-overview",
            "description": "Обзор текущего состояния по журналу процесса",
            "body": "При запросе обзора прочитай эпизоды текущего процесса. "
            "Сначала раздел «Завершено», затем раздел «Осталось». "
            "Указывай только факты из записей. Кратко перечисли выполненное и незавершённое.",
            "dependencies": [
                {"kind": "command", "name": "record.search"},
                {"kind": "command", "name": "record.read"},
            ],
        },
        reason="Общий исходный способ обзора",
        authority_source="Учебный сценарий: общий v1",
    )
    for name in ("A", "B"):
        run(
            "skill.bind",
            process=name,
            slot="overview",
            reference=skill["reference"],
            expected_configuration_revision=0,
            reason="Исходная согласованная версия",
        )
    connect_agent(root, root, agent="pi")
    connect_agent(root, root, agent="codex")
    return {
        "version": version("zaratustra"),
        "home": root.as_posix(),
        "processes": processes,
        "skill": skill["reference"],
        "episode": episode["reference"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("home", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.home), ensure_ascii=False))


if __name__ == "__main__":
    main()
