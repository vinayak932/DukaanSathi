# DukaanSathi AI – Your Voice-Powered Digital Shop Assistant

### Making everyday shop management simpler through AI and natural conversation.

## 1. Overview

DukaanSathi AI is a voice-first AI assistant designed to simplify daily operations for small shopkeepers and local retail businesses in India. It allows shopkeepers to manage essential business activities through natural Hindi, Hinglish and English voice commands instead of manually navigating multiple screens or maintaining every transaction in a physical register.

At the centre of the platform is **Chotu**, an intelligent voice assistant that understands shopkeeper instructions and helps execute business operations.

## 2. The Problem

Small retail businesses often manage their daily operations manually. Shopkeepers have to:
- Maintain inventory and keep track of stock.
- Record daily sales and payment methods.
- Manage customer credit (udhaar) and repayments.
- Keep track of outstanding customer balances.
- Calculate and review daily business performance.

These activities consume valuable time and can lead to mistakes or incomplete records.

## 3. Our Solution

DukaanSathi AI brings these operations together in one platform. Shopkeepers can simply speak to Chotu in their everyday language. The system interprets their instructions and uses deterministic backend logic to perform the relevant operations and update business records.

The goal is to make technology accessible to shopkeepers without requiring them to learn complicated software or workflows.

## 4. Key Features

- **Voice-Based Interaction:** Communicate with Chotu using Hindi, Hinglish and English.
- **Inventory Management:** Add products, update stock and manage product information.
- **Sales Management:** Record sales with cash, UPI or udhaar payment methods.
- **Customer Khata:** Maintain customer records and outstanding credit balances.
- **Repayment Tracking:** Record payments received from customers against existing udhaar.
- **Business Queries:** Ask questions about sales and available business information.
- **Dashboard:** View important business figures, recent sales and low-stock products.
- **Voice Responses:** Receive spoken responses from Chotu.

## 5. Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite, SQLAlchemy |
| AI / Natural Language Understanding | Groq API – GPT-OSS-20B |
| Speech-to-Text | Gnani Prisma |
| Text-to-Speech | Gnani Timbre |
| Frontend | HTML, CSS, JavaScript |
| Authentication | Flask-Login |

## 6. How It Works

1. The shopkeeper gives a voice command.
2. Speech-to-Text converts the audio into text.
3. The AI layer interprets the user's intent and extracts relevant information.
4. Python backend services validate the request and perform the appropriate database operation.
5. Chotu generates a response, which is converted into speech.
6. The updated information is available through the dashboard.

**An important design principle:** AI is used to understand natural language, while actual business calculations, transaction validation and database updates are handled by backend logic.

## 7. Vision

Our vision is to make AI genuinely useful for small businesses by building technology around the way people already work and communicate.

DukaanSathi AI aims to reduce the complexity of shop management and give local shopkeepers a simple, accessible digital assistant.

**DukaanSathi AI – Your Shop. Your Voice. Your Digital Assistant.**
