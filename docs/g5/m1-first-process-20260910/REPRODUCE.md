# Воспроизведение G5 T4

Проверенный candidate: `46718e4da82810e57ba7126c8ec3ef0fc4f57268`.
Source/B: `b1e0853f9b405e2910f2085dae6fd7f6100ba009`.
Review scripts сохранены как исполняемые Python `.py.txt` в evidence; расширение
предотвращает смешение development tests с review artifacts. Они не меняют product.

## Новая изоляция

Создать **новую чистую** review worktree от candidate, с новым свободным именем
ветки. Существующие author/review worktree не переключать и не очищать.
STOP означает halt; STEER прочитать/разрешить. Прочитать candidate AGENTS,
validation.config и CALL. PROBA36; никаких OPORA/re-sync/model gates.
Скопировать только этот review пакет в новую копию из exact review commit.
`verify_candidate.py.txt` ожидает HEAD=candidate до добавления review-коммита.
Из готового review commit можно читать retained evidence без повторного исполнения.

Все следующие команды запускаются из корня **новой** worktree. Имена scratch
папок должны быть свободны, иначе выбрать новые; scripts и runner никогда не
должны перезаписывать прошлые trials. Все свои изменения scripts сохранить отдельно.

```powershell
if (Test-Path -LiteralPath STOP) { throw 'STOP present' }
if (Test-Path -LiteralPath STEER.md) { throw 'Read and resolve STEER' }
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '_scratch/g5-environment/uv-cache')
uv sync --locked
if (Test-Path '_scratch/g5-native-deliver-01') { throw 'Choose NEW basetemp' }
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/g5-native-deliver-01'
uv run --locked python -m tools.check --deliver
uv run --locked python -m tools.probe_first_process --output _scratch/g5-source-01
uv run --locked python docs/g5/m1-first-process-20260910/evidence/verify_candidate.py.txt
uv run --locked python docs/g5/m1-first-process-20260910/evidence/refute.py.txt _scratch/g5-refutation-02
uv run --locked python docs/g5/m1-first-process-20260910/evidence/retained_replay.py.txt
```

Сохранять stdout/stderr и exit каждого запуска в новый evidence/log, как в
`receipt.json`. После pytest проверить actual directory и test children внутри
именно своей `_scratch`, `git check-ignore` и отсутствие links/junctions.
Runtime/cache доступ при managed sandbox может требовать штатного escalation.
Required-tool STOP не обходится. Первая sandbox uv-попытка и Git index denial
оригинальной G5 сохранены; новых попыток в старые каталоги не делать.

`retained_replay.py.txt` содержит read-only проверку author checkout по его прежнему
пути, отдельную от повторов wheel/snapshots. Если в будущей сессии author checkout
уже недоступен/изменён, это историческое ограничение пометить явно и сравнить CALL
через candidate Git blob; не восстанавливать/переключать чужую копию ради проверки.
Тот script ожидает новый `_scratch/g5-retained-01` и проверенный basetemp выше.
Точные headers/Git HEAD/provenance в replay будут относиться к новой физической
сессии: обновить только source_ref собственного review host, не product files.

## Что должно наблюдаться

- Native Deliver:217 tests,8 contracts и все стадии PASS. Отдельные tools не
  заменяют этот required run.
- Exact source и retained wheel: release, Results на11/18, cancel_work на19,
  два Results, cancelled continuation без completion_id.
- Собственный refutation host: discard с нестандартными inspection bytes;
  семантически тот же JSON с другим digest отвергается. Incomplete/missing/
  incompatible/closed/unknown/refused authority не меняют footprint.
- Все семь capability names; выбранный контекст требует отдельного caller,
  metadata scope не показывает hidden Result header, inherited exact refs
  сохраняют также отрицательные наблюдения. Stale/revoked/foreign path не раскрывают
  данные. Два экземпляра первого lot не меняют состояние друг друга; это не T5.
- Авторские snapshots до двух Results: restore в NEW пути, затем open_work даёт
  исходные context bytes, apply_mutation с новыми path-bound confirmations даёт
  прежний fingerprint/revision. UUID/timestamps новых сценариев будут отличаться.

`refute-attempt-01.py.txt` сохранён для объяснения неудачной первой проверки.
Он ожидает неправильный code `invalid_work` у cancelled Work, тогда как public
Core правильно возвращает `permission_denied`. Для рабочего повторения используется
`refute.py.txt`. Обе исходные runtime папки сохранены в отдельных ZIP; первая
не является базой второго прогона.

## Проверка архивов и G5-F01

`evidence/manifest.json` перечисляет byte sizes/SHA256 собственных review files,
исключая самого себя. `*-manifest.json` для ZIP содержит archive SHA256, hashes
всех decompressed files и complete directory inventory. Использовать штатный
`tools.probe_m1.restore_snapshot(archive, NEW_target, manifest)`; target должен
быть внутри новой review `_scratch`. Нельзя править DB/state Markdown для replay.
Для проверки сохранённых snapshots достаточно своего разрешённого fictional
host: prepare_authorization → authorize_local → open_work/apply_mutation.

При повторении первоначального byte-audit ожидаются **два записанных расхождения**:
одно реальное G5-F01 и одно исправленное допущение самого audit. Follow-up
`retained_replay.py.txt` устанавливает их точную диспозицию:

1. Committed CALL LF hash `52c6a45de5b86b4710fd1df0155b0393b389bf33761758478463fe549d07ab4f`,
   11464 bytes. Авторский manifest ожидает CRLF hash
   `5c0b4674c59b67c9e80e8e6f7ee6a89101d4cd3ef61863b0edc672b2ee8ff054`,11565 bytes.
   LF→CRLF даёт именно эти bytes/hash. Это P3 к упаковке, сохранённый без правки
   candidate evidence; не буквальный PASS всей outer manifest.
2. Retained `source.diff` имеет scope, явно записанный в
   `docs/m1-first-process/evidence/package-t4.py.txt`. Scoped diff совпадает.
   Первоначальный audit ошибочно сравнил с unrestricted diff. Полные независимые
   diffs также сохранены в G5 evidence.

## Baseline B и дальнейшая граница

Source B остаётся `b1e0853f9b405e2910f2085dae6fd7f6100ba009`, даже после появления
review commit. Сопоставление B→будущий T5 выполняется по полным Git trees/diff
Core и process_packs, всей установке/lock/host/rules, exact inputs/outputs обоих
сценариев. Одно совпадение hashes не доказывает Process independence. Один host
с обоими пакетами/одна установка и общий контракт, отдельные workspace/revisions.
P§30 «без изменения основной семантики Core» и P§40 «без изменения Core» сохраняются.
Этот документ не разрешает запуск T5 и не объявляет Proof C/T6/T7/M1 готовыми.

END_OF_FILE: docs/g5/m1-first-process-20260910/REPRODUCE.md
