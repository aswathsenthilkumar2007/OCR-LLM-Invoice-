# OCR LLM Invoice Processing System

An AI-powered invoice processing system that extracts invoice information using PaddleOCR and applies intelligent data normalization, validation, and duplicate invoice detection.

## Overview

The OCR LLM Invoice Processing System aims to automate invoice data extraction and processing, reducing manual data entry and improving data consistency.

The backend uses FastAPI to expose APIs and PaddleOCR to extract text from uploaded invoice documents.

## Current Features

- Invoice image upload and processing
- OCR-based text extraction using PaddleOCR
- Date normalization
- Amount normalization
- Text normalization
- Duplicate detection foundation
- Backend API using FastAPI

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Backend Framework | FastAPI |
| OCR Engine | PaddleOCR |
| Server | Uvicorn |
| Data Validation | Python |
| Version Control | Git and GitHub |

## Project Structure

```text
OCR-Invoice-AI/
│
├── backend/
│   └── app/
│       └── services/
│
├── tests/
│
├── README.md
├── .gitignore
└── requirements.txt
```

*The project structure above is a simplified overview and may evolve during development.*

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/aswathsenthilkumar2007/OCR-LLM-Invoice-.git
cd OCR-LLM-Invoice-
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the backend

Use the FastAPI application entry point configured in your project.

For example:

```bash
uvicorn backend.app.main:app --reload
```

### 6. Access API documentation

```text
http://127.0.0.1:8000/docs
```

## Development Roadmap

- [x] FastAPI backend setup
- [x] OCR integration using PaddleOCR
- [x] Date, amount and text normalization
- [x] Initial duplicate detection implementation
- [ ] Advanced invoice field validation
- [ ] Database integration
- [ ] LLM-powered structured invoice extraction
- [ ] Improved duplicate invoice detection
- [ ] Frontend dashboard
- [ ] Complete end-to-end testing

## Project Status

Currently under active development.

## Author

Aswath S

AI & Data Science Engineering Student