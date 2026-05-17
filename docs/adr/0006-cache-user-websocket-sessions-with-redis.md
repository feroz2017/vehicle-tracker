# 6. Cache user WebSocket sessions with Redis

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We need to be able to duplicate our backend server. Each server needs to see 

## Decision

We'll store the WebSocket sessions with Redis. Each server instance accesses the same Redis database. Each client will use only one of the servers and the load balancer needs to relay each client to the right server.

This complicates the WebSocket connection management, since now the server(s) needs to store and manage user sessions. However, this allows the app to scale dynamically based on the number of users.

## Consequences

## Notes