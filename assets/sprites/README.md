# Спрайты-замены

Сейчас вся графика рисуется кодом (`reddome/render/art.py`). Если положить сюда PNG с прозрачностью, игра возьмёт его вместо процедурного спрайта.

Имя файла: `{kind}_{side}_{state}_{angle}.png`

| Часть | Значения |
| --- | --- |
| `kind` | `dome`, `solar`, `ice_drill`, `oxy_gen`, `regolith`, `hangar`, `drone`, `guard_rover`, `drill_rotor` |
| `side` | `player`, `vector` |
| `state` | здания: `on`, `off`, `shadow`, `scaffold`; дрон: `idle`, `carry`, `shadow`; ровер: `body`, `turret`, `shadow`; `drill_rotor`: `spin` |
| `angle` | `0` для зданий и теней; у юнитов и ротора `0`–`15` — поворот по 22,5° по часовой, `0` — нос вправо |

Примеры: `hangar_vector_on_0.png`, `guard_rover_player_body_4.png`.

Размеры как у процедурных спрайтов: здание 44 × 44 px, купол 78 × 78, дрон 26 × 26, ровер 34 × 34. Перед добавлением чужой картинки запишите её лицензию и источник в таблицу «Сторонние ресурсы и лицензии» в README.
