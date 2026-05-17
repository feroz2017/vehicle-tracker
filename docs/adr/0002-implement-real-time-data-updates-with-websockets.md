# 2. Implement real-time data updates with Websockets

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

The client-app needs to receive real-time updates of the vehicle positions. For efficiency the user should only get the positional data of the vehicles they are interested in.

## Decision

We'll use WebSockets and a publish/subscribe architecture to send position data to clients.

The publish/subscribe pattern is an efficient way to send data updates. Clients can subscribe only for the data they need and our server will only send new data when it's received.

## Consequences

## Notes