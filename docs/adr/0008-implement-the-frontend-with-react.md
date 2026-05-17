# 8. Implement the frontend with React

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We need to pick the technology to implement the client-side UI of our application.

The UI needs to be able to show bus routes and vehicle positions on a map and to smoothly update the vehicle positions. We want the app to have a smooth user experience.

Since we're building a Web app, the UI needs to run in a browser.

## Decision

We'll implemet the UI as an single page application using a React framework.

Using an SPA framework makes it easier to implement real-time updates and map functionality using Leaflet/Mapbox GL JS/etc.

React is a mature technology with a lot of support and libraries for UI components.

## Consequences

Adds complexity and can be slow to run and load. Need to pay attention to performance, especially on mobile devices.

## Notes