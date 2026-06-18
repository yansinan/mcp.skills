# MCP Streamable HTTP Transport — Spec Excerpts (2025-06-18)

Source: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

## Core Structure

- Server provides **single HTTP endpoint** (`/mcp`) supporting both POST and GET
- Replaces the older HTTP+SSE transport from 2024-11-05

## POST Requests (Client → Server)

- Every JSON-RPC message = new HTTP POST
- **MUST** include `Accept: application/json, text/event-stream`
- Body = single JSON-RPC request/notification/response
- Server MUST respond with either:
  - `Content-Type: text/event-stream` (SSE stream)
  - `Content-Type: application/json` (single response)
  - 202 Accepted (for notifications/responses with no body)

## GET Requests (Listening for Server Messages)

- Client MAY issue GET to open SSE stream
- **MUST** include `Accept: text/event-stream`
- Server either:
  - Returns SSE stream (`Content-Type: text/event-stream`)
  - Returns 405 Method Not Allowed

## Session Management

- Server MAY assign session ID in `Mcp-Session-Id` header on InitializeResult
- Session ID: globally unique, cryptographically secure, ASCII visible chars only
- Client MUST include `Mcp-Session-Id` on all subsequent requests
- Server MAY terminate session → responds 404
- Client sends DELETE + `Mcp-Session-Id` to close session

## Protocol Version Header

- Client MUST include `MCP-Protocol-Version: <version>` on all requests
- Fallback: if header absent, server assumes `2025-03-26`
- Invalid version → 400 Bad Request

## Auth

Spec does NOT define auth mechanism — delegated to transport layer.
- Servers SHOULD implement proper authentication
- Common patterns: `Authorization: Bearer`, custom headers
