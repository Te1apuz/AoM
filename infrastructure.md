# Инфраструктура

## Репозитории

| Роль | Репозиторий | SSH |
|------|-------------|-----|
| Рабочий форк: отсюда бот читает данные, сюда открывает PR | https://github.com/Te1apuz/AoM | `git@github.com:Te1apuz/AoM.git` |
| Оригинал (автор RedCat#1BVV), доступа на запись пока нет | https://github.com/RedCat161/AoM | `git@github.com:RedCat161/AoM.git` |

Пока доступа к оригиналу нет, ветки и pull request'ы делаются в форке.
Когда RedCat даст доступ, PR пойдут в `RedCat161/AoM`.

## Доступ к GitHub

- Ключ: `~/.ssh/id_ed25519` (приватный), `~/.ssh/id_ed25519.pub` (публичный).
- Отпечаток: `SHA256:xCB/Ndmkj2+xjFsTBSG7b7Oyd2xcS/MbglKmnLxrG+E` (ED25519).
- Приватный ключ в репозиторий не коммитить.
- Публичный ключ должен быть добавлен в аккаунт `Te1apuz`:
  GitHub → Settings → SSH and GPG keys → New SSH key.

Проверка доступа:

```sh
ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -T git@github.com
git ls-remote git@github.com:Te1apuz/AoM.git
```

Официальные отпечатки хоста github.com
([docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)):

- ED25519 `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`
- ECDSA `SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM`
- RSA `SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s`

Если ssh пишет `REMOTE HOST IDENTIFICATION HAS CHANGED` с отпечатком
`SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8`, значит в `known_hosts`
лежит старый RSA-ключ GitHub, отозванный в марте 2023. Исправление:

```sh
ssh-keygen -R github.com
ssh-keyscan -t ed25519,rsa,ecdsa github.com >> ~/.ssh/known_hosts
ssh-keygen -lf ~/.ssh/known_hosts | grep github.com   # сверить с отпечатками выше
```

## Данные

- Живая таблица (сейчас главный источник данных о героях):
  https://docs.google.com/spreadsheets/d/18IWMCIs8q2usE4HzB9enjbVJ6C1YLw50
  (короткая ссылка https://goo.su/6EyVuw, описание https://teletype.in/@aom_guides/6Zn8U2gti_7).
- Выгрузка без авторизации:
  `https://docs.google.com/spreadsheets/d/18IWMCIs8q2usE4HzB9enjbVJ6C1YLw50/export?format=xlsx`
- `AoM Артефакты!!!.xlsx` в репозитории — устаревший снимок от 2026-02-21
  (197 героев против 209 в живой таблице на 2026-10-25).
- Картинки таблица берёт по ссылкам
  `https://raw.githubusercontent.com/RedCat161/AoM/main/<папка>/<имя>_200.jpg`.
  Полный размер (1024×1024) лежит по тому же пути без `_200`.
