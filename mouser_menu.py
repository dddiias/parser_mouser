import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv, find_dotenv

from mouser_cli import (
    _get_api_key,
    _is_valid_pn,
    fetch_by_partnumber,
    fetch_by_keyword,
    extract_first_part,
    transform_strict,
    write_csv,
    print_table,
)

load_dotenv(find_dotenv(), override=False)


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nВыход.")
        sys.exit(0)


def _split_pns(s: str) -> List[str]:
    parts = [t.strip() for t in s.replace(",", " ").split() if t.strip()]
    return parts


def _save_json(rows: List[Dict[str, Any]], out_path: str) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _save_raw(data: Dict[str, Any], save_dir: Path, name: str) -> None:
    save_dir.mkdir(parents=True, exist_ok=True)
    safe = name.replace("/", "_")
    with (save_dir / f"{safe}.json").open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _lookup_one(pn: str, api_key: str, retries: int = 3, timeout: int = 20,
                save_raw_dir: Path | None = None) -> dict | None:
    if not _is_valid_pn(pn):
        print(f"  ⚠️  Пропускаю некорректный ввод: {pn!r}")
        return None

    try:
        data_pn = fetch_by_partnumber(pn, api_key, retries, timeout)
    except Exception as e:
        print(f"  ❌ Ошибка запроса (partnumber): {e}")
        return None

    part = extract_first_part(data_pn)
    used_keyword = False

    if not part:
        try:
            data_kw = fetch_by_keyword(pn, api_key, retries, timeout)
        except Exception as e:
            print(f"  ❌ Ошибка запроса (keyword): {e}")
            return None
        part = extract_first_part(data_kw)
        used_keyword = True
        if save_raw_dir:
            _save_raw(data_kw, save_raw_dir, f"{pn}__keyword")
    else:
        if save_raw_dir:
            _save_raw(data_pn, save_raw_dir, f"{pn}__partnumber")

    if not part:
        print("  ⚠️  Ничего не найдено.")
        return None

    row = transform_strict(part)
    print("  ✓ Готово.")
    return row


def main():
    try:
        api_key = _get_api_key()
    except SystemExit:
        print("Создайте .env с MOUSER_API_KEY=... (или экспортируйте переменную окружения) и запустите снова.")
        return

    results_map: Dict[str, Dict[str, Any]] = {}
    save_raw_dir: Path | None = None

    while True:
        print("\n============== Mouser Parser (интерактивный режим) ==============")
        print("1) Ввести парт-номер(а) и показать таблицу")
        print("2) Сохранить последние результаты в CSV")
        print("3) Сохранить последние результаты в JSON")
        print("4) Указать папку для сохранения сырых ответов API (RAW)")
        print("0) Выход")
        choice = _ask("\nВыберите пункт меню: ")

        if choice == "0":
            print("Пока! 👋")
            break

        elif choice == "1":
            raw = _ask("Введите один или несколько парт-номеров (через пробел или запятую): ")
            pns = _split_pns(raw)
            if not pns:
                print("  ⚠️  Ничего не введено.")
                continue

            results = []
            for pn in pns:
                print(f"  → Ищу: {pn} ...")
                row = _lookup_one(pn, api_key, retries=3, timeout=20, save_raw_dir=save_raw_dir)
                if row:
                    key = pn.strip().lower()
                    results_map[key] = row

            if results_map:
                print("\nРезультаты:")
                print_table(list(results_map.values()))
            else:
                print("  ⚠️  Пусто — нет валидных результатов.")

        elif choice == "2":
            if not results_map:
                print("  ⚠️  Нет данных для сохранения. Сначала выполните поиск (пункт 1).")
                continue
            out = _ask("Имя файла CSV (по умолчанию: mouser_results.csv): ")
            out = out or "mouser_results.csv"
            try:
                write_csv(list(results_map.values()), out)
                print(f"  ✓ CSV сохранён → {out}")
            except Exception as e:
                print(f"  ❌ Ошибка при сохранении CSV: {e}")

        elif choice == "3":
            if not results_map:
                print("  ⚠️  Нет данных для сохранения. Сначала выполните поиск (пункт 1).")
                continue
            out = _ask("Имя файла JSON (по умолчанию: mouser_results.json): ")
            out = out or "mouser_results.json"
            try:
                _save_json(list(results_map.values()), out)
                print(f"  ✓ JSON сохранён → {out}")
            except Exception as e:
                print(f"  ❌ Ошибка при сохранении JSON: {e}")

        elif choice == "4":
            path = _ask("Укажи путь к папке для RAW (пусто — отключить): ")
            if not path:
                save_raw_dir = None
                print("  RAW сохранение отключено.")
            else:
                p = Path(path)
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    save_raw_dir = p
                    print(f"  ✓ RAW будут сохраняться в: {p}")
                except Exception as e:
                    print(f"  ❌ Не удалось создать папку: {e}")
        else:
            print("  ⚠️  Неверный выбор. Попробуйте ещё раз.")


if __name__ == "__main__":
    main()
