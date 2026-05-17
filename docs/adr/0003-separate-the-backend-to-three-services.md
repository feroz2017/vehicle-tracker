# 3. Separate the backend to two services with their own responsibilities 

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

The server-side backend application needs to poll the external APIs for route and vehicle data, store and filter that data and serve and publish the data to our client app.

We need to pick the technology for implementing our backend API server. 

The server sends data to the client app and needs to be able to manage WebSocket connections and it needs to offer a REST API.

The backend is also responsible for fetching the vehicle and route data from external APIs and storing the result to a cache database.

## Decision

We'll separate the backend functions into a worker and a application service. The worker service will be responsible for getting the data from external APIs and for managing. The application service will be responsible for providing the APIs to the frontend. The services will communicate using a shared database.

We'll use Python and the FastAPI framework for server implementation.

Python has a lot of mature, trusted libraries that can be used to implement all required backend functions.

FastAPI can be used to build multiple kinds of APIs and offers the tools to build both REST APIs and WebSocket APIs. It also comes with easy tools for server deployment and good tools for API documentation.

## Consequences

We're restricted to using Python libraries.

## Notes