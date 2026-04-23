# TRADE-008: Исправление ложного Ollama fallback

Дата: 2026-04-23

Версия: `0.4.1`

## Инцидент

В Telegram пришло сообщение:

```text
🔴 Quant_Diana: ИИ-решение не получено. Причина: техническая ошибка ИИ-вызова, подробности в логе трейдера.
```

## Что показали логи

Для `Quant_Diana` в 12:33 MSK:

- prompt был нормальный: около 2412 символов;
- `RAG_MARKET`, `RAG_NEWS`, `RAG_TRADES` сформировались;
- несколько Gemini-моделей были пропущены health guard после timeout;
- `gemini-2.5-flash-lite` не ответила за 35 секунд;
- после этого fallback ушел в `ollama/llama3.2`;
- локальный бинарь `ollama` отсутствует, поэтому возникло:

```text
FileNotFoundError: [Errno 2] No such file or directory: 'ollama'
```

Из-за последней ошибки сообщение в Telegram выглядело как технический сбой, хотя реальная причина была в timeout/cooldown Gemini-моделей.

## Причина

В документации уже было зафиксировано, что MOEX-трейдеры должны использовать только Gemini fallback.

Но в `ai_paper_trader.py` оставалось:

```python
include_ollama=True
```

Это добавляло `ollama/llama3.2` в конец fallback-цепочки.

## Исправление

В `ai_paper_trader.py` установлено:

```python
include_ollama=False
```

Теперь MOEX-трейдеры используют только список Gemini-моделей:

1. `gemini-3.1-pro-preview`
2. `gemini-3-flash-preview`
3. `gemini-3.1-flash-lite-preview`
4. `gemini-2.5-pro`
5. `gemini-2.5-flash`
6. `gemini-2.5-flash-lite`

## Проверки

Пройдены:

```bash
/home/user/trading_venv/bin/python -m py_compile ai_paper_trader.py gemini_cli_runner.py ai_cost_guard.py
./tests/run_ai_fallback_smoke.sh
```

`tests/run_ai_fallback_smoke.sh` теперь дополнительно проверяет, что `ai_paper_trader.py` держит `include_ollama=False`.

## Текущий вывод

Сбой `Quant_Diana` был не из-за RAG и не из-за размера prompt.

Основная цепочка причин:

```text
Gemini timeout/cooldown -> последняя попытка в неустановленный ollama -> ложная техническая ошибка
```

После исправления при такой ситуации трейдер должен сообщать более точную причину: timeout или cooldown Gemini-модели, без `FileNotFoundError: ollama`.
