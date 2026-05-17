# 9. Use GitHub Actions to implement a CI/CD pipeline

Date: 2026-05-06

Participants: Muhammad Feroz, Joakim Haukilehto, Elina Juutilainen

## Status

Accepted

## Context

We want to automate the application testing and delivery process.

## Decision

We'll use GitHub version control and GitHub actions for implementing a CI/CD pipeline. The CI/CD pipeline will have a testing and a Docker image build step.

This allows for the continuos integration and delivery of the application. We can verify that the application works as it should after code changes.

We'll use a trunk-based development strategy and commit our code changes to the main branch. We'll run the CI/CD jobs for the main branch.

## Consequences

The CI/CD pipeline requires upkeep and maintenance.

## Notes

Currently there's no full test coverage, the main goal is to have a functioning automation pipeline. Adding wider test coverage in the future would be necessary.

## Notes