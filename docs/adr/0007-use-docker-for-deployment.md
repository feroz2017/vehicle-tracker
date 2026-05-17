# 7. Use Docker for deployment

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We need to decide how to deploy the app. The app consists of a client-side app, a server-side app and various Redis instances.  

## Decision

We'll containerize the application using Docker. The client-side web application and server-side backend will be containerized separately. Using Docker makes it easy to manage our Redis instance(s).

Using Docker also makes it easy to set up a common development environment and to automate the delivery process during CI/CD. We can manage different build versions with different image tags.

Docker allows for flexible deployment. Multiplying client app and server instances will be easier.

## Consequences

Requires Docker for deployment.

## Notes