# S2S (Syllabus-to-Ship)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Powered by SerpApi](https://img.shields.io/badge/Powered%20by-SerpApi-orange.svg)](https://serpapi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> An Open-Mesh AI engine that transforms university course syllabi across all academic streams into live, real-world work opportunities sourced in real time via SerpApi.

---

## 🌟 Overview

Students across university disciplines—**Commerce, Arts, Sciences, and Engineering**—frequently spend years memorizing abstract theory for exams, graduating with empty portfolios and zero industry exposure.

**S2S (Syllabus-to-Ship)** reverses this disconnect:
1. **Upload Syllabus:** Students input their current semester syllabus or chapter topics.
2. **Deconstruct Competencies:** S2S extracts theoretical topics and translates them into operational market skills.
3. **Open-Mesh Real-Time Search:** Using SerpApi, S2S queries live platforms in real time:
   - **Catchafire:** Active non-profit & NGO projects (branding, financial budgeting, surveys, research).
   - **Upwork & Freelance Platforms:** Live freelance client briefs and entry-level contract tasks.
   - **Kaggle:** Active data science competitions, exploratory challenges, and public datasets.
   - **UN Volunteers:** Global civic and socio-economic research assignments.
   - **Open Source & Bounties:** Live GitHub issues, bugs, and feature bounties.
4. **The "Why You Can Do This" Bridge:** Cites the exact course unit that qualifies the student to execute and ship the live deliverable.
5. **Ship Blueprint:** Generates an actionable 3-phase execution guide and STAR resume bullet point.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- SerpApi API Key ([Get a free key here](https://serpapi.com/manage-api-key))

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/RakshamDessai/SerpApi-Hackathon.git
cd SerpApi-Hackathon

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API Key
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your SerpApi key:
```env
SERPAPI_API_KEY=your_actual_serpapi_key_here
```

### 4. Verify Connection
```bash
python test_serpapi.py
```

### 5. Launch Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🏗️ Repository Structure

```
├── src/
│   ├── __init__.py
│   ├── config.py           # Environment loader and key validation
│   ├── serpapi_service.py  # Structured SerpApi multi-engine search client
│   └── agent.py            # Autonomous query planning & research agent
├── app.py                  # Interactive Streamlit dashboard
├── test_serpapi.py         # Connectivity diagnostic script
├── IMPLEMENTATION_PLAN.md  # Complete technical blueprint & 55-feature catalog
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variable template
└── .gitignore              # Clean ignore rules
```

---

## 📜 License
MIT License.
