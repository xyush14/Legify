"""Headnote WhatsApp bot package.

Spec: docs/WHATSAPP_BOT_PRD.md
Migration: migrations/006_whatsapp_bot.sql

Modules
-------
client     — Meta Cloud API send-message wrapper
session    — conversation state, quota tracking, phone↔user linkage
handlers   — intent dispatch (LINK / HELP / UPGRADE / REFINE / research)
formatters — WhatsApp text + PDF memo formatting

The webhook route lives in headnote/api/whatsapp.py.
"""
