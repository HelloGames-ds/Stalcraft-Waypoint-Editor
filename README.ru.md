
# Stalcraft Waypoint Editor

<img wifth="128" height="128" alt="icon" src="https://github.com/HelloGames-ds/Stalcraft-Waypoint-Editor/blob/main/assets/app.ico" />

---

Десктопный редактор вейпоинтов для **Stalcraft** с загрузкой карты по зонам, редактированием маркеров, парсингом изображений в маркеры и поддержкой слоёв.

---

## Скриншоты

<img width="632" height="312" alt="Image" src="https://github.com/user-attachments/assets/1af8c97f-be9f-486a-af7c-c7478d5eebe4" />

<img width="1920" height="1017" alt="Image" src="https://github.com/user-attachments/assets/2f3c2438-d8b4-46f2-9606-9145e15e78a3" />

<img width="1920" height="1017" alt="Image" src="https://github.com/user-attachments/assets/3e49643e-7501-45d2-874e-248d64b5aca0" />

<img width="914" height="849" alt="Image" src="https://github.com/user-attachments/assets/29f151f7-c518-4ce6-8734-3dd3b859ea18" />

---

## Возможности

- Загрузка зон карты из `assets/maps/zone_pack_png`
- Включение только нужных регионов вместо загрузки всей карты сразу
- Загрузка и сохранение `waypoints.cfg`
- Создание, перемещение, удаление, переименование, смена цвета и иконки вейпоинтов
- Парсинг изображений в маркеры (`Mask fill`/`Silhouette contour`/`Detail edges`)
- Предпросмотр сгенерированных маркеров перед парсингом
- Поддержка слоёв с отдельным локальным хранилищем
- Отмена / Повтор действия
- Настройка пути к папке EXBO
- Интерфейс RU / EN
- Базовая кастомизация интерфейса

---

## Требования

- Windows
- Python `3.13` рекомендуется

Установка зависимостей:

```powershell
py -3 -m pip install -r requirements.txt
```

---

## Запуск

### Вариант 1: Запуск готового `.exe`

- Откройте страницу `Releases` репозитория
- Скачайте `Stalcraft-Waypoint-Editor.exe` из ассетов последнего релиза
- Запустите исполняемый файл

### Вариант 2: Запуск из исходного кода

Из корня проекта:

```powershell
py .\PyGUI\main.py
```

---

## Первый запуск

При первом запуске приложение запрашивает:

1. Язык интерфейса
2. Путь к папке `EXBO`

Пример пути:

```text
C:\Users\<YourUser>\AppData\Roaming\EXBO
```

После этого приложение ищет файл:

```text
<EXBO>\runtime\stalcraft\config\waypoints.cfg
```

Локальные файлы приложения хранятся в:

```text
%APPDATA%\Stalcraft-Waypoint-Editor
```

Содержимое:

- `app_config.json`
- `settings.json`
- `ui_config.json`
- `layers.json`
- `backups/`
- `.cache/`

Эти файлы привязаны к текущему пользователю, не хранятся рядом с исполняемым файлом и обычно не должны добавляться в репозиторий.

---

## Горячие клавиши

- `H` — скрыть / показать боковую панель
- `Delete` — удалить выбранные вейпоинты или загруженное изображение
- `Ctrl+S` — сохранить вейпоинты в cfg
- `Ctrl+Z` — отменить действие
- `Ctrl+Y` — повторить действие
- `Ctrl+Shift+Z` — повторить действие

---

## Структура проекта

- `PyGUI/main.py` — точка входа приложения
- `PyGUI/desktop_app.py` — главный класс приложения
- `PyGUI/ui_mixin.py` — построение интерфейса и оформление темой
- `PyGUI/image_mixin.py` — логика парсинга и предпросмотра изображений
- `PyGUI/zone_mixin.py` — загрузка и отображение зон
- `PyGUI/layers_mixin.py` — система слоёв
- `PyGUI/i18n.py` — переводы
- `simplemapper_core.py` — ввод-вывод cfg, поиск ассетов и сканирование карты
- `assets/maps/zone_pack_png` — набор зон в формате PNG
- `assets/waypoint_icons` — иконки вейпоинтов
- `.github/workflows/build-exe.yml` — workflow GitHub Actions для сборки `.exe` под Windows
- `simplemapper_runtime.spec` — spec-файл PyInstaller для упаковки в один файл

---

## Сборка EXE

Репозиторий настроен на сборку автономного `.exe` под Windows через GitHub Actions.

- Отправьте изменения в ветку `main`
- Откройте последний запуск `Build Windows EXE` во вкладке `Actions`
- Скачайте артефакт с `Stalcraft-Waypoint-Editor.exe`

---

## Благодарности

Отдельная благодарность [TeamDima](https://github.com/DeTTK) за оригинальную программу.
