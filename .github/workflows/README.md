# Przepływy pracy GitHub Actions

| Plik | Kiedy się uruchamia | Co sprawdza |
|---|---|---|
| `ci.yml` | `push` na `main`, każdy pull request, ręcznie | testy `pytest`, budowa zasobów Tailwind, budowa obrazu Dockera i test dymny działającego kontenera |
