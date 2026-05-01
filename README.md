# AI-Powered Data Extraction Tool for MSK Clinical Practice Guidelines Review

## Overview

This repository contains the source code, prompt version history, and validation 
data for a custom AI-powered data extraction tool developed to support a systematic 
review of sex and gender considerations in musculoskeletal (MSK) clinical practice 
guidelines (CPGs).

The tool is designed to function as a semi-automated second reviewer, extracting 
structured and qualitative data fields from CPG documents and producing outputs for 
human review and adjudication. It was built using the Streamlit framework and the 
Anthropic API (Claude Sonnet 4.6).

This repository accompanies two pre-registered studies:

- **Parent review** — Sex and gender considerations in MSK clinical practice 
  guidelines (Australia, UK, US, WHO)  
  OSF registration: https://doi.org/10.17605/OSF.IO/2ZEQM

- **Methodological study** — Development and validation of the AI extraction tool  
  OSF registration: https://osf.io/sxnu4/overview

---

## Repository Structure
/app/           Streamlit application source code
/prompts/       All prompt versions, version-controlled throughout development
/docs/          Protocol documents and methodology notes
/data/          Validation study outputs (AI extractions and human gold st---

## How to Use This Tool

### Option 1 — Browser access (no installation required)

A live deployment of the finalised tool is available at:  
🔗 *[Streamlit Community Cloud URL — to be added upon deployment]*

### Option 2 — Run locally

Requirements: Python 3.9+, an Anthropic API key

```bash
git clone https://github.com/DrAlessInMotion/msk-cpg-extraction-tool.git
cd msk-cpg-extraction-tool
pip install -r requirements.txt
streamlit run app/app.py
```

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

---

## Prompt Version History

All versions of the extraction prompt are stored in `/prompts/` with version numbers 
and dated commit messages documenting what changed between iterations and why. This 
version history is a TRIPOD-LLM reporting requirement (item 9a).

---

## Reporting Standards

Development and evaluation of this tool follows the TRIPOD-LLM framework:

> Gallifant J, et al. The TRIPOD-LLM reporting guideline for studies using large language models. *Nature Medicine*, 2025; 31(1): 60–69.

---

## Citation

*To be added upon publication.*

---

## Licence

MIT License. See `LICENSE` for details.

---

## Contact

Alessandra Marcelo — The George Institute for Global Health / UNSW
