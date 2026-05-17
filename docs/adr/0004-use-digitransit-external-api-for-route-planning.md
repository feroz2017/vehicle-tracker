# 4. Use Digitransit external API for route planning

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We want to plan all the possible bus routes between the start and end coordinates provided by the user.

## Decision

We'll use the additional external [Digitransit API](https://digitransit.fi/en/developers/apis/) Routing API to plan possible user routes between two coordinate locations.

Digitransit provides a ready and reliable routing API. Implementing and testing the routing logic ourselves would take more work and it would not provide significantly more value to our app.

## Consequences

Using the Digitransit API means that we have an additional external API dependency.

## Notes