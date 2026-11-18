# Third-party notices

Oxcart is released under the MIT License (see [LICENSE](LICENSE)). It includes code from the project below, which
keeps its own copyright notice.

## Dolphin (document parser)

- Source: <https://github.com/bytedance/Dolphin>
- Copyright 2025 ByteDance Ltd. and/or its affiliates
- License: MIT. The original license file is kept unchanged at [licenses/Dolphin-MIT.txt](licenses/Dolphin-MIT.txt).

This repository began as a copy of Dolphin, taken while Dolphin was published under the MIT License (its commits
here run from 2025-05-26 to 2025-07-10 and are kept in the history with their authors). The Dolphin project later
changed its own license; that change does not apply to the copy used here.

Files that come from Dolphin, unchanged:

- `chat.py`, `demo_page.py`
- `utils/` (`markdown_utils.py`, `model.py`, `processor.py`, `utils.py`)
- `config/Dolphin.yaml`
- `deployment/` (the vLLM and TensorRT-LLM serving examples)
- `pyproject.toml`, `.pre-commit-config.yaml`, `README_CN.md`

Files that started in Dolphin and were changed for Oxcart: `README.md`, `requirements.txt`, `.gitignore`.
