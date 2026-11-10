
# DukaanSathi AI 🏪
### Your Shop. Your Voice. Your Digital Assistant.

DukaanSathi AI is a voice-first AI assistant built to simplify everyday shop management for small retailers in India.

Meet **Chotu** — an intelligent voice assistant that helps shopkeepers manage inventory, record sales, track customer credit (udhaar), record repayments, and access business information through natural Hindi, Hinglish, and English voice commands.

The goal is simple: make managing a shop as easy as having a conversation.

---

## 🚀 The Problem

Small shopkeepers often manage their businesses using physical registers and manual calculations.

- Maintaining inventory and tracking stock.
- Recording daily sales and payment methods.
- Managing customer credit and outstanding balances.
- Tracking repayments.
- Understanding daily business performance.

These repetitive tasks take time away from serving customers and growing the business.

## 💡 Our Solution

DukaanSathi AI brings these operations into one platform powered by a conversational AI assistant.

Instead of navigating multiple screens or manually entering every transaction, shopkeepers can simply speak to Chotu.

Chotu understands the instruction, extracts the relevant information, and uses backend business logic to process the operation and update the records.

## ✨ Key Features

### 🎙️ Voice-First AI Assistant
- Natural voice interaction with Chotu.
- Supports Hindi, Hinglish, and English commands.
- Speech-to-Text and Text-to-Speech integration.

### 📦 Inventory Management
- Add and manage products.
- Track stock quantities.
- Configure product pricing.
- Identify low-stock products.

### 💰 Sales Management
- Record sales through voice commands.
- Support for Cash, UPI, and Udhaar transactions.
- Maintain sales records.

### 👥 Customer Khata
- Maintain customer information.
- Track outstanding customer balances.
- Record customer repayments.

### 📊 Business Dashboard
- View business statistics.
- Monitor recent sales.
- Track inventory and outstanding balances.
- Access important business information.

### 🤖 Conversational Business Queries
- Ask questions about sales.
- Retrieve available business information through natural language.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| Backend | Python, Flask |
| Database | SQLite, SQLAlchemy |
| AI / NLU | Groq API, GPT-OSS-20B |
| Speech-to-Text | Gnani Prisma |
| Text-to-Speech | Gnani Timbre |
| Frontend | HTML, CSS, JavaScript |
| Authentication | Flask-Login |

---

## ⚙️ How It Works

```text
Shopkeeper's Voice Command
          |
          v
   Speech-to-Text
    (Gnani Prisma)
          |
          v
   Natural Language
    Understanding
    (Groq API)
          |
          v
   Intent & Entity
     Extraction
          |
          v
  Python Backend Logic
          |
          v
   Database Operations
    (SQLite / SQLAlchemy)
          |
          v
   Response Generation
          |
          v
     Text-to-Speech
     (Gnani Timbre)
          |
          v
   Spoken Response
       from Chotu
```

**Design principle:** AI handles language understanding, while deterministic Python backend services handle business calculations, validation, permissions, and database transactions.

This separation helps keep business operations reliable and prevents the language model from directly modifying business records.

---

## 🔐 Security & Reliability

- Shop-scoped data access.
- Authentication for shop accounts.
- Backend validation before database operations.
- Business transactions handled through backend services.
- AI service failures should not be allowed to silently corrupt business records.

---

## 📸 Project Demo

Demo Video : https://www.youtube.com/watch?v=rhwt-ourtKM

**Screenshots:** Coming soon.

---

## 🎯 Project Vision

Our vision is to make AI genuinely useful for small businesses.

DukaanSathi AI aims to reduce the complexity of everyday shop management and make digital tools accessible to local shopkeepers through something they already use every day — their voice.

---

## 👨‍💻 Developer

**Vinayak Dubey**

GitHub: [@vinayak932](https://github.com/vinayak932)

---

## 📄 Project Description

For a concise overview of the problem, solution, features, architecture, and vision, see [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md).

---

**DukaanSathi AI — Your Shop. Your Voice. Your Digital Assistant.**
