# 5. Cache route and vehicle data with Redis

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We're polling the Waltti API to get the latest route and vehicle position data. 

Waltti API is rate limited so we need to restrict the number of requests that we send to it. Additionally, if the Waltti API goes down or we are unable to reach it, we want to show the user data from the last succesfull request. 

## Decision

We'll store the latest vehicle position and route data locally. We'll use a Redis database for data storage.

A key-value database allows flexible data values and offers fast data retrieval. We're only storing the latest request data and we're not storing the data for long periods of time.

If the external Waltti API goes down, we can serve the latest available update from our local database.

## Consequences

We need to manage our Redis instance.

## Notes
