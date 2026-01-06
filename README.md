# BibGuard: Anti-Hallucination Bibliography Auditor

**BibGuard** is your final line of defense against AI-generated hallucinations in academic papers. Designed for **human-in-the-loop self-auditing**, it helps you verify that every citation in your LaTeX project is genuine, accurate, and relevant before you submit.

AI coding assistants and writing tools often hallucinate plausible-sounding but non-existent references. **BibGuard** verifies the existence of every entry against real-world databases (arXiv, Google Scholar) and uses advanced LLMs to double-check that the cited paper actually supports your claims.

🚀 You can checkout beta branch for more experimental features.

## 🛡 Why BibGuard?

-   **🚫 Stop Hallucinations**: Instantly flag citations that don't exist or have mismatched metadata.
-   **🔒 Safe & Non-Destructive**: Your original `.bib` file is **never modified**. We generate a detailed report so *you* can make the final decisions.
-   **🧠 Contextual Relevance**: Ensure the paper you cited actually discusses what you claim it does.
-   **⚡ Efficiency Boost**: Drastically reduces the time needed to manually check hundreds of citations.

## 🚀 Features

-   **🔍 Reality Check**: Validates metadata against **arXiv**, **Semantic Scholar**, **DBLP**, **OpenAlex**, **CrossRef**, and **Google Scholar** to catch fake papers.
-   **🤖 AI Relevance Judge**: Uses LLMs to read your citation context and the paper's abstract to score relevance (1-5).
-   **📝 Comprehensive Markdown Report**: Generates a detailed, readable **Markdown report** (`.md`) with prioritized issues for manual verification.
-   **👀 Usage Analysis**: Highlights missing citations (in TeX but not Bib) and unused Bib entries.
-   **👯 Duplicate Detector**: Identifies duplicate entries to keep your Bib file healthy.

## 📦 Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## ⚡ Quick Start

Perform a full self-audit (Reality Check + Relevance + Usage Analysis):

```bash
python main.py --bib paper.bib --tex paper.tex --enable-all
```

**Note:** This will print a summary to the console and save a detailed `report.md` for your review. It also creates a *separate* `_only_used_entry.bib` file for reference, but leaves your original file untouched.

## 🛠 Usage Guide

### 1. The "Reality Check" (Metadata & Existence)
Verify that every paper in your bib file actually exists and has correct metadata.

```bash
python main.py --bib paper.bib --tex paper.tex --check-metadata
```

### 2. The "Relevance Check" (AI Evaluation)
Use an LLM to ensure you haven't cited a real paper for the wrong reason.

**Supported Backends:** `openai`, `anthropic`, `deepseek`, `gemini`, `vllm`, `ollama`

```bash
# Using DeepSeek (Recommended for cost/performance)
export DEEPSEEK_API_KEY="your-key-here"
python main.py --bib paper.bib --tex paper.tex --check-relevance --llm deepseek
```

### 3. Review & Clean
BibGuard focuses on **reporting**. Run the usage check to see what's missing or unused:

```bash
python main.py --bib paper.bib --tex paper.tex --check-usage
```

Review the generated report carefully. If you decide to clean up your bibliography, you can use the generated `paper_only_used_entry.bib` as a reference or a starting point, but always verify the changes manually.

## 📝 Output Report

BibGuard produces a detailed **Markdown report** (`report.md`) containing:
-   **⚠️ Critical Issues (Prioritized)**: Missing entries, duplicates, and metadata mismatches are shown first.
-   **Hallucination Alerts**: Entries that couldn't be found online.
-   **Relevance Scores**: Detailed breakdown of why a citation might be irrelevant, with context.
-   **Metadata Fixes**: Discrepancies between your BibTeX and official records.
-   **Cleanliness Stats**: Unused and missing citations.

## 🧐 Understanding Mismatches

BibGuard is strict, but false positives happen. Here are common scenarios where you might see a "Mismatch" warning that is actually safe to ignore:

1.  **Year Discrepancy (±1 Year)**:
    *   *Scenario*: Your bib says `2023`, but the fetched metadata says `2024`.
    *   *Reason*: Often caused by the delay between a preprint (arXiv) and the official conference/journal publication.
    *   *Action*: Verify which version you intend to cite.

2.  **Author List Variations**:
    *   *Scenario*: "Author mismatch" with low similarity.
    *   *Reason*: Different databases handle large author lists differently (e.g., truncating with `et al.` vs. listing all authors).
    *   *Action*: Check if the primary authors match.

3.  **Non-Academic Sources (Blogs/Websites)**:
    *   *Scenario*: "Confidence: Low" or "Unable to fetch metadata".
    *   *Reason*: Blogs, software documentation, and websites are often not indexed by academic databases like Semantic Scholar or DBLP.
    *   *Action*: Manually verify the URL and title.
