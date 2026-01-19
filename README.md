# BibGuard Gamma (Experimental Branch)

> ⚠️ **This is an experimental branch with bleeding-edge features.**

**BibGuard** is a comprehensive LaTeX paper quality assurance tool that validates bibliography entries and checks submission quality.

## 🚀 Quick Start

### 1. Installation

```bash
git clone -b gamma https://github.com/yourusername/bibguard.git
cd bibguard
pip install -r requirements.txt
```

### 2. Initialize Configuration

```bash
python main.py --init
```

This creates `bibguard.yaml`. Edit it to set your `.bib` and `.tex` file paths.

### 3. Run Check

```bash
python main.py
```

**Output** (in `bibguard_output/`):
- `bibliography_report.md` - Bibliography validation results
- `latex_quality_report.md` - Writing quality analysis
- `line_by_line_report.md` - Line-numbered issue list
- `*_only_used.bib` - Clean bibliography (used entries only)

## 📋 Essential Configuration

Edit `bibguard.yaml` to customize checks. Only the most important settings are shown below:

```yaml
files:
  bib: "paper.bib"
  tex: "paper.tex"
  output_dir: "bibguard_output"  # All outputs go here

bibliography:
  check_metadata: true      # Validate against online databases (arXiv, DBLP, etc.)
  check_usage: true         # Find unused/missing entries
  check_duplicates: true    # Detect duplicate entries

submission:
  enabled: true             # Enable LaTeX quality checks
  
  # Check Categories
  caption: true             # Table/figure caption placement
  reference: true           # Cross-reference integrity
  formatting: true          # Citation spacing, blank lines
  equation: true            # Equation punctuation, numbering
  sentence: true            # Sentence length, weak starters
  consistency: true         # Terminology, hyphenation
  ai_artifacts: true        # AI-generated text detection
  anonymization: true       # Double-blind compliance
  citation_quality: true    # Citation age, balance
```

## 🛠 Advanced Usage (LLM)

To use LLMs for citation relevance checking:

```yaml
bibliography:
  check_relevance: true

llm:
  backend: "gemini"  # or: openai, anthropic, deepseek, ollama, vllm
  api_key: ""        # Or use environment variable (e.g., GEMINI_API_KEY)
```
