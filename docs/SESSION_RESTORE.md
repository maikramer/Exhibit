# Session restore — comportamento e lição aprendida

Preferência: sidebar **Loading → Restore Last Session** (`restore-session`, default `true`).
Lista persistida: GSettings `session-files` (paths absolutos).

## Fluxo

```
startup (sem arquivo CLI)
  → LoadMixin._restore_session_files()
  → session_paths_to_restore(enabled, stored)   # session_files.py
  → _open_model_paths(paths)                    # fila sequencial
       load_file(primeiro)
       _pending_open_paths = resto
  → on_file_opened / on_file_not_opened
       → _persist_session_files()               # só se fila vazia e sem warm-load
       → _advance_open_queue()                  # próximo new_tab=True
close / open completo
  → _persist_session_files()                    # LifecycleMixin.on_close_request também
```

Helpers sem GTK: `src/session_files.py` (`collect_session_paths`, `existing_session`, `session_paths_to_restore`).
Toggle off limpa `session-files` (`LifecycleMixin.on_restore_session_toggled`).

## Por que fila sequencial (não paralelo)

Warm-load (`_start_warm_load`) **seleciona** a página da aba alvo para o `GtkGLArea` mapear e o F3D `create_external` ter contexto GL.

Bug antigo: `_open_model_paths` chamava `load_file` em loop para todos os paths. Cada warm-load selecionava a próxima aba → só a **última** ficava mapped/realized. Abas anteriores:

1. ficavam eternamente em “Loading…” (engine nunca inicializa);
2. tinham `filepath` ainda vazio;
3. `_persist_session_files` (chamado em cada `on_file_opened`) gravava só abas já carregadas → **truncava `session-files` no meio do próprio restore** (ex.: 2 abas → 1 path salvo).

Sintoma típico: Recent cheio, `session-files` com 1 item, restore abre 1 modelo.

## Regras que não podem regredir

1. `_open_model_paths` inicia **só** o primeiro `load_file`; resto em `_pending_open_paths`.
2. `_advance_open_queue` roda em **sucesso e falha** (`on_file_opened` + `on_file_not_opened`).
3. `_persist_session_files` **não grava** se `_pending_open_paths` não-vazio ou se alguma aba tem `_warm_load_holder`.
4. CLI / `HANDLES_OPEN` com `startup_filepath` **não** chama restore (comportamento intencional).

## Testes

Guia geral da suite: [TESTING.md](TESTING.md).

| Arquivo | Cobertura |
|---------|-----------|
| `tests/test_session_files.py` | collect / existing / enable gate |
| `tests/test_session_restore_queue.py` | fila, ordem, new_tab, anti-truncate mid-restore, skip persist com warm-load, AST “sem for/while load_file” |

## Arquivos-chave

| Arquivo | Papel |
|---------|--------|
| `src/window_load.py` | `_open_model_paths`, `_advance_open_queue`, restore/persist |
| `src/session_files.py` | helpers GSettings-friendly |
| `src/window_lifecycle.py` | toggle + persist no close |
| `src/window.py` | `_pending_open_paths = []` no `__init__`; restore se sem CLI file |
| `data/io.github.nokse22.Exhibit.gschema.xml` | `session-files`, `restore-session` |
