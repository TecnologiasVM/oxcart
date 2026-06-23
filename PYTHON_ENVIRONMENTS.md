# Python Virtual Environments - Oxcart RAG Project

## Overview
This project now has two Python virtual environments configured with different Python versions.

---

## Environment 1: `.venv-clean` (Original)
**Python Version:** 3.10.11
**PyTorch:** 2.1.0+cu118
**CUDA:** 11.8
**Total Packages:** 253

### Activation
```bash
.venv-clean\Scripts\activate
```

### Key Packages
- PyTorch 2.1.0 with CUDA 11.8
- Transformers 4.47.0
- Timm 0.5.4
- Weaviate Client 4.16.9
- LangChain ecosystem
- Gradio 5.43.1
- Jupyter full stack
- vLLM support (vllm_mbart 0.1)
- LLMStudio 1.0.6

### Jupyter Kernel
- Kernel Name: `python3`
- Display Name: Default Python 3

### Use Cases
- Production environment
- Dolphin parser (document parsing)
- Legacy compatibility
- All features fully tested

---

## Environment 2: `venv` (New - Python 3.13)
**Python Version:** 3.13.0
**PyTorch:** 2.6.0+cu118
**CUDA:** 11.8
**GPU:** NVIDIA GeForce RTX 3060
**Total Packages:** ~245 (excluding incompatible packages)

### Activation
```bash
venv\Scripts\activate
```

### Key Packages
- PyTorch 2.6.0 with CUDA 11.8 ✓
- Transformers 4.47.0 ✓
- Timm 1.0.20 ✓
- Weaviate Client 4.16.9 ✓
- LangChain ecosystem ✓
- Gradio 5.43.1 ✓
- Jupyter full stack ✓
- Tiktoken 0.12.0 (upgraded from 0.7.0)

### Jupyter Kernel
- Kernel Name: `venv-py313`
- Display Name: "Python 3.13 (venv)"
- Location: `C:\Users\VM-SERVER\AppData\Roaming\jupyter\kernels\venv-py313`

### Notable Differences from `.venv-clean`
**Packages NOT Available:**
- `llmstudio` and `llmstudio-core` (no Python 3.13 support yet)
- `vllm_mbart` (excluded)

**Upgraded Packages:**
- Numpy: 1.26.4 → 2.3.3 (required for Python 3.13 compatibility)
- PyTorch: 2.1.0 → 2.6.0 (newer version with Python 3.13 support)
- Tiktoken: 0.7.0 → 0.12.0 (newer prebuilt wheels)
- Various other packages auto-upgraded for compatibility

### Use Cases
- Development with newer Python features
- Testing compatibility with Python 3.13
- Future-proofing
- All core functionality verified working

---

## GPU Verification

Both environments have CUDA support verified:

```bash
# Test GPU access
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

**Expected Output:**
```
CUDA: True
GPU: NVIDIA GeForce RTX 3060
```

---

## Requirements Files

### Backup Files Created
- `requirements-venv-clean-backup.txt` - Full freeze of `.venv-clean` (253 packages)
- `requirements-venv-py313-final2.txt` - Python 3.13 compatible requirements
- `requirements.txt` - Original project requirements

### Installing from Scratch

**For Python 3.10 (`.venv-clean`):**
```bash
py -3.10 -m venv .venv-clean
.venv-clean\Scripts\activate
pip install torch==2.1.0+cu118 torchvision==0.16.0+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements-venv-clean-backup.txt
```

**For Python 3.13 (`venv`):**
```bash
py -3.13 -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install torch==2.6.0+cu118 torchvision==0.21.0+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install timm transformers==4.47.0
pip install tiktoken --only-binary=:all:
pip install -r requirements-venv-py313-final2.txt
python -m ipykernel install --user --name=venv-py313 --display-name="Python 3.13 (venv)"
```

---

## Switching Between Environments

### In Jupyter Notebook
1. Open Jupyter Lab or Notebook
2. Click `Kernel` → `Change Kernel`
3. Select either:
   - `python3` (Python 3.10 - .venv-clean)
   - `Python 3.13 (venv)` (Python 3.13 - venv)

### In Terminal/Command Line
```bash
# Deactivate current environment
deactivate

# Activate desired environment
.venv-clean\Scripts\activate   # For Python 3.10
# OR
venv\Scripts\activate           # For Python 3.13
```

---

## Installed Python Versions on System

- Python 3.7 (legacy)
- Python 3.10.11 ✓ (used by `.venv-clean`)
- Python 3.13.0 ✓ (used by `venv`)
- Python 3.14.0 (not recommended - too new, limited package support)

---

## Notes

1. **CRITICAL:** Always use `.venv-clean` for production work with the Dolphin parser
2. The `venv` environment is for development and testing with newer Python features
3. Both environments preserve CUDA 11.8 support for GPU acceleration
4. All core dependencies (PyTorch, Transformers, Weaviate, LangChain) work in both environments
5. Never install packages in system Python - always use virtual environments

---

## Troubleshooting

### CUDA Not Available
```bash
# Verify PyTorch installation
python -c "import torch; print(torch.__version__)"
# Should show +cu118 suffix

# If not, reinstall:
pip uninstall torch torchvision
pip install torch==2.6.0+cu118 torchvision==0.21.0+cu118 --index-url https://download.pytorch.org/whl/cu118
```

### Package Import Errors
- Check you're in the correct environment: `python --version`
- Verify package is installed: `pip list | grep package-name`
- Reinstall if needed: `pip install --force-reinstall package-name`

### Jupyter Kernel Not Found
```bash
# List kernels
jupyter kernelspec list

# Reinstall kernel
python -m ipykernel install --user --name=venv-py313 --display-name="Python 3.13 (venv)"
```

---

**Last Updated:** 2025-01-22
**Maintained By:** Claude Code Assistant
