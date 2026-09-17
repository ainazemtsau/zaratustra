"""Create a new fictional Home for the ordinary installed Pi web-inbox walkthrough."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib import metadata
from pathlib import Path
from typing import Any
from uuid import UUID

from zaratustra.commands import Command, Context, execute
from zaratustra.commands.connect import connect_agent
from zaratustra.home import init_home
from zaratustra.journal import Scope, Store
from zaratustra.web_exchange import Exchange, Origin


def prepare(root: Path, *, setup_only: bool = False) -> dict[str, Any]:
    root = root.resolve()
    scratch = Path(__file__).resolve().parents[1] / "_scratch"
    if not root.is_relative_to(scratch) or root.exists():
        raise ValueError("Choose a NEW directory inside this checkout's _scratch")
    root.mkdir(parents=True)
    init_home(root)
    context = Context(home=root.as_posix())

    def run(action: str, **fields: Any) -> dict[str, Any]:
        return execute(
            context,
            Command.model_validate({"action": action, **fields}),
            source_ref="fictional-stage3-walkthrough",
        )

    row = run(
        "process.create",
        title="Учебный Development",
        purpose="Неперсональный показ входящих запросов",
    )["process"]
    context = Context(home=root.as_posix(), workspace=row["location"], process_id=UUID(row["id"]))
    if setup_only:
        connect_agent(root, root, agent="pi")
        return {
            "version": metadata.version("zaratustra"),
            "home": root.as_posix(),
            "process": row["id"],
            "scenario": "first setup; no channel, packet or request prepared",
        }
    run("web.configure", payload={"repository": "fictional-owner/private-home"})
    current = run(
        "record.create",
        type_name="document",
        title="Текущее состояние",
        payload={
            "text": "В работе ничего нет. Идеи можно сохранять для последующего выбора. "
            "Разработку не начинали."
        },
        reason="Fictional current state",
    )
    packet = run(
        "web.prepare",
        payload={
            "question": "Обсудить удобство переключения моделей",
            "references": [current["reference"]],
        },
    )
    exchange = Exchange(
        Store(
            Path(row["location"]),
            Scope(kind="process", id=UUID(row["id"])),
            "fictional-stage3-web-request",
        ),
        {"title": row["name"]},
    )
    original = chr(10).join(
        [
            '{ "broken_json": да, дальше обычный текст',
            "Процесс: Учебный Development.",
            "Поручение владельца: сохрани идею переключения моделей в бэклог как предложение; "
            "выполнять её пока не надо.",
            "Предложение из обсуждения: перед длинным исследованием выбирать модель "
            "по задаче и доступному лимиту.",
            "Отдельно сохрани учебный отчёт «Сравнение моделей.md». "
            "Его файл обязателен, но ещё не передан.",
            "Отчёт и предложение не являются утверждённым выбором модели или подписки.",
            "Обсуждали по подготовленному контексту: "
            + json.dumps(packet["reference"], ensure_ascii=False),
        ]
    )
    raw = original.encode("utf-8")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
    captured = exchange.capture(
        Origin(
            repository="fictional-owner/private-home",
            branch="main",
            path=exchange.prefix + "/requests/fictional-discussion.md",
            blob=blob,
            commit="a" * 40,
        ),
        raw,
    )
    connect_agent(root, root, agent="pi")
    return {
        "version": metadata.version("zaratustra"),
        "home": root.as_posix(),
        "process": row["id"],
        "request": captured["reference"],
        "context": packet["reference"],
        "transport": "fixture captured locally, not a real ChatGPT/GitHub transfer",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("home", type=Path)
    parser.add_argument("--setup-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.home, setup_only=args.setup_only), ensure_ascii=False))


if __name__ == "__main__":
    main()
