# 1. Build a Web application

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We need to pick a platform for the project application. 

The application will show the user a list of possible bus routes from point A to point B and let hte user track vehicle positions on chosen bus route. The app will show the data to the user on a map.

## Decision

We will build a Web application with a client-server architecture.

We also considered building a mobile application. We chose a web app because the members in our group have more experience building web applications. It is a fast way to implement a first version of the software.

Our users will most likely want to access our application using their mobile devices. A web app is accessed through a browser and it can run on multiple different devices.

The main functionality of the app is real-time data updates, so offline access is not essential.

## Consequences

The performance of the client-side UI will most likely be worse than a mobile application.

We can't use the full functionalities offered by a device (push notifications, etc...).


## Notes