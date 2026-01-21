# BibGuard: Bibliography & LaTeX Quality Auditor

**BibGuard** is your comprehensive quality assurance tool for academic papers. It validates bibliography entries against real-world databases and checks LaTeX submission quality to catch errors before you submit.

AI coding assistants and writing tools often hallucinate plausible-sounding but non-existent references. **BibGuard** verifies the existence of every entry against multiple databases (arXiv, CrossRef, DBLP, Semantic Scholar, OpenAlex, Google Scholar) and uses advanced LLMs to ensure cited papers actually support your claims.

## 🛡 Why BibGuard?

-   **🚫 Stop Hallucinations**: Instantly flag citations that don't exist or have mismatched metadata
-   **📋 LaTeX Quality Checks**: Detect formatting issues, weak writing patterns, and submission compliance problems
-   **🔒 Safe & Non-Destructive**: Your original files are **never modified** - only detailed reports are generated
-   **🧠 Contextual Relevance**: Ensure cited papers actually discuss what you claim (with LLM)
-   **⚡ Efficiency Boost**: Drastically reduce time needed to manually verify hundreds of citations

## 🚀 Features

### Bibliography Validation
-   **🔍 Multi-Source Verification**: Validates metadata against arXiv, CrossRef, DBLP, Semantic Scholar, OpenAlex, and Google Scholar
-   **🤖 AI Relevance Check**: Uses LLMs to verify citations match their context (optional)
-   **📊 Preprint Detection**: Warns if >50% of references are preprints (arXiv, bioRxiv, etc.)
-   **👀 Usage Analysis**: Highlights missing citations and unused bib entries
-   **👯 Duplicate Detector**: Identifies duplicate entries with fuzzy matching

### LaTeX Quality Checks
-   **📐 Format Validation**: Caption placement, cross-references, citation spacing, equation punctuation
-   **✍️ Writing Quality**: Weak sentence starters, hedging language, redundant phrases
-   **🔤 Consistency**: Spelling variants (US/UK English), hyphenation, terminology
-   **🤖 AI Artifact Detection**: Conversational AI responses, placeholder text, Markdown remnants
-   **🔠 Acronym Validation**: Ensures acronyms are defined before use (smart matching)
-   **🎭 Anonymization**: Checks for identity leaks in double-blind submissions
-   **📅 Citation Age**: Flags references older than 30 years

## 📦 Installation

```bash
git clone git@github.com:thinkwee/BibGuard.git
cd BibGuard
pip install -r requirements.txt
```

## ⚡ Quick Start

### 1. Initialize Configuration

```bash
python main.py --init
```

This creates `config.yaml`. Edit it to set your file paths. You have two modes:

#### Option A: Single File Mode
Best for individual papers.
```yaml
files:
  bib: "paper.bib"
  tex: "paper.tex"
  output_dir: "bibguard_output"
```

#### Option B: Directory Scan Mode
Best for large projects or a collection of papers. BibGuard will recursively search for all `.tex` and `.bib` files.
```yaml
files:
  input_dir: "./my_project_dir"
  output_dir: "bibguard_output"
```

### 2. Run Full Check

```bash
python main.py
```

**Output** (in `bibguard_output/`):
- `bibliography_report.md` - Bibliography validation results
- `latex_quality_report.md` - Writing and formatting issues
- `line_by_line_report.md` - All issues sorted by line number
- `*_only_used.bib` - Clean bibliography (used entries only)

## 🛠 Configuration

Edit `config.yaml` to customize checks:

```yaml
bibliography:
  check_metadata: true        # Validate against online databases (takes time)
  check_usage: true           # Find unused/missing entries
  check_duplicates: true      # Detect duplicate entries
  check_preprint_ratio: true  # Warn if >50% are preprints
  check_relevance: false      # LLM-based relevance check (requires API key)

submission:
  # Format checks
  caption: true               # Table/figure caption placement
  reference: true             # Cross-reference integrity
  formatting: true            # Citation spacing, blank lines
  equation: true              # Equation punctuation, numbering
  
  # Writing quality
  sentence: true              # Weak starters, hedging language
  consistency: true           # Spelling, hyphenation, terminology
  acronym: true               # Acronym definitions (3+ letters)
  
  # Submission compliance
  ai_artifacts: true          # AI-generated text detection
  anonymization: true         # Double-blind compliance
  citation_quality: true      # Old citations (>30 years)
  number: true                # Percentage formatting
```

## 🤖 LLM-Based Relevance Check

To verify citations match their context using AI:

```yaml
bibliography:
  check_relevance: true

llm:
  backend: "gemini"  # Options: gemini, openai, anthropic, deepseek, ollama, vllm
  api_key: ""        # Or use environment variable (e.g., GEMINI_API_KEY)
```

**Supported Backends:**
- **Gemini** (Google): `GEMINI_API_KEY`
- **OpenAI**: `OPENAI_API_KEY`
- **Anthropic**: `ANTHROPIC_API_KEY`
- **DeepSeek**: `DEEPSEEK_API_KEY` (recommended for cost/performance)
- **Ollama**: Local models (no API key needed)
- **vLLM**: Custom endpoint

Then run:
```bash
python main.py
```

## 📝 Understanding Reports

### Bibliography Report
Shows for each entry:
- ✅ **Verified**: Metadata matches online databases
- ⚠️ **Issues**: Mismatches, missing entries, duplicates
- 📊 **Statistics**: Usage, duplicates, preprint ratio

### LaTeX Quality Report
Organized by severity:
- 🔴 **Errors**: Critical issues (e.g., undefined references)
- 🟡 **Warnings**: Important issues (e.g., inconsistent spelling)
- 🔵 **Suggestions**: Style improvements (e.g., weak sentence starters)

### Line-by-Line Report
All LaTeX issues sorted by line number for easy fixing.

## 🧐 Understanding Mismatches

BibGuard is strict, but false positives happen:

1.  **Year Discrepancy (±1 Year)**:
    - *Reason*: Delay between preprint (arXiv) and official publication
    - *Action*: Verify which version you intend to cite

2.  **Author List Variations**:
    - *Reason*: Different databases handle large author lists differently
    - *Action*: Check if primary authors match

3.  **Venue Name Differences**:
    - *Reason*: Abbreviations vs. full names (e.g., "NeurIPS" vs. "Neural Information Processing Systems")
    - *Action*: Both are usually correct

4.  **Non-Academic Sources**:
    - *Reason*: Blogs, documentation not indexed by academic databases
    - *Action*: Manually verify URL and title

## 🔧 Advanced Options

```bash
python main.py --help              # Show all options
python main.py --list-templates    # List conference templates
python main.py --config my.yaml    # Use custom config file
```

## 🤝 Contributing

Contributions welcome! Please open an issue or pull request.

## 🙏 Acknowledgments

BibGuard uses multiple data sources:
- arXiv API
- CrossRef API
- Semantic Scholar API
- DBLP API
- OpenAlex API
- Google Scholar (via scholarly)

---

**Made with ❤️ for researchers who care about their submission**
