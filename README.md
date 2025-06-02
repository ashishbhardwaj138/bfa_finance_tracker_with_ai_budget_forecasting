# 💸 Smart Personal Finance Tracker

A full-stack, AI-powered open-source application that intelligently extracts financial data from your emails, visualizes it via an intuitive dashboard, and predicts your future expenses — all while running securely on your local system.

---

## 🧠 Key Features

- 🔐 Secure Gmail or IMAP login (OAuth2/token-based)
- 📥 Auto-fetch and parse transaction-related emails
- 🏷️ NLP-powered classification of credit/debit, vendor, category, etc.
- 📊 Interactive dashboard for insights
- 📈 Budget forecasting using time-series ML (Prophet)
- 🗃️ Fully self-hosted, no cloud or server dependency
- 🛠️ Modular Django + React + Celery architecture

---

## 🚀 Demo Screenshots

*To be added after first implementation phase*

---

## 🧩 Architecture Overview

- **Frontend**: React + Tailwind CSS
- **Backend**: Django REST Framework
- **ML Modules**: spaCy (NLP), Prophet (Forecasting)
- **Database**: PostgreSQL
- **Queue**: Celery + Redis
- **Deployment**: Docker Compose (runs locally)

---

## 🧰 Prerequisites

- Python 3.10+
- Node.js 16+
- Docker + Docker Compose
- Gmail or IMAP-compatible email account
- Gmail API credentials (if using Gmail)

---

## 📦 Local Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/finance-tracker-ai.git
cd finance-tracker-ai
